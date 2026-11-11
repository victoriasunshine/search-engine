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
