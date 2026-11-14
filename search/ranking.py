# tf-idf + boost for important words
import heapq
import math
from indexer.weighting import doc_term_weight, idf, pivoted_length

# How much a match in title / headings / bold counts, on top of a normal match.
IMPORTANT_WEIGHT = 1.0


def tf_weight(count):
    "log-scaled term frequency: 1 + log10(tf), or 0 if the word is absent"
    if count <= 0:
        return 0.0
    return 1 + math.log10(count)


def rank(doc_ids, postings_lists, total_docs, doc_lengths, average_length, top_k=5):
    """Score each matching page and return the top_k doc ids, best first.

    score(page) = sum over query terms of
        idf * (tf_weight(tf) + IMPORTANT_WEIGHT * tf_weight(important_tf))
    idf = log10(N / df), where df = number of pages that contain the term.
    """
    idfs = [idf(len(postings), total_docs) for postings in postings_lists]
    scores = {}
    for doc_id in doc_ids:
        score = 0.0
        for term_idf, postings in zip(idfs, postings_lists):
            tf, important_tf = postings[doc_id]
            score += term_idf * doc_term_weight(tf, important_tf)
        scores[doc_id] = score / pivoted_length(doc_lengths[doc_id], average_length)

    # Only the top_k pages are needed, so skip sorting every match.
    # Ties go to the smaller doc id, so results are the same every run.
    return heapq.nsmallest(top_k, scores, key=lambda d: (-scores[d], d))
