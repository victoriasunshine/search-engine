# stems query, looks  up postings
import bisect
import json
import os
from indexer.tokenizer import tokenize, stem
from search.ranking import rank



def query_terms(query):
    terms = []
    tokens = tokenize(query)

    for token in tokens:
        term = stem(token)

        if term not in terms:
            terms.append(term)

    return terms

def boolean_and(postings_lists):
    if not postings_lists:
        return []

    shortest = postings_lists[0]

    for postings in postings_lists:
        if len(postings) < len(shortest):
            shortest = postings

    results = []

    for doc_id in shortest:
        found_in_all = True

        for postings in postings_lists:
            if doc_id not in postings:
                found_in_all = False
                break

        if found_in_all:
            results.append(doc_id)

    return results


# Always find index/dev in the project folder, no matter where the code is run from
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_DIR = os.path.join(PROJECT_DIR, "index", "dev")
SEEK_EVERY = 64

class IndexReader:
    "reads postings from index on disk w/o loading postings.txt into memory"
    def __init__(self, index_dir = INDEX_DIR):
        # Build path, read the file into a list of pairs
        with open(os.path.join(index_dir, "seek.json"), encoding = "utf-8") as f:
            seek = json.load(f)

        #split the pairs into two lists that line up by postion
        self.seek_terms = [term for term, offset in seek]
        self.seek_offsets = [offset for term, offset in seek]

        # open files, do not read
        self.lexicon_file = open(os.path.join(index_dir, "lexicon.tsv"), "rb")
        self.postings_file = open(os.path.join(index_dir, "postings.txt"), "rb")

        # load the urls
        self.doc_urls = {} # empty dic
        self.doc_lengths = {} # doc_id -> vector length, for cosine
        with open(os.path.join(index_dir, "docs.tsv"), encoding = "utf-8") as f:
            for line in f: #read line at a time
                doc_id, url, length = line.rstrip("\n").split("\t") #remove newline and split into ID/URL/length
                self.doc_urls[int(doc_id)] = url
                self.doc_lengths[int(doc_id)] = float(length)
        self.average_length = sum(self.doc_lengths.values()) / max(len(self.doc_lengths), 1)

        #meta.json holds m1 numbers, grab page count
        with open(os.path.join(index_dir,"meta.json")) as f:
            self.total_docs = json.load(f)["documents"]

    def find_term(self,term):
        "Find word in the lexicon, returns doc_freq/offset/length or none"

        # find last shortcut word that comes at or before our word
        i = bisect.bisect_right(self.seek_terms,term) - 1
        if i < 0:
            return None

        #jump to where shortcut word line starts in lexicon.tsv
        self.lexicon_file.seek(self.seek_offsets[i])

        #Flip through at most 64 cards
        for _ in range(SEEK_EVERY):
            line = self.lexicon_file.readline()
            if not line:
                break #end reached

            word, doc_freq, offset, length = line.decode("utf-8").rstrip("\n").split("\t")
            if word == term:
                return int(doc_freq), int(offset), int(length) #found card
            if word > term:
                break #passed it

        return None

    def get_postings(self,term):
        "return a words posting as {doc_id: (tf, important_tf)}, or {}"

        # find words card, if not found return empty dict
        entry = self.find_term(term)
        if entry is None:
            return {}

        #unpack 3 numbers
        doc_freq, offset, length = entry

        #go to words line in postings.txt and read
        self.postings_file.seek(offset)
        line=self.postings_file.read(length).decode("utf-8")

        # line appears as word<TAB> 12, 3, 1,
        word,postings_text = line.rstrip("\n").split("\t", 1)

        postings = {}
        for posting in postings_text.split(" "):
            doc_id, tf, imp = posting.split(",")
            postings[int(doc_id)] = (int(tf), int(imp))
        return postings
    def close(self):
        "close the two index files left open for seeking"
        self.lexicon_file.close()
        self.postings_file.close()
        
def search(reader, query, top_k=5):
    "AND-match the query, rank the matches with tf-idf, return the top_k URLs"
    terms = query_terms(query)
    postings_lists = []

    for term in terms:
        postings = reader.get_postings(term)

        if not postings:
            return []

        postings_lists.append(postings)

    results = boolean_and(postings_lists)
    ranked = rank(results, postings_lists, reader.total_docs, 
                  reader.doc_lengths, reader.average_length, top_k)

    return [reader.doc_urls[doc_id] for doc_id in ranked]


# This test only runs when you run query.py directly
if __name__ == "__main__":
    import time  # used as a stopwatch to time each lookup

    # Create the reader: loads seek.json, docs.tsv, meta.json, and opens the big files
    reader = IndexReader()

    # Look up some words and time each one
    # Words are stemmed in the index ("machine" -> "machin", "lopes" -> "lope").
    # "zzznotaword" checks that a missing word returns 0 pages instead of crashing.
    for word in ["machin", "learn", "acm", "cristina", "lope", "zzznotaword"]:
        start = time.perf_counter()                    # start the stopwatch
        postings = reader.get_postings(word)
        ms = (time.perf_counter() - start) * 1000      # seconds -> milliseconds
        print(f"{word}: found on {len(postings)} pages ({ms:.2f} ms)")

    # Check a few results by hand: the first 3 pages that contain "acm",
    # with how often the word appears and the page's URL
    print()
    postings = reader.get_postings("acm")
    for doc_id in sorted(postings)[:3]:
        tf, imp = postings[doc_id]
        print(doc_id, "| tf:", tf, "| important:", imp, "|", reader.doc_urls[doc_id])