import unittest

from search.query import query_terms, boolean_and, search


class QueryTests(unittest.TestCase):

    def test_empty_query(self):
        self.assertEqual(query_terms(""), [])

    def test_only_separators(self):
        self.assertEqual(query_terms("   !!! "), [])

    def test_repeated_words(self):
        self.assertEqual(query_terms("Cats CAT cats"), ["cat"])

    def test_lowercase_and_stemming(self):
        self.assertEqual(
            query_terms("MACHINE learning"),
            ["machin", "learn"]
        )


class BooleanTests(unittest.TestCase):

    def setUp(self):
        self.cat = {1: (2, 0), 3: (1, 0)}
        self.dog = {2: (1, 0), 3: (2, 0)}
        self.fish = {3: (1, 0), 4: (2, 0)}

    def test_no_lists(self):
        self.assertEqual(boolean_and([]), [])

    def test_missing_word(self):
        self.assertEqual(boolean_and([self.cat, {}]), [])

    def test_one_word(self):
        results = boolean_and([self.cat])
        self.assertEqual(sorted(results), [1, 3])

    def test_two_words(self):
        self.assertEqual(
            boolean_and([self.cat, self.dog]),
            [3]
        )

    def test_reverse_order(self):
        self.assertEqual(
            boolean_and([self.dog, self.cat]),
            [3]
        )

    def test_three_words(self):
        self.assertEqual(
            boolean_and([self.cat, self.dog, self.fish]),
            [3]
        )

    def test_no_common_documents(self):
        first = {1: (1, 0)}
        second = {2: (1, 0)}

        self.assertEqual(boolean_and([first, second]), [])

class TestReader:

    def __init__(self):
        self.doc_urls = {
            1: "https://example.org/cat",
            2: "https://example.org/dog",
            3: "https://example.org/both"
        }

        self.total_docs = 3
        self.doc_lengths = {1: 1.0, 2: 1.0, 3: 1.0}
        self.average_length = 1.0

    def get_postings(self, term):
        if term == "cat":
            return {1: (2, 0), 3: (1, 0)}

        if term == "dog":
            return {2: (1, 0), 3: (2, 0)}

        return {}


class SearchTests(unittest.TestCase):

    def setUp(self):
        self.reader = TestReader()

    def test_both_words(self):
        results = search(self.reader, "Cats dogs")

        self.assertEqual(
            results,
            ["https://example.org/both"]
        )

    def test_one_word(self):
        results = search(self.reader, "Cats")

        self.assertCountEqual(
            results,
            [
                "https://example.org/cat",
                "https://example.org/both"
            ]
        )

    def test_missing_word(self):
        results = search(self.reader, "Cats elephant")
        self.assertEqual(results, [])

    def test_empty_query(self):
        results = search(self.reader, "")
        self.assertEqual(results, [])

    def test_repeated_words(self):
        results = search(self.reader, "Cats cats dogs")

        self.assertEqual(
            results,
            ["https://example.org/both"]
        )

    def test_result_limit(self):
        results = search(self.reader, "Cats", top_k=1)
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()