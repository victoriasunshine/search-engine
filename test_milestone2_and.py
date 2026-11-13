

import os
from pathlib import Path
import unittest

from search.search import connect_backend, run_query

ROOT = "https://example.org/"


@unittest.skipUnless(os.environ.get("MILESTONE2_AND_INDEX"), "build and set MILESTONE2_AND_INDEX")
class BooleanANDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        find_urls, close = connect_backend(Path(os.environ["MILESTONE2_AND_INDEX"]))
        cls.find_urls = staticmethod(find_urls)
        cls.addClassCleanup(close)

    def assert_urls(self, query, *pages):
        self.assertCountEqual(run_query(self.find_urls, query).urls, [ROOT + page for page in pages])

    def test_single_terms_have_both_shared_and_exclusive_documents(self):
        self.assert_urls("galaxy", "both", "galaxy-only")
        self.assert_urls("telescope", "both", "telescope-only")

    def test_two_terms_require_both(self):
        self.assert_urls("galaxy telescope", "both")

    def test_query_order_and_duplicate_terms_preserve_intersection(self):
        self.assert_urls("telescope galaxy galaxy", "both")

    def test_missing_term_excludes_every_document(self):
        self.assert_urls("galaxy qzxnonexistent")


if __name__ == "__main__":
    unittest.main()
