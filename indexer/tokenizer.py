# alphanumeric tokens + porter stemming

from nltk.stem import PorterStemmer

stemmer = PorterStemmer()


def tokenize(text):
    tokens = []
    current_token = []

    for character in text.lower():
        if character.isalnum():
            current_token.append(character)
        else:
            if current_token:
                tokens.append("".join(current_token))
                current_token = []

    if current_token:
        tokens.append("".join(current_token))

    return tokens


def count_terms(text):
    counts = {}
    tokens = tokenize(text)

    for token in tokens:
        term = stemmer.stem(token)

        if term in counts:
            counts[term] = counts[term] + 1
        else:
            counts[term] = 1

    return counts