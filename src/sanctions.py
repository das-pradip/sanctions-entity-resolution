# src/sanctions.py
# Phase 2 — Algorithm A: Exact Matching
# Phase 2 — Algorithm B: Levenshtein Distance
#
# WHY THIS FILE EXISTS:
# Simple string matching fails for sanctions screening because
# the same person's name has no canonical spelling across languages.
# We need algorithms that measure HOW DIFFERENT two strings are,
# not just WHETHER they are identical.


# ============================================================
# ALGORITHM A — EXACT MATCHING
# ============================================================
# What it does: checks if two strings are identical
# When it works: never reliable for cross-source name matching
# When it fails: any transliteration, typo, or formatting difference

def exact_match(name1, name2):
    """
    Returns True only if names are exactly identical
    after lowercasing.
    
    WHY WE LOWERCASE:
    "OSAMA BIN LADEN" and "osama bin laden" are the same person.
    Capitalisation differences come from different data entry
    conventions across OFAC, UN, and EU lists.
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
    
    WHY WE BUILD THIS:
    "Abdul Rahman" vs "Abdel Rahman" = distance of 1
    One character difference. Exact match says False.
    Levenshtein says 1 — almost identical.
    """
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    # Create a grid of size (len(s1)+1) x (len(s2)+1)
    # Each cell will store the edit distance between
    # the first i characters of s1 and first j characters of s2
    rows = len(s1) + 1
    cols = len(s2) + 1

    # Build the grid filled with zeros
    grid = []
    for i in range(rows):
        grid.append([0] * cols)

    # First row: distance from empty string to s2[:j]
    # requires j insertions
    for j in range(cols):
        grid[0][j] = j

    # First column: distance from s1[:i] to empty string
    # requires i deletions
    for i in range(rows):
        grid[i][0] = i

    # Fill in the rest of the grid
    for i in range(1, rows):
        for j in range(1, cols):
            if s1[i-1] == s2[j-1]:
                # Characters match — no operation needed
                grid[i][j] = grid[i-1][j-1]
            else:
                # Characters differ — take minimum of 3 operations
                substitute = grid[i-1][j-1] + 1  # change one char
                delete     = grid[i-1][j]   + 1  # delete from s1
                insert     = grid[i][j-1]   + 1  # insert into s1
                grid[i][j] = min(substitute, delete, insert)

    # Bottom-right cell contains the final answer
    return grid[rows-1][cols-1]


def levenshtein_similarity(s1, s2):
    """
    Converts raw edit distance into a similarity score
    between 0.0 and 1.0.

    WHY WE NORMALISE:
    Raw distance of 2 means different things for:
    - "Ali" vs "Eli"       (short names, very different)
    - "Muhammad" vs "Mohammed" (long names, quite similar)
    We divide by the longest string length to make scores comparable.

    Score of 1.0 = identical
    Score of 0.0 = completely different
    """
    distance = levenshtein_distance(s1, s2)
    max_length = max(len(s1), len(s2))

    if max_length == 0:
        return 1.0

    return 1.0 - (distance / max_length)


# ============================================================
# TEST IT — run this file directly to see results
# ============================================================

if __name__ == "__main__":

    print("=" * 55)
    print("EXACT MATCHING TESTS")
    print("=" * 55)

    print(exact_match("Osama Bin Laden", "Osama Bin Laden"))   # True
    print(exact_match("Osama Bin Laden", "osama bin laden"))   # True
    print(exact_match("Osama Bin Laden", "Usama Bin Ladin"))   # False
    print(exact_match("Abdul Rahman",    "Abdel Rahman"))      # False

    print()
    print("=" * 55)
    print("LEVENSHTEIN DISTANCE TESTS")
    print("=" * 55)

    pairs = [
        ("Abdul Rahman",    "Abdel Rahman"),
        ("Usama Bin Laden", "Osama Bin Ladin"),
        ("Moammar Gadhafi", "Muammar Gaddafi"),
        ("Ali Khan",        "Ali Khan"),
        ("Ali Khan",        "Ahmed Khan"),
    ]

    for name1, name2 in pairs:
        distance   = levenshtein_distance(name1, name2)
        similarity = levenshtein_similarity(name1, name2)
        print(f"{name1:20} vs {name2:20} → distance: {distance}  similarity: {similarity:.2f}")