class InvertedIndex:
    '''Builds inverted index:term -> list of postings
    (doc_id, frequency, important_frequency)'''

    def __init__(self):
        self.index = {}
        self.doc_urls = {}
        self.seen_urls = set()
        self.next_doc_id = 0

    def add_document(self, url,term_counts, important_count=None):
        """give page a doc Id and add one posting per term """

        if url in self.seen_urls:
            return None
        self.seen_urls.add(url)

        doc_id = self.next_doc_id
        self.next_doc_id += 1
        self.doc_urls[doc_id] = url

        if important_count is None:
            important_count = {}

        # How many times in importnat text
        for term, count in term_counts.items():
            if term not in self.index:
                self.index[term] = []
            important = important_count.get(term, 0)
            self.index[term].append((doc_id, count, important))

        return doc_id