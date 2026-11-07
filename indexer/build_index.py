# write partial indexes to disk, then merge
"""Build the inverted index from the corpus (Milestone 1).

Run from the repo root:
    python3 -m indexer.build_index ~/ir-data/DEV index/dev

For every page (document_parser streams one page at a time):
    parse HTML -> stem + count terms (full text and important text)
    -> add postings (doc_id, tf, important_tf) to the in-memory index
    -> when memory holds MAX_POSTINGS postings, offload a partial index to disk
Then the partial indexes are merged into the final index:
    postings.txt   term<TAB>doc,tf,imp doc,tf,imp ...   (one line per term)
    lexicon.tsv    term<TAB>df<TAB>byte offset<TAB>byte length in postings.txt
    seek.json      every 64th lexicon term + its byte offset in lexicon.tsv
    docs.tsv       doc_id<TAB>url
    meta.json      the Milestone 1 numbers
"""

import argparse
import heapq
import json
import os
import shutil
import time

from document_parser import iter_documents
from indexer.inverted_index import InvertedIndex
from indexer.tokenizer import count_terms

# Offload the in-memory index after this many postings. On the developer
# corpus this gives several partial indexes (the spec requires at least 3).
MAX_POSTINGS = 2_000_000

# Store every SEEK_EVERY-th lexicon term in seek.json (an index of the index),
# so search can find a term without loading the whole lexicon.
SEEK_EVERY = 64


def build(corpus, out_dir, max_postings=MAX_POSTINGS):
    start = time.time()
    partial_dir = os.path.join(out_dir, "partials")
    os.makedirs(partial_dir, exist_ok=True)

    index = InvertedIndex()
    partial_paths = []
    postings_in_memory = 0
    pages_read = skipped_empty = skipped_repeat = 0

    def offload():
        """Write the in-memory postings to the next partial file, then clear."""
        nonlocal postings_in_memory
        path = os.path.join(partial_dir, "partial_%03d.txt" % len(partial_paths))
        index.write_partial(path)
        partial_paths.append(path)
        index.clear_postings()
        postings_in_memory = 0
        print("  offloaded partial index %d (%d docs so far)"
              % (len(partial_paths), index.next_doc_id))

    with open(os.path.join(out_dir, "docs.tsv"), "w", encoding="utf-8") as docs_file:
        for doc in iter_documents(corpus):
            pages_read += 1
            if doc.url in index.seen_urls:      # same URL (fragment removed) again
                skipped_repeat += 1
                continue

            term_counts = count_terms(doc.text)
            if not term_counts:                  # no words at all: nothing to index
                skipped_empty += 1
                continue
            # Counts inside title / headings / bold, for ranking later.
            important_counts = count_terms(doc.important_text)

            doc_id = index.add_document(doc.url, term_counts, important_counts)
            docs_file.write("%d\t%s\n" % (doc_id, doc.url))

            postings_in_memory += len(term_counts)
            if postings_in_memory >= max_postings:
                offload()

            if pages_read % 5000 == 0:
                print("  read %d pages (%.0fs)" % (pages_read, time.time() - start))

    if postings_in_memory:
        offload()

    unique_terms = merge(partial_paths, out_dir)
    shutil.rmtree(partial_dir)

    size = sum(os.path.getsize(os.path.join(out_dir, f))
               for f in ("postings.txt", "lexicon.tsv", "seek.json", "docs.tsv"))
    stats = {
        "documents": index.next_doc_id,
        "unique_tokens": unique_terms,
        "index_size_kb": round(size / 1024),
        "postings_file_kb": round(os.path.getsize(os.path.join(out_dir, "postings.txt")) / 1024),
        "partial_indexes": len(partial_paths),
        "pages_read": pages_read,
        "skipped_empty": skipped_empty,
        "skipped_repeated_url": skipped_repeat,
        "build_seconds": round(time.time() - start),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as meta:
        json.dump(stats, meta, indent=2)
    return stats


def read_partial(path, part_no):
    """Yield (term, part_no, postings) from one partial index file, in order."""
    with open(path, encoding="utf-8") as partial:
        for line in partial:
            term, postings = line.rstrip("\n").split("\t", 1)
            yield term, part_no, postings


def merge(partial_paths, out_dir):
    """K-way merge of the sorted partial files into the final index.

    heapq.merge always yields the smallest term among all files next, so each
    term's postings from every partial come out together. Each partial holds
    higher doc ids than the one before it, so joining them in part_no order
    keeps every postings list sorted by doc id. Only one line per partial
    file is in memory at a time. Returns the number of unique terms."""
    streams = [read_partial(path, n) for n, path in enumerate(partial_paths)]
    seek = []
    unique_terms = 0

    with open(os.path.join(out_dir, "postings.txt"), "wb") as postings_out, \
            open(os.path.join(out_dir, "lexicon.tsv"), "wb") as lexicon_out:

        def write_term(term, chunks):
            nonlocal unique_terms
            joined = " ".join(chunks)
            doc_freq = joined.count(" ") + 1
            line = (term + "\t" + joined + "\n").encode("utf-8")
            offset = postings_out.tell()
            postings_out.write(line)
            if unique_terms % SEEK_EVERY == 0:
                seek.append([term, lexicon_out.tell()])
            lexicon_out.write(("%s\t%d\t%d\t%d\n" % (term, doc_freq, offset, len(line)))
                              .encode("utf-8"))
            unique_terms += 1

        current_term, chunks = None, []
        for term, _, postings in heapq.merge(*streams):
            if term != current_term:
                if current_term is not None:
                    write_term(current_term, chunks)
                current_term, chunks = term, []
            chunks.append(postings)
        if current_term is not None:
            write_term(current_term, chunks)

    with open(os.path.join(out_dir, "seek.json"), "w", encoding="utf-8") as seek_out:
        json.dump(seek, seek_out, ensure_ascii=False)
    return unique_terms


def main():
    parser = argparse.ArgumentParser(description="Build the inverted index.")
    parser.add_argument("corpus", help="corpus folder (e.g. ~/ir-data/DEV) or .zip")
    parser.add_argument("out_dir", help="where to write the index (e.g. index/dev)")
    parser.add_argument("--max-postings", type=int, default=MAX_POSTINGS,
                        help="offload a partial index after this many postings")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    stats = build(os.path.expanduser(args.corpus), args.out_dir, args.max_postings)

    print("\nMilestone 1 numbers")
    print("  Documents:           %d" % stats["documents"])
    print("  Unique tokens:       %d" % stats["unique_tokens"])
    print("  Index size on disk:  %d KB" % stats["index_size_kb"])
    print("  Partial indexes:     %d" % stats["partial_indexes"])
    print("  Skipped: %d empty, %d repeated URL"
          % (stats["skipped_empty"], stats["skipped_repeated_url"]))
    print("  Build time:          %ds" % stats["build_seconds"])
    if stats["partial_indexes"] < 3:
        print("  WARNING: fewer than 3 partial indexes; lower --max-postings")


if __name__ == "__main__":
    main()
