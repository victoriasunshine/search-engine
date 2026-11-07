"""Milestone 1, Part A: stream corpus JSON records into parsed documents.

No tokenization, stemming, document IDs, or indexing happens in this module.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from html import unescape
import json
import logging
from pathlib import Path
import re
import sys
from typing import Callable, Iterator
from urllib.parse import urldefrag
from zipfile import ZipFile

from lxml import etree, html


@dataclass(frozen=True)
class ParsedDocument:
    url: str
    text: str
    title_text: str
    heading_text: str
    bold_text: str
    important_text: str
    source_path: str
    encoding: str | None = None

    def to_dict(self) -> dict:
        """Return a JSON-serializable record for a teammate's pipeline."""
        return asdict(self)


class DocumentError(ValueError):
    """A corpus record is invalid or cannot be parsed."""


EXCLUDED_TAGS = frozenset({"script", "style", "noscript", "template"})
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "body", "br", "caption",
    "dd", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer",
    "form", "head", "header", "hr", "html", "li", "main", "nav", "ol", "p",
    "pre", "section", "table", "tbody", "td", "th", "thead", "title", "tr", "ul",
}) | HEADING_TAGS


def _normalize(text: str) -> str:
    # Avoid materializing millions of individual words for large text files.
    return re.sub(r"\s+", " ", text).strip()


def _extract_text(content: str) -> dict[str, str]:
    """Recover broken HTML; keep each text occurrence once per output field.

    Inline tags preserve word boundaries (e.g. co<b>op</b>erate); block tags
    insert spaces. The iterative traversal also avoids Python recursion limits.
    This is structural extraction, not browser rendering or CSS visibility.
    """
    fields = {key: [] for key in (
        "text", "title_text", "heading_text", "bold_text", "important_text"
    )}
    if not content.strip():
        return {key: "" for key in fields}
    if "<" not in content:
        # The corpus includes large plain-text files, not just HTML pages.
        return {key: _normalize(unescape(content)) if key == "text" else ""
                for key in fields}
    # JSON has already decoded the content into Unicode. Ignore stale HTML
    # charset declarations rather than decoding that Unicode a second time.
    # Crawled pages can have deeply nested layouts. The default depth limit can
    # silently truncate these when recover=True, so allow large local pages.
    parser = html.HTMLParser(encoding="utf-8", recover=True, no_network=True,
                             huge_tree=True)
    try:
        root = html.document_fromstring(content.encode("utf-8"), parser=parser)
    except (etree.ParserError, etree.XMLSyntaxError, UnicodeError) as exc:
        # Comments/declarations alone are valid empty-text pages. Resource
        # limits or other fatal errors must still be reported rather than lost.
        if (isinstance(exc, etree.ParserError) and str(exc) == "Document is empty"
                and not any(e.level_name == "FATAL" for e in parser.error_log)):
            return {key: "" for key in fields}
        raise DocumentError(f"HTML parsing failed: {exc}") from exc
    if any(error.level_name == "FATAL" for error in parser.error_log):
        raise DocumentError(f"HTML parser could not recover: {parser.error_log.last_error}")

    def append(value: str | None, flags: tuple[bool, bool, bool]) -> None:
        if value:
            fields["text"].append(value)
            for key, active in zip(("title_text", "heading_text", "bold_text"), flags):
                if active:
                    fields[key].append(value)
            if any(flags):
                fields["important_text"].append(value)

    # Events carry ancestor flags; a child tail belongs to its parent context.
    stack = [("node", root, (False, False, False))]
    while stack:
        event, value, flags = stack.pop()
        if event == "text":
            append(value, flags)
            continue
        node = value
        if not isinstance(node.tag, str):  # comments / processing instructions
            continue
        tag = node.tag.lower()
        if tag in EXCLUDED_TAGS:
            continue
        active = (flags[0] or tag == "title",
                  flags[1] or tag in HEADING_TAGS,
                  flags[2] or tag in {"b", "strong"})
        # Separate independent important regions, including inline bold spans.
        for key, old, new in zip(("title_text", "heading_text", "bold_text"), flags, active):
            if new and not old:
                fields[key].append(" ")
        if any(active) and not any(flags):
            fields["important_text"].append(" ")
        if tag in BLOCK_TAGS:
            append(" ", active)
            stack.append(("text", " ", active))
        children = list(node)
        for child in reversed(children):
            stack.append(("text", child.tail, active))
            stack.append(("node", child, active))
        append(node.text, active)
    return {key: _normalize("".join(parts)) for key, parts in fields.items()}


def parse_document(record: dict, source_path: str = "") -> ParsedDocument:
    """Parse a decoded dataset record without changing case or removing words.

    URL fragments are removed; query strings are preserved. Repeated URLs are
    retained so that the indexing team can choose its own deduplication policy.
    """
    if not isinstance(record, dict):
        raise DocumentError("JSON record must be an object")
    if not isinstance(record.get("url"), str) or not record["url"].strip():
        raise DocumentError("record needs a nonempty string 'url'")
    if not isinstance(record.get("content"), str):
        raise DocumentError("record needs a string 'content'")
    encoding = record.get("encoding")
    if encoding is not None and not isinstance(encoding, str):
        raise DocumentError("'encoding' must be a string or null")
    try:
        url = urldefrag(record["url"].strip())[0]
    except ValueError as exc:
        raise DocumentError(f"invalid URL: {exc}") from exc
    if not url:
        raise DocumentError("URL is empty after removing the fragment")
    return ParsedDocument(url=url, source_path=source_path, encoding=encoding,
                          **_extract_text(record["content"]))


def _is_record(path: str) -> bool:
    parts = Path(path).parts
    return path.lower().endswith(".json") and not any(
        part.startswith(".") or part == "__MACOSX" for part in parts
    )


def iter_documents(
    source: str | Path, *, strict: bool = False,
    on_error: Callable[[str, Exception], None] | None = None,
) -> Iterator[ParsedDocument]:
    """Read a ZIP, directory tree, or single JSON file in stable path order.

    Only one document's content is held at a time. ZIP member names and folder
    paths are sorted for reproducibility. Invalid records are logged and skipped
    by default; strict=True raises DocumentError on the first invalid record.
    Missing input paths or unreadable/corrupt ZIP archives always raise.
    """
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(source)

    def read_one(label: str, read: Callable[[], bytes]) -> ParsedDocument | None:
        try:
            # Corpus JSON is UTF-8; utf-8-sig also accepts an optional BOM.
            return parse_document(json.loads(read().decode("utf-8-sig")), label)
        except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
            if strict:
                raise DocumentError(f"{label}: {exc}") from exc
            if on_error is not None:
                on_error(label, exc)
            else:
                logging.getLogger(__name__).warning("Skipping %s: %s", label, exc)
            return None

    if source.is_file() and source.suffix.lower() == ".zip":
        with ZipFile(source) as archive:
            for name in sorted(n for n in archive.namelist() if _is_record(n)):
                doc = read_one(name, lambda: archive.read(name))
                if doc is not None:
                    yield doc
    else:
        paths = sorted(source.rglob("*.json")) if source.is_dir() else [source]
        for path in paths:
            label = path.relative_to(source).as_posix() if source.is_dir() else path.name
            if not _is_record(label):
                continue
            doc = read_one(label, path.read_bytes)
            if doc is not None:
                yield doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="dataset ZIP, directory, or JSON")
    parser.add_argument("--output", type=Path, help="JSON Lines output (default: stdout)")
    parser.add_argument("--strict", action="store_true", help="stop on a bad record")
    args = parser.parse_args()
    # Do not let an output file overwrite a corpus input.
    if args.output and (args.output.resolve() == args.source.resolve() or
                        args.output.suffix.lower() != ".jsonl"):
        parser.error("--output must be a separate .jsonl file")
    count = skipped = 0

    def report_error(label: str, exc: Exception) -> None:
        nonlocal skipped
        skipped += 1
        print(f"Skipping {label}: {exc}", file=sys.stderr)

    stream = args.output.open("w", encoding="utf-8") if args.output else sys.stdout
    try:
        for doc in iter_documents(args.source, strict=args.strict, on_error=report_error):
            stream.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    finally:
        if args.output:
            stream.close()
    print(f"Parsed {count} documents; skipped {skipped} invalid records.", file=sys.stderr)


if __name__ == "__main__":
    main()
