

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from itertools import islice
import json
from pathlib import Path
import sys
from time import perf_counter_ns
from typing import TextIO

TOP_K = 5
REQUIRED_QUERIES = (
    "cristina lopes",
    "machine learning",
    "ACM",
    "master of software engineering",
)
FindURLs = Callable[[str, int], Iterable[str]]


@dataclass(frozen=True)
class QueryResult:
    query: str
    urls: tuple[str, ...]
    elapsed_ms: float


def run_query(find_urls: FindURLs, query: str) -> QueryResult:
    """Time retrieval through URL resolution, excluding console output."""
    started = perf_counter_ns()
    urls = tuple(islice(find_urls(query, TOP_K), TOP_K))
    return QueryResult(query, urls, (perf_counter_ns() - started) / 1_000_000)


def print_result(result: QueryResult, output: TextIO) -> None:
    if result.urls:
        for number, url in enumerate(result.urls, start=1):
            print(f"{number}. {url}", file=output)
    else:
        print("No results.", file=output)
    print(f"Search time: {result.elapsed_ms:.2f} ms", file=output)
    print(file=output, flush=True)


def run_console(find_urls: FindURLs, source: TextIO, output: TextIO) -> None:
    print("ICS Search | Milestone 2", file=output)
    print("Enter a query, or type :quit to exit.", file=output)
    while True:
        print("Search> ", end="", file=output, flush=True)
        line = source.readline()
        if not line:
            print(file=output)
            return
        query = line.strip()
        if query.casefold() == ":quit":
            return
        if query:
            print_result(run_query(find_urls, query), output)


def connect_backend(index_dir: Path) -> tuple[FindURLs, Callable[[], None]]:
    """Adapt the team's search API to a callable returning URLs in result order.

    Assumed handoff: IndexReader(index_dir), search(reader, query, top_k=5)
    returning URL strings. If the team returns IDs or scored hits, translate
    those to URLs here using its reader, preserving the returned order.
    """
    from .query import IndexReader, search

    reader = IndexReader(index_dir)

    def find_urls(query: str, limit: int) -> Iterable[str]:
        return search(reader, query, top_k=limit)

    return find_urls, getattr(reader, "close", lambda: None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index_dir", type=Path, help="directory containing the built index")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--required", action="store_true", help="run the four report queries")
    mode.add_argument("--query", action="append", help="run a query; repeat for multiple queries")
    parser.add_argument("--results-json", type=Path, help="save batch results for the report")
    args = parser.parse_args(argv)
    if args.results_json and not (args.required or args.query):
        parser.error("--results-json requires --required or --query")

    try:
        find_urls, close = connect_backend(args.index_dir)
    except ModuleNotFoundError as exc:
        if exc.name != "search.query":
            raise
        parser.exit(1, "Cannot find search/query.py. Add the team's search backend first.\n")
    except OSError as exc:
        parser.exit(1, f"Could not open index: {exc}\n")

    try:
        if args.required or args.query:
            queries = REQUIRED_QUERIES if args.required else args.query
            results = []
            for query in queries:
                print(f"Search> {query}")
                result = run_query(find_urls, query)
                print_result(result, sys.stdout)
                results.append(result)
            if args.results_json:
                with args.results_json.open("w", encoding="utf-8") as stream:
                    json.dump([asdict(result) for result in results], stream, indent=2,
                              ensure_ascii=False)
                    stream.write("\n")
        else:
            run_console(find_urls, sys.stdin, sys.stdout)
    except KeyboardInterrupt:
        print()
        return 130
    finally:
        close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
