

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from search.search import REQUIRED_QUERIES, main, run_console, run_query


class ConsoleTests(unittest.TestCase):
    def test_top_five_preserves_backend_order(self):
        def find_urls(query, limit):
            self.assertEqual((query, limit), ("machine learning", 5))
            return (f"https://example.org/{i}" for i in range(7, 0, -1))

        result = run_query(find_urls, "machine learning")
        self.assertEqual(result.urls, tuple(f"https://example.org/{i}" for i in range(7, 2, -1)))
        self.assertGreaterEqual(result.elapsed_ms, 0)

    def test_console_handles_blank_query_no_hits_and_exit(self):
        calls = []

        def find_urls(query, limit):
            calls.append(query)
            return []

        output = io.StringIO()
        run_console(find_urls, io.StringIO("\nmissing term\n:quit\nunused\n"), output)
        self.assertEqual(calls, ["missing term"])
        self.assertIn("No results.", output.getvalue())
        self.assertRegex(output.getvalue(), r"Search time: \d+\.\d{2} ms")

    def test_required_batch_saves_results_and_closes_reader(self):
        calls = []
        closed = []

        def find_urls(query, limit):
            calls.append(query)
            return ["https://example.org/result"]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            with patch("search.search.connect_backend", return_value=(find_urls, lambda: closed.append(True))):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = main([directory, "--required", "--results-json", str(path)])
            self.assertEqual(status, 0)
            results = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(tuple(calls), REQUIRED_QUERIES)
        self.assertEqual([entry["query"] for entry in results], list(REQUIRED_QUERIES))
        self.assertTrue(all(entry["urls"] == ["https://example.org/result"] for entry in results))
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
