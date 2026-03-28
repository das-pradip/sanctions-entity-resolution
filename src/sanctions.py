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





# ============================================================
# ALGORITHM C — PHONETIC MATCHING (SOUNDEX)
# ============================================================
# What it does: converts names to a sound-based code
#               names that sound alike get the same code
# When it works: transliterated names, spelling variants
#               "Usama" and "Osama" → both encode to same sound
# When it fails: very different languages for same name
#               "Yusuf" and "Joseph" — different sounds entirely

def soundex(name):
    """
    Converts a name to its Soundex code.
    
    WHY SOUNDEX:
    Levenshtein compares spelling character by character.
    Soundex compares sound — how the name is pronounced.
    A bank clerk might spell "Muhammad" as "Mohammed" but
    both names sound identical when spoken aloud.
    Soundex catches these variants that Levenshtein misses.
    
    Returns a 4-character code like "M530"
    """
    
    # Step 1: Handle empty input
    if not name:
        return ""
    
    # Step 2: Uppercase and keep only letters
    # WHY: Soundex works on letters only
    #      We uppercase so our mapping works consistently
    name = name.upper()
    
    # Keep only alphabetic characters
    # WHY: hyphens, spaces, numbers should not affect sound code
    name = ''.join(char for char in name if char.isalpha())
    
    if not name:
        return ""
    
    # Step 3: Save the first letter
    # WHY: Soundex always keeps the first letter unchanged
    first_letter = name[0]
    
    # Step 4: Define the sound mapping
    # WHY: Letters that sound similar map to the same digit
    #      B and P sound similar → both map to 1
    #      M and N are nasal sounds → both map to 5
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2',
        'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
        # Vowels A E I O U and H W Y are NOT in mapping
        # WHY: vowels and these consonants are ignored
        #      they don't contribute to the core sound
    }
    
    # Step 5: Convert remaining letters using mapping
    # WHY: We skip the first letter here — it's already saved
    #      We only encode letters that have a mapping
    #      Vowels and H,W,Y are skipped entirely
    encoded = first_letter
    
    prev_code = mapping.get(first_letter, '0')
    
    for char in name[1:]:
        code = mapping.get(char, '0')
        
        if code == '0':
            # Vowel or ignored letter — skip it
            # but reset prev_code so next consonant is not skipped
            prev_code = '0'
            continue
            
        if code != prev_code:
            # Only add if different from previous code
            # WHY: "Lll" should not become "L444"
            #      Adjacent same sounds are one sound
            encoded += code
            
        prev_code = code
    
    # Step 6: Pad or trim to exactly 4 characters
    # WHY: Soundex is always exactly 4 characters
    #      Makes comparison simple and consistent
    encoded = encoded[:4].ljust(4, '0')
    
    return encoded


def phonetic_similarity(name1, name2):
    """
    Compares two names phonetically.
    
    Returns score between 0.0 and 1.0:
    1.0 = sound identical
    0.5 = first letter different but sound pattern same
    0.0 = completely different sounds
    
    WHY TWO LEVELS:
    "Usama" and "Osama" have same sound pattern but different
    first letters — due to transliteration of Arabic vowels.
    We give partial credit because this is extremely common
    in sanctions data.
    """
    code1 = soundex(name1)
    code2 = soundex(name2)
    
    if not code1 or not code2:
        return 0.0
    
    # Exact phonetic match
    if code1 == code2:
        return 1.0
    
    # Same numeric pattern, different first letter
    # WHY: Arabic/Persian names often transliterate first
    #      vowel differently — "U" vs "O" in Usama/Osama
    if code1[1:] == code2[1:]:
        return 0.8
    
    # Partially matching sound pattern
    matches = sum(c1 == c2 for c1, c2 in zip(code1, code2))
    return matches / 4.0


# ============================================================
# ADD THESE TESTS to your if __name__ == "__main__" block
# ============================================================

# Find this line in your file:
# if __name__ == "__main__":
# And ADD these lines at the bottom of that block:

print()
print("=" * 55)
print("PHONETIC MATCHING TESTS")
print("=" * 55)

phonetic_pairs = [
    ("Usama",     "Osama"),
    ("Muhammad",  "Mohammed"),
    ("Moammar",   "Muammar"),
    ("Smith",     "Smyth"),
    ("Ali",       "Ali"),
    ("Ali",       "Ahmed"),
]

for name1, name2 in phonetic_pairs:
    code1 = soundex(name1)
    code2 = soundex(name2)
    score = phonetic_similarity(name1, name2)
    print(f"{name1:12} → {code1}  |  {name2:12} → {code2}  |  similarity: {score:.2f}")