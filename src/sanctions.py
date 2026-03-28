# src/sanctions.py
# Sanctions Entity Resolution System
# Building a hybrid name matching pipeline
#
# WHY THIS FILE EXISTS:
# Simple string matching fails for sanctions screening because
# the same person's name has no canonical spelling across languages.
# We need algorithms that measure HOW DIFFERENT two strings are,
# not just WHETHER they are identical.
#
# ALGORITHMS IMPLEMENTED:
# A) Exact matching      — baseline, always fails in practice
# B) Levenshtein         — character edit distance
# C) Soundex phonetic    — sound-based matching
# D) N-gram / Jaccard    — character chunk overlap
# E) Vector embeddings   — semantic similarity


# ============================================================
# IMPORTS
# ============================================================
# WHY AT THE TOP:
# All imports go at the top of the file by Python convention.
# This makes it immediately clear what libraries this file needs.
# Anyone reading the file knows the dependencies in 5 seconds.

from sentence_transformers import SentenceTransformer
import numpy as np

# Load embedding model once at startup
# WHY ONCE: loading takes ~2 seconds
# If loaded inside a function, it reloads on every comparison
# At module level it loads once and stays in memory
print("Loading embedding model...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model loaded.")


# ============================================================
# ALGORITHM A — EXACT MATCHING
# ============================================================
# What it does: checks if two strings are identical
# When it works: never reliable for cross-source name matching
# When it fails: any transliteration, typo, or formatting difference

def exact_match(name1, name2):
    """
    Returns True only if names are exactly identical
    after lowercasing and stripping whitespace.

    WHY LOWERCASE:
    "OSAMA BIN LADEN" and "osama bin laden" are the same person.
    Capitalisation differences come from different data entry
    conventions across OFAC, UN, and EU lists.

    WHY STRIP:
    Removes accidental spaces from start/end of string.
    Real data often has extra spaces from data entry.
    """
    return name1.lower().strip() == name2.lower().strip()


# ============================================================
# ALGORITHM B — LEVENSHTEIN DISTANCE
# ============================================================
# What it does: counts minimum edits to turn string A into string B
# When it works: names differing by 1-3 characters (transliteration)
# When it fails: reordered name tokens ("Bin Laden Osama" vs "Osama Bin Laden")

def levenshtein_distance(s1, s2):
    """
    Returns the number of single-character edits needed
    to transform s1 into s2.

    Three allowed operations:
    - Substitute: change one character to another
    - Insert: add a character
    - Delete: remove a character

    Uses Dynamic Programming — stores answers to subproblems
    in a 2D grid so we never recalculate the same thing twice.

    grid[i][j] = edit distance between
                 first i characters of s1
                 AND first j characters of s2
    """
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    rows = len(s1) + 1
    cols = len(s2) + 1

    # Build empty grid
    grid = []
    for i in range(rows):
        grid.append([0] * cols)

    # Base case: distance from empty string
    # First row: j insertions needed
    for j in range(cols):
        grid[0][j] = j

    # First column: i deletions needed
    for i in range(rows):
        grid[i][0] = i

    # Fill remaining cells
    for i in range(1, rows):
        for j in range(1, cols):
            if s1[i-1] == s2[j-1]:
                # Characters match — no operation needed
                grid[i][j] = grid[i-1][j-1]
            else:
                # Try all three operations, take cheapest
                substitute = grid[i-1][j-1] + 1
                delete     = grid[i-1][j]   + 1
                insert     = grid[i][j-1]   + 1
                grid[i][j] = min(substitute, delete, insert)

    return grid[rows-1][cols-1]


def levenshtein_similarity(s1, s2):
    """
    Converts raw edit distance into a similarity score
    between 0.0 and 1.0.

    WHY NORMALISE:
    Distance of 2 means different things for short vs long names.
    We divide by longest string length to make scores comparable.

    Score of 1.0 = identical
    Score of 0.0 = completely different
    """
    distance   = levenshtein_distance(s1, s2)
    max_length = max(len(s1), len(s2))

    if max_length == 0:
        return 1.0

    return 1.0 - (distance / max_length)


# ============================================================
# ALGORITHM C — PHONETIC MATCHING (SOUNDEX)
# ============================================================
# What it does: converts names to a sound-based code
#               names that sound alike get the same code
# When it works: transliterated names, spelling variants
# When it fails: very different languages for same name

def soundex(name):
    """
    Converts a name to its Soundex code — a 4-character
    representation of how the name sounds.

    WHY SOUNDEX:
    Levenshtein compares spelling character by character.
    Soundex compares sound — how the name is pronounced.
    Muhammad and Mohammed sound identical — Soundex catches this
    even when Levenshtein gives a borderline score.

    Rules:
    1. Keep first letter
    2. Remove vowels after first letter
    3. Replace consonants with sound-group numbers
    4. Keep exactly 4 characters, pad with zeros
    """
    if not name:
        return ""

    name = name.upper()
    name = ''.join(char for char in name if char.isalpha())

    if not name:
        return ""

    first_letter = name[0]

    # Sound group mapping
    # Letters that sound similar map to same digit
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2',
        'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
    }

    encoded  = first_letter
    prev_code = mapping.get(first_letter, '0')

    for char in name[1:]:
        code = mapping.get(char, '0')

        if code == '0':
            prev_code = '0'
            continue

        if code != prev_code:
            encoded += code

        prev_code = code

    # Pad or trim to exactly 4 characters
    encoded = encoded[:4].ljust(4, '0')

    return encoded


def phonetic_similarity(name1, name2):
    """
    Compares two names phonetically using Soundex codes.

    Returns:
    1.0 — identical sound codes
    0.8 — same numeric pattern, different first letter
          (common in Arabic transliteration: U vs O in Usama/Osama)
    0.0 to 0.75 — partial match based on shared code positions
    """
    code1 = soundex(name1)
    code2 = soundex(name2)

    if not code1 or not code2:
        return 0.0

    if code1 == code2:
        return 1.0

    # Same numeric pattern, different first letter
    if code1[1:] == code2[1:]:
        return 0.8

    # Partial match
    matches = sum(c1 == c2 for c1, c2 in zip(code1, code2))
    return matches / 4.0


# ============================================================
# ALGORITHM D — N-GRAM SIMILARITY (JACCARD)
# ============================================================
# What it does: splits names into character chunks
#               measures overlap between two sets of chunks
# When it works: reordered tokens, partial name matches
# When it fails: very short names (Ali → only 1 trigram)

def get_ngrams(text, n=3):
    """
    Splits a string into overlapping chunks of n characters.

    WHY N-GRAMS:
    "Bin Laden" and "Laden Bin" share the same character
    chunks regardless of word order.

    WHY n=3 (trigrams):
    n=2 too short — appears in many unrelated names
    n=3 balanced — specific enough, flexible enough
    n=4 too strict — one spelling difference kills the match

    WHY SET not LIST:
    Sets automatically remove duplicates.
    Order does not matter for overlap calculation.
    """
    text = text.lower().strip()
    text = text.replace(" ", "")

    if len(text) < n:
        return {text}

    ngrams = set()
    for i in range(len(text) - n + 1):
        ngram = text[i:i+n]
        ngrams.add(ngram)

    return ngrams


def jaccard_similarity(name1, name2, n=3):
    """
    Measures overlap between two names using Jaccard formula.

    Jaccard = shared ngrams / total unique ngrams

    WHY JACCARD:
    Normalises by total unique ngrams — longer names
    with more ngrams don't automatically score higher.
    """
    ngrams1 = get_ngrams(name1, n)
    ngrams2 = get_ngrams(name2, n)

    if not ngrams1 or not ngrams2:
        return 0.0

    intersection = ngrams1 & ngrams2   # shared chunks
    union        = ngrams1 | ngrams2   # all unique chunks

    return len(intersection) / len(union)


def token_overlap_similarity(name1, name2):
    """
    Splits names into words and measures word-level overlap.

    WHY TOKEN OVERLAP IN ADDITION TO N-GRAMS:
    N-grams work at character level.
    Token overlap works at word level.

    "Bin Laden" vs "Laden Bin":
    Token overlap: {"bin","laden"} vs {"laden","bin"}
    → 2 shared / 2 union = 1.00 — perfect score

    Handles word reordering perfectly.
    """
    tokens1 = set(name1.lower().strip().split())
    tokens2 = set(name2.lower().strip().split())

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union        = tokens1 | tokens2

    return len(intersection) / len(union)


# ============================================================
# ALGORITHM E — VECTOR EMBEDDINGS (SEMANTIC SIMILARITY)
# ============================================================
# What it does: converts names into vectors of numbers
#               representing their meaning in semantic space
# When it works: names with similar context/meaning
# When it fails: unknown aliases with no semantic connection

def get_embedding(text):
    """
    Converts a name into a vector of 384 numbers.

    Each number represents one dimension of meaning.
    Together they place the name at a specific point
    in a 384-dimensional meaning space.
    """
    return embedding_model.encode(text)


def cosine_similarity_score(vec1, vec2):
    """
    Measures the angle between two vectors.

    Small angle = similar meaning = high score
    Large angle = different meaning = low score

    WHY COSINE NOT EUCLIDEAN DISTANCE:
    Cosine measures direction not magnitude.
    Text vectors can have different lengths but same meaning.
    Cosine similarity correctly ignores magnitude differences.

    Formula: cos(θ) = (A · B) / (|A| × |B|)
    """
    dot_product = np.dot(vec1, vec2)
    norm1       = np.linalg.norm(vec1)
    norm2       = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def embedding_similarity(name1, name2):
    """
    Full pipeline: name → vector → cosine similarity score.
    Returns score between 0.0 and 1.0.
    """
    vec1  = get_embedding(name1)
    vec2  = get_embedding(name2)
    score = cosine_similarity_score(vec1, vec2)

    # Clip to clean range — floating point can produce 1.0000002
    return float(np.clip(score, 0.0, 1.0))


# ============================================================
# MAIN — RUN ALL TESTS
# ============================================================
# WHY if __name__ == "__main__":
# This block runs ONLY when we run this file directly.
# When another file imports our functions, this block is skipped.
# Without this guard, test output would print on every import.

if __name__ == "__main__":

    # --------------------------------------------------------
    # ALGORITHM A — EXACT MATCHING TESTS
    # --------------------------------------------------------
    print("=" * 55)
    print("EXACT MATCHING TESTS")
    print("=" * 55)

    print(exact_match("Osama Bin Laden", "Osama Bin Laden"))
    print(exact_match("Osama Bin Laden", "osama bin laden"))
    print(exact_match("Osama Bin Laden", "Usama Bin Ladin"))
    print(exact_match("Abdul Rahman",    "Abdel Rahman"))

    # --------------------------------------------------------
    # ALGORITHM B — LEVENSHTEIN TESTS
    # --------------------------------------------------------
    print()
    print("=" * 55)
    print("LEVENSHTEIN DISTANCE TESTS")
    print("=" * 55)

    lev_pairs = [
        ("Abdul Rahman",    "Abdel Rahman"),
        ("Usama Bin Laden", "Osama Bin Ladin"),
        ("Moammar Gadhafi", "Muammar Gaddafi"),
        ("Ali Khan",        "Ali Khan"),
        ("Ali Khan",        "Ahmed Khan"),
    ]

    for name1, name2 in lev_pairs:
        distance   = levenshtein_distance(name1, name2)
        similarity = levenshtein_similarity(name1, name2)
        print(f"{name1:20} vs {name2:20} → distance: {distance}  similarity: {similarity:.2f}")

    # --------------------------------------------------------
    # ALGORITHM C — PHONETIC TESTS
    # --------------------------------------------------------
    print()
    print("=" * 55)
    print("PHONETIC MATCHING TESTS")
    print("=" * 55)

    phonetic_pairs = [
        ("Usama",    "Osama"),
        ("Muhammad", "Mohammed"),
        ("Moammar",  "Muammar"),
        ("Smith",    "Smyth"),
        ("Ali",      "Ali"),
        ("Ali",      "Ahmed"),
    ]

    for name1, name2 in phonetic_pairs:
        code1 = soundex(name1)
        code2 = soundex(name2)
        score = phonetic_similarity(name1, name2)
        print(f"{name1:12} → {code1}  |  {name2:12} → {code2}  |  similarity: {score:.2f}")

    # --------------------------------------------------------
    # ALGORITHM D — N-GRAM TESTS
    # --------------------------------------------------------
    print()
    print("=" * 55)
    print("N-GRAM AND TOKEN OVERLAP TESTS")
    print("=" * 55)

    ngram_pairs = [
        ("Bin Laden",       "Laden Bin"),
        ("Osama Bin Laden", "Laden Bin Osama"),
        ("Rahman",          "Rehman"),
        ("Abdul Rahman",    "Abdel Rahman"),
        ("Ali Khan",        "Ahmed Khan"),
    ]

    for name1, name2 in ngram_pairs:
        jaccard = jaccard_similarity(name1, name2)
        token   = token_overlap_similarity(name1, name2)
        print(f"{name1:20} vs {name2:20}")
        print(f"  Jaccard(trigram): {jaccard:.2f}  |  Token overlap: {token:.2f}")
        print()

    # --------------------------------------------------------
    # ALGORITHM E — VECTOR EMBEDDING TESTS
    # --------------------------------------------------------
    print()
    print("=" * 55)
    print("VECTOR EMBEDDING TESTS")
    print("=" * 55)

    embedding_pairs = [
        ("Osama Bin Laden",  "Usama Bin Ladin"),
        ("Muhammad",         "Mohammed"),
        ("Abdul Rahman",     "Abdel Rahman"),
        ("Osama",            "The Ghost"),
        ("Ali Khan",         "Ahmed Khan"),
        ("Osama Bin Laden",  "Apple Juice"),
    ]

    for name1, name2 in embedding_pairs:
        score = embedding_similarity(name1, name2)
        print(f"{name1:25} vs {name2:25} → similarity: {score:.2f}")