import bisect
import json
import os

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
        with open(os.path.join(index_dir, "docs.tsv"), encoding = "utf-8") as f:
            for line in f: #read line at a time
                doc_id, url = line.rstrip("\n").split("\t", 1) #remove newline and split first tab into ID/URL
                self.doc_urls[int(doc_id)] = url

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




