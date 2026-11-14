import math

# Each occurrence of a term in important text (title, h1-h3, b, strong)
# counts this many EXTRA times. Important text is also part of the full
# text, so with a boost of 2 an important occurrence counts 3 times total.
IMPORTANT_BOOST = 2


def doc_term_weight(tf, important_tf):
    """Document-side weight of one term (log-scaled boosted frequency)."""
    boosted = tf + IMPORTANT_BOOST * important_tf
    return 1 + math.log10(boosted)


def doc_length(term_counts, important_counts):
    """Euclidean length of a document's weight vector, used to normalize
    scores so long pages don't win just because they have more words."""
    total = 0.0
    for term, tf in term_counts.items():
        weight = doc_term_weight(tf, important_counts.get(term, 0))
        total += weight * weight
    return math.sqrt(total)


def idf(doc_freq, total_docs):
    """Inverse document frequency: rare terms count more than common ones."""
    return math.log10(total_docs / doc_freq)


# Pivoted length normalization. Plain cosine (divide by the page's length)
# over-rewards very short pages, e.g. image-detail and slide pages. Instead
# divide by a mix of the page's length and the average length:
#   pivot = (1 - SLOPE) * average length + SLOPE * page length
# SLOPE = 1 is plain cosine; smaller values move long and short pages toward
# the average. 0.3 gave the best top 5 on the four Milestone 2 queries.
PIVOT_SLOPE = 0.3


def pivoted_length(length, average_length):
    """The number a page's score is divided by (see PIVOT_SLOPE)."""
    return (1 - PIVOT_SLOPE) * average_length + PIVOT_SLOPE * length
