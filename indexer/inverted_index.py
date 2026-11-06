class InvertedIndex:
    '''Builds inverted index:term -> list of postings
    (doc_id, frequency, important_frequency)'''

    def __init__(self):
        self.index = {}
        self.doc_urls = {}
        self.seen_urls = set()
        self.next_doc_id = 0

