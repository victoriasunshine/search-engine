# stems query, looks  up postings
from indexer.tokenizer import tokenize, stem


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