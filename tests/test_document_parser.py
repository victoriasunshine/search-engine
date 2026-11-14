"""Small hand-checkable contracts for Part A and its teammate interface."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from indexer.document_parser import DocumentError, iter_documents, parse_document


def record(content, url="https://example.org/page?q=1#section"):
    return {"url": url, "content": content, "encoding": "utf-8"}


class ParserTests(unittest.TestCase):
    def test_full_text_and_important_regions(self):
        doc = parse_document(record(
            "<title>Search &amp; Retrieval</title><h1>A <strong>Good</strong> Title</h1>"
            "<p>The <b>quick</b> fox.</p><h3>Details</h3><h6>Small heading</h6>"
        ), "sample.json")
        self.assertEqual(doc.url, "https://example.org/page?q=1")
        self.assertEqual(doc.text, "Search & Retrieval A Good Title The quick fox. Details Small heading")
        self.assertEqual(doc.title_text, "Search & Retrieval")
        self.assertEqual(doc.heading_text, "A Good Title Details Small heading")
        self.assertEqual(doc.bold_text, "Good quick")
        self.assertEqual(doc.important_text, "Search & Retrieval A Good Title quick Details Small heading")
        self.assertEqual(doc.source_path, "sample.json")

    def test_nested_bold_is_not_duplicated(self):
        doc = parse_document(record("<h2>one <b>two <strong>three</strong></b> four</h2>"))
        self.assertEqual(doc.text, "one two three four")
        self.assertEqual(doc.important_text, doc.text)
        self.assertEqual(doc.bold_text, "two three")

    def test_noncontent_and_comments_are_removed_but_tails_remain(self):
        doc = parse_document(record(
            "<p>Before</p><script>bad()</script><style>.bad{}</style>"
            "<noscript>fallback</noscript><template>unused</template><!--secret-->"
            "<p>After <script>bad()</script>tail</p>"
        ))
        self.assertEqual(doc.text, "Before After tail")

    def test_broken_html(self):
        doc = parse_document(record("<h1>Broken</h1><p>Hello <strong>world"))
        self.assertEqual(doc.text, "Broken Hello world")
        self.assertEqual(doc.bold_text, "world")

    def test_deeply_nested_page_is_not_silently_truncated(self):
        content = "<div>" * 500 + "<b>Deep text</b>" + "</div>" * 500 + "<p>Tail</p>"
        doc = parse_document(record(content))
        self.assertEqual(doc.text, "Deep text Tail")
        self.assertEqual(doc.bold_text, "Deep text")

    def test_plain_empty_and_unicode(self):
        self.assertEqual(parse_document(record("Plain text\nwith  spaces")).text,
                         "Plain text with spaces")
        self.assertEqual(parse_document(record(" \n ")).text, "")
        doc = parse_document(record('<meta charset="ascii"><p>Café 中文 &amp; tea&nbsp;time</p>'))
        self.assertEqual(doc.text, "Café 中文 & tea time")

    def test_comment_and_declaration_only_pages(self):
        for content in ["<!--comment-->", "<!DOCTYPE html>", "<!--unclosed"]:
            with self.subTest(content=content):
                self.assertEqual(parse_document(record(content)).text, "")

    def test_inline_and_block_word_boundaries(self):
        doc = parse_document(record("<p>co<b>op</b>erate</p><div>next<br>line</div><b>first</b><b>second</b>"))
        self.assertEqual(doc.text, "cooperate next line firstsecond")
        self.assertEqual(doc.bold_text, "op first second")

    def test_xml_declaration_and_optional_encoding(self):
        value = record('<?xml version="1.0" encoding="iso-8859-1"?><p>Café</p>')
        del value["encoding"]
        doc = parse_document(value)
        self.assertEqual(doc.text, "Café")
        self.assertIsNone(doc.encoding)

    def test_invalid_records_are_rejected(self):
        for value in [[], {}, record(None), record("text", ""), record("text", "#only"),
                      {**record("text"), "encoding": 3}]:
            with self.subTest(value=value), self.assertRaises(DocumentError):
                parse_document(value)

    def test_directory_zip_parity_and_error_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            (corpus / "domain").mkdir(parents=True)
            files = {
                "domain/b.json": json.dumps(record("<h2>Second</h2>")),
                "domain/a.json": json.dumps(record("First")),
                "domain/bad.json": "{bad",
                "__MACOSX/fake.json": "bad",
                "domain/._fake.json": "bad",
                "domain/ignore.txt": "ignored",
            }
            archive_path = root / "corpus.zip"
            with ZipFile(archive_path, "w") as archive:
                for name, value in files.items():
                    path = corpus / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(value, encoding="utf-8")
                    archive.writestr(name, value)
            errors = []
            docs = list(iter_documents(corpus, on_error=lambda p, e: errors.append(p)))
            zipped = list(iter_documents(archive_path, on_error=lambda p, e: None))
            self.assertEqual(docs, zipped)
            self.assertEqual([d.source_path for d in docs], ["domain/a.json", "domain/b.json"])
            self.assertEqual(errors, ["domain/bad.json"])
            # Same cleaned URL is retained for each separate input document.
            self.assertEqual(docs[0].url, docs[1].url)
            with self.assertRaises(DocumentError):
                list(iter_documents(corpus, strict=True))
            single = list(iter_documents(corpus / "domain/a.json"))
            self.assertEqual(single[0].text, "First")

    def test_bom_json_and_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.json"
            path.write_text(json.dumps(record("Hi")), encoding="utf-8-sig")
            self.assertEqual(next(iter_documents(path)).text, "Hi")
            with self.assertRaises(FileNotFoundError):
                list(iter_documents(path.parent / "missing"))

    def test_command_line_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.json"
            output = Path(tmp) / "parsed.jsonl"
            path.write_text(json.dumps(record("<h1>Hello</h1>")), encoding="utf-8")
            script = Path(__file__).resolve().parents[1] / "document_parser.py"
            result = subprocess.run([sys.executable, str(script), str(path), "--output", str(output)],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(output.read_text())["heading_text"], "Hello")
            self.assertIn("Parsed 1 documents; skipped 0", result.stderr)


if __name__ == "__main__":
    unittest.main()
