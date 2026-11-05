
import re
import sqlite3
from threading import RLock

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
MASK = (1 << 64) - 1


def tokens(text):
    return TOKEN_RE.findall(text.lower())


def stable_hash(value):
    """FNV-1a 64-bit, implemented directly (stable across Python processes)."""
    result = 14695981039346656037
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 1099511628211) & MASK
    return result


def simhash(word_list):
    """Frequency-weighted word fingerprint; each word votes on all 64 bits."""
    counts = {}
    for word in word_list:
        counts[word] = counts.get(word, 0) + 1
    votes = [0] * 64
    for word, frequency in counts.items():
        hashed = stable_hash(word)
        for bit in range(64):
            votes[bit] += frequency if hashed & (1 << bit) else -frequency
    result = 0
    for bit, vote in enumerate(votes):
        if vote > 0:
            result |= 1 << bit
    return result


def hamming_distance(left, right):
    difference = left ^ right
    distance = 0
    while difference:
        difference &= difference - 1
        distance += 1
    return distance


class DuplicateDetector:
    """Persistent, process-local thread-safe check-and-add operation.

    Four 16-bit bands guarantee a candidate match for distance <= 3: at least
    one band must be unchanged. Candidates still get a full Hamming comparison.
    Near matches must also have word counts within 10% to reduce false positives.
    Only unique representatives are stored, preventing chains of similarity
    from gradually drifting far from an original page.
    """

    def __init__(self, state_path="crawler_similarity.sqlite3", threshold=3):
        if not 0 <= threshold <= 3:
            raise ValueError("four-band indexing supports thresholds from 0 to 3")
        self.threshold = threshold
        self.lock = RLock()
        self.db = sqlite3.connect(state_path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS similarity_pages ("
                        "id INTEGER PRIMARY KEY, digest TEXT NOT NULL, "
                        "normalized TEXT NOT NULL, fingerprint TEXT NOT NULL, "
                        "words INTEGER NOT NULL, b0 INTEGER, b1 INTEGER, "
                        "b2 INTEGER, b3 INTEGER)")
        self.db.execute("CREATE INDEX IF NOT EXISTS similarity_digest "
                        "ON similarity_pages(digest)")
        for band in range(4):
            self.db.execute("CREATE INDEX IF NOT EXISTS similarity_band%d "
                            "ON similarity_pages(b%d)" % (band, band))
        self.db.commit()

    def check_and_add(self, text):
        """Return 'exact', 'near', or None (new page); empty text isn't stored.

        Exact means equal normalized tokens, not byte-identical HTML. Store the
        normalized text too, so a hash collision cannot cause an exact match.
        """
        words = tokens(text)
        if not words:
            return None
        normalized = " ".join(words)
        digest = format(stable_hash(normalized), "016x")
        fingerprint = simhash(words)
        bands = [(fingerprint >> (16 * band)) & 65535 for band in range(4)]
        with self.lock, self.db:
            for (old_text,) in self.db.execute(
                    "SELECT normalized FROM similarity_pages WHERE digest=?", (digest,)):
                if old_text == normalized:
                    return "exact"
            candidates = self.db.execute(
                "SELECT fingerprint, words FROM similarity_pages "
                "WHERE b0=? OR b1=? OR b2=? OR b3=?", bands)
            for old_fingerprint, count in candidates:
                length_ratio = min(count, len(words)) / max(count, len(words))
                if (length_ratio >= 0.9 and hamming_distance(
                        fingerprint, int(old_fingerprint, 16)) <= self.threshold):
                    return "near"
            self.db.execute(
                "INSERT INTO similarity_pages "
                "(digest, normalized, fingerprint, words, b0, b1, b2, b3) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (digest, normalized, format(fingerprint, "016x"), len(words), *bands))
        return None

    def close(self):
        with self.lock:
            self.db.close()
