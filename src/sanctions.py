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
# COMBINED FEATURE VECTOR SCORER
# ============================================================
# This is the core of the sanctions matching system.
# It combines all five algorithms into one confidence score.
#
# WHY COMBINE:
# No single algorithm wins alone. Each covers blind spots
# of the others. The combined score is more reliable than
# any individual score.
#
# WHY WEIGHTED AVERAGE:
# Algorithms have different reliability levels.
# Token overlap and Levenshtein are more reliable
# than embeddings for sanctions name matching.
# Weights reflect this — embeddings get lowest weight.
#
# DESIGN DECISIONS:
# 1. Missing fields → NULL, excluded from average
#    not zeroed out (absence of evidence ≠ no match)
# 2. Weighted average over AVAILABLE fields only
# 3. DOB within ±2 years → full score
# 4. Country exact match → full score
# 5. Passport exact match → full score (strongest signal)

# Algorithm weights — must sum to 1.0
# These are starting weights — ML model will improve them later
NAME_ALGORITHM_WEIGHTS = {
    'token_overlap': 0.30,   # highest: handles reordering perfectly
    'levenshtein':   0.25,   # high: strong on char differences
    'phonetic':      0.20,   # medium: sound variants
    'ngram':         0.15,   # medium: fills gaps
    'embedding':     0.10,   # low: unreliable on proper nouns
}


def score_name_similarity(name1, name2):
    """
    Runs all five name algorithms and returns a
    weighted combined name similarity score.

    WHY ALL FIVE:
    Each algorithm catches what others miss.
    Levenshtein misses reordering — token overlap catches it.
    Phonetic misses some variants — N-gram catches them.
    Combined signal is always stronger.

    Returns:
    - score: float between 0.0 and 1.0
    - breakdown: dict showing each algorithm's contribution
                 so we can explain WHY the score is what it is
    """

    # Calculate each algorithm's score
    scores = {
        'token_overlap': token_overlap_similarity(name1, name2),
        'levenshtein':   levenshtein_similarity(name1, name2),
        'phonetic':      phonetic_similarity(name1, name2),
        'ngram':         jaccard_similarity(name1, name2),
        'embedding':     embedding_similarity(name1, name2),
    }

    # Calculate weighted sum
    # WHY: each score multiplied by its weight
    # then summed = weighted average
    weighted_sum = 0.0
    for algorithm, score in scores.items():
        weight       = NAME_ALGORITHM_WEIGHTS[algorithm]
        weighted_sum += score * weight

    return weighted_sum, scores


def score_dob(dob1, dob2, tolerance_years=2):
    """
    Compares two date of birth values with tolerance.

    WHY ±2 YEARS TOLERANCE:
    1. Data entry errors are common — clerk types 1970 vs 1971
    2. Deliberate evasion — sanctioned person gives wrong DOB
    3. Intelligence uncertainty — OFAC uses "circa 1960"
    4. Multiple sources may have different values

    WHY RETURN NULL FOR MISSING:
    If either DOB is unknown, we cannot score this field.
    Returning 0 would penalise records with missing DOB —
    systematically letting sanctioned entities with missing
    data slip through. NULL excludes it from the average.

    Returns:
    - 1.0 if DOBs match within tolerance
    - 0.0 if DOBs exist but are too far apart
    - None if either DOB is missing (excluded from scoring)
    """

    # Handle missing values
    # WHY CHECK BOTH: either missing = we cannot compare
    if dob1 is None or dob2 is None:
        return None   # NULL — excluded from average

    # Extract year — handle both "1970" and "1970-01-15" formats
    try:
        year1 = int(str(dob1)[:4])
        year2 = int(str(dob2)[:4])
    except (ValueError, TypeError):
        return None   # Cannot parse — treat as missing

    difference = abs(year1 - year2)

    if difference <= tolerance_years:
        return 1.0    # Within tolerance — DOB evidence satisfied
    else:
        return 0.0    # Too far apart — DOB evidence contradicts


def score_country(country1, country2):
    """
    Compares country fields.

    WHY SIMPLE EXACT MATCH:
    Country names should be standardised during normalisation.
    If both are present and match — strong corroborating signal.
    If both are present and don't match — evidence against.
    If either is missing — NULL, excluded from scoring.

    Returns:
    - 1.0 if countries match
    - 0.0 if countries exist but don't match
    - None if either country is missing
    """
    if country1 is None or country2 is None:
        return None

    # Normalise before comparing
    c1 = country1.lower().strip()
    c2 = country2.lower().strip()

    return 1.0 if c1 == c2 else 0.0


def score_passport(passport1, passport2):
    """
    Compares passport numbers.

    WHY PASSPORT IS THE STRONGEST SIGNAL:
    A passport number uniquely identifies a document.
    Exact match is near-certain identity confirmation.
    Non-match does NOT mean different person —
    passports expire, people get new ones, use multiple.

    Returns:
    - 1.0 if passports match exactly
    - 0.0 if both exist but don't match
    - None if either is missing
    """
    if passport1 is None or passport2 is None:
        return None

    p1 = str(passport1).upper().strip()
    p2 = str(passport2).upper().strip()

    return 1.0 if p1 == p2 else 0.0


def score_records(record1, record2):
    """
    Master scoring function — combines ALL field scores
    into one final confidence score.

    Takes two records as dictionaries:
    {
        'name':     string or None,
        'dob':      string or None,
        'country':  string or None,
        'passport': string or None
    }

    Returns:
    - final_score: float between 0.0 and 1.0
    - explanation: string describing why this score was given
    - breakdown: dict of all individual scores

    WHY RETURN EXPLANATION:
    Compliance analysts must be able to answer:
    "Why did the system say these two records are the same?"
    We build the reason string here — Phase 7 explainability
    starts from day one, not as an afterthought.
    """

    breakdown = {}
    explanation_parts = []

    # ── Name similarity ──────────────────────────────────
    # Name is always present — if missing, use empty string
    # ── Name similarity ──────────────────────────────────
    # WHY WE CHECK ALIASES:
    # Two records might have completely different primary names
    # but share an alias — Abu Bakr Al-Baghdadi is also known as
    # Ibrahim Awad Ibrahim Al-Badri. If EU uses the birth name
    # and UN uses the common name, primary name comparison fails.
    # We check ALL name combinations and take the highest score.

    name1    = record1.get('name') or ''
    name2    = record2.get('name') or ''
    aliases1 = record1.get('aliases', []) or []
    aliases2 = record2.get('aliases', []) or []

    # Build list of all names for each record
    all_names1 = [name1] + aliases1 if name1 else aliases1
    all_names2 = [name2] + aliases2 if name2 else aliases2

    if all_names1 and all_names2:
        # Try every combination — take highest score
        # WHY HIGHEST: we want the best evidence available
        # If any name pair matches strongly — that is evidence
        best_name_score     = 0.0
        best_name_breakdown = {}

        for n1 in all_names1:
            for n2 in all_names2:
                if n1 and n2:
                    s, b = score_name_similarity(n1, n2)
                    if s > best_name_score:
                        best_name_score     = s
                        best_name_breakdown = b

        breakdown['name'] = best_name_score
        breakdown['name_detail'] = best_name_breakdown
        explanation_parts.append(
            f"name similarity {best_name_score:.2f}"
        )
    else:
        breakdown['name'] = None

    # ── DOB similarity ───────────────────────────────────
    dob_score = score_dob(
        record1.get('dob'),
        record2.get('dob')
    )
    breakdown['dob'] = dob_score

    if dob_score is not None:
        explanation_parts.append(f"DOB score {dob_score:.2f}")
    else:
        explanation_parts.append("DOB unknown (excluded)")

    # ── Country similarity ───────────────────────────────
    country_score = score_country(
        record1.get('country'),
        record2.get('country')
    )
    breakdown['country'] = country_score

    if country_score is not None:
        explanation_parts.append(f"country score {country_score:.2f}")
    else:
        explanation_parts.append("country unknown (excluded)")

    # ── Passport similarity ──────────────────────────────
    passport_score = score_passport(
        record1.get('passport'),
        record2.get('passport')
    )
    breakdown['passport'] = passport_score

    if passport_score is not None:
        explanation_parts.append(f"passport score {passport_score:.2f}")
    else:
        explanation_parts.append("passport unknown (excluded)")

    # ── Weighted final score ─────────────────────────────
    # Field weights — passport is strongest single identifier
    FIELD_WEIGHTS = {
        'name':     0.40,   # important but can be wrong
        'dob':      0.20,   # useful but often missing/wrong
        'country':  0.15,   # corroborating signal
        'passport': 0.25,   # strongest single identifier
    }

    weighted_sum      = 0.0
    total_weight_used = 0.0

    for field, weight in FIELD_WEIGHTS.items():
        score = breakdown.get(field)

        if score is not None:
            # Field has a value — include in average
            weighted_sum      += score * weight
            total_weight_used += weight
        # else: field is NULL — excluded from average
        # WHY: do not penalise for missing data

    # Normalise by weights actually used
    # WHY: if passport is missing (weight 0.25 excluded)
    #      we normalise over remaining 0.75 not 1.0
    #      otherwise scores are systematically low
    if total_weight_used == 0:
        final_score = 0.0
    else:
        final_score = weighted_sum / total_weight_used

    # ── Decision ─────────────────────────────────────────
    # ── Decision ─────────────────────────────────────────
    # WHY OVERRIDE CONDITIONS:
    # Pure score thresholds miss edge cases where one field
    # provides overwhelming evidence despite low overall score.
    #
    # OVERRIDE 1 — DOB exact match + country match:
    # If two records have identical DOB AND same country
    # they warrant manual review regardless of name similarity.
    # WHY: DOB exact match is very unlikely by chance.
    # Combined with country — strong corroborating evidence.
    # This catches temporal drift cases (name change after marriage)
    # where name algorithms fail but DOB+country confirm identity.
    #
    # OVERRIDE 2 — Passport exact match:
    # Passport match alone forces manual review minimum.
    # A passport number is a unique document identifier.
    # Two records sharing a passport number must be reviewed.

    dob_exact     = breakdown.get('dob') == 1.0
    country_exact = breakdown.get('country') == 1.0
    passport_hit  = breakdown.get('passport') == 1.0

    if final_score >= 0.85:
        decision = "AUTO BLOCK"
    elif final_score >= 0.65:
        decision = "MANUAL REVIEW"
    elif dob_exact and country_exact:
        # Override — DOB + country exact match
        # forces manual review even with low name score
        decision = "MANUAL REVIEW"
        explanation_parts.append(
            "OVERRIDE: DOB+country exact match"
        )
    elif passport_hit:
        # Override — passport match forces manual review
        decision = "MANUAL REVIEW"
        explanation_parts.append(
            "OVERRIDE: passport exact match"
        )
    else:
        decision = "CLEAR"

    # ── Build explanation string ──────────────────────────
    # WHY DETAILED EXPLANATION:
    # A compliance analyst must be able to answer:
    # "Why did the system say these two records match?"
    # Regulators require this audit trail.
    # A score alone is not sufficient — the reasoning must
    # be documented for every decision made by the system.

    explanation_lines = []

    # Line 1 — Overall decision
    explanation_lines.append(
        f"DECISION: {decision} (confidence: {final_score:.2f})"
    )

    # Line 2 — Name analysis
    name_detail = breakdown.get('name_detail', {})
    if name_detail:
        explanation_lines.append(
            f"NAME ANALYSIS:"
        )
        explanation_lines.append(
            f"  Levenshtein:    {name_detail.get('levenshtein', 0):.2f}"
            f"  (character edit distance)"
        )
        explanation_lines.append(
            f"  Phonetic:       {name_detail.get('phonetic', 0):.2f}"
            f"  (sound similarity)"
        )
        explanation_lines.append(
            f"  Token overlap:  {name_detail.get('token_overlap', 0):.2f}"
            f"  (shared words)"
        )
        explanation_lines.append(
            f"  N-gram:         {name_detail.get('ngram', 0):.2f}"
            f"  (character chunks)"
        )
        explanation_lines.append(
            f"  Embedding:      {name_detail.get('embedding', 0):.2f}"
            f"  (semantic meaning)"
        )
        explanation_lines.append(
            f"  Combined name:  {breakdown.get('name', 0):.2f}"
        )

    # Line 3 — Field by field breakdown
    explanation_lines.append(f"FIELD SCORES:")

    dob_score = breakdown.get('dob')
    if dob_score is not None:
        dob_label = "exact match" if dob_score == 1.0 \
                    else "within tolerance" if dob_score > 0 \
                    else "too different"
        explanation_lines.append(
            f"  DOB:      {dob_score:.2f}  ({dob_label})"
        )
    else:
        explanation_lines.append(
            f"  DOB:      NULL  (missing from one or both records"
            f" — excluded from score)"
        )

    country_score = breakdown.get('country')
    if country_score is not None:
        country_label = "exact match" if country_score == 1.0 \
                        else "no match"
        explanation_lines.append(
            f"  Country:  {country_score:.2f}  ({country_label})"
        )
    else:
        explanation_lines.append(
            f"  Country:  NULL  (missing — excluded from score)"
        )

    passport_score = breakdown.get('passport')
    if passport_score is not None:
        passport_label = "EXACT MATCH — strong identity signal" \
                         if passport_score == 1.0 \
                         else "no match (may have new passport)"
        explanation_lines.append(
            f"  Passport: {passport_score:.2f}  ({passport_label})"
        )
    else:
        explanation_lines.append(
            f"  Passport: NULL  (missing — excluded from score)"
        )

    # Line 4 — Override conditions if fired
    for part in explanation_parts:
        if "OVERRIDE" in part:
            explanation_lines.append(
                f"⚠️  {part}"
            )

    # Line 5 — What the analyst should do
    if decision == "AUTO BLOCK":
        explanation_lines.append(
            "ACTION: Transaction blocked automatically. "
            "Notify compliance officer."
        )
    elif decision == "MANUAL REVIEW":
        explanation_lines.append(
            "ACTION: Send to analyst review queue. "
            "Do not process transaction until reviewed."
        )
    else:
        explanation_lines.append(
            "ACTION: Transaction cleared. "
            "Audit log entry created."
        )

    explanation = "\n".join(explanation_lines)

    return final_score, decision, explanation, breakdown


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


    # --------------------------------------------------------
    # COMBINED FEATURE VECTOR SCORING TESTS
    # --------------------------------------------------------
    print()
    print("=" * 55)
    print("COMBINED FEATURE VECTOR SCORING TESTS")
    print("=" * 55)

    # Test 1: Strong match — same person, small name difference
    record_sanctions_1 = {
        'name':     'Usama Bin Laden',
        'dob':      '1957',
        'country':  'Saudi Arabia',
        'passport': None
    }
    record_transaction_1 = {
        'name':     'Osama Bin Ladin',
        'dob':      '1957',
        'country':  'Saudi Arabia',
        'passport': None
    }

    # Test 2: Same name, completely different person
    record_sanctions_2 = {
        'name':     'Ali Khan',
        'dob':      '1975',
        'country':  'Pakistan',
        'passport': 'PK-7734521'
    }
    record_transaction_2 = {
        'name':     'Ali Khan',
        'dob':      '1975',
        'country':  'Pakistan',
        'passport': 'PK-9981234'   # different passport
    }

    # Test 3: Missing fields — DOB and passport unknown
    record_sanctions_3 = {
        'name':     'Abdul Rahman Al-Sudais',
        'dob':      None,
        'country':  'Saudi Arabia',
        'passport': None
    }
    record_transaction_3 = {
        'name':     'Abdel Rahman Al-Sudais',
        'dob':      '1960',
        'country':  'Saudi Arabia',
        'passport': None
    }

    # Test 4: Passport match — strongest signal
    record_sanctions_4 = {
        'name':     'Hassan Al-Turabi',
        'dob':      '1932',
        'country':  'Sudan',
        'passport': 'SD-4421983'
    }
    record_transaction_4 = {
        'name':     'Hasan Al-Turabi',
        'dob':      '1933',
        'country':  'Sudan',
        'passport': 'SD-4421983'   # same passport ← strong signal
    }

    test_cases = [
        ("Test 1: Strong name match",
         record_sanctions_1, record_transaction_1),
        ("Test 2: Same name, different passport",
         record_sanctions_2, record_transaction_2),
        ("Test 3: Missing fields",
         record_sanctions_3, record_transaction_3),
        ("Test 4: Passport match",
         record_sanctions_4, record_transaction_4),
    ]

    for test_name, rec1, rec2 in test_cases:
        score, decision, explanation, breakdown = score_records(rec1, rec2)
        print(f"\n{test_name}")
        print(f"  Record 1: {rec1}")
        print(f"  Record 2: {rec2}")
        print(f"  → {explanation}")      