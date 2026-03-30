# src/normaliser.py
#
# WHY THIS FILE EXISTS:
# Before any comparison can happen, names must be
# normalised into a consistent format.
# Without normalisation:
# "Müller" vs "Muller" → poor Levenshtein score
# "OSAMA" vs "osama"   → exact match fails
# "  Ali  " vs "Ali"   → exact match fails
#
# Normalisation happens BEFORE blocking and scoring.
# It is the first step in the pipeline.
#
# WHAT NORMALISATION DOES:
# 1. Lowercase everything
# 2. Strip extra whitespace
# 3. Remove diacritics (é→e, ü→u, ñ→n)
# 4. Transliterate common Arabic/Russian patterns
# 5. Remove punctuation that varies across sources
# 6. Tokenise into individual words

from unidecode import unidecode
import re


# ============================================================
# STEP 1 — LOWERCASE
# ============================================================

def to_lowercase(text):
    """
    Converts text to lowercase.

    WHY:
    "OSAMA BIN LADEN" and "Osama Bin Laden" are the same.
    Different databases use different capitalisation conventions.
    Lowercase is our standard — everything gets converted here.
    """
    if not text:
        return ""
    return text.lower()


# ============================================================
# STEP 2 — STRIP WHITESPACE
# ============================================================

def strip_whitespace(text):
    """
    Removes leading/trailing spaces and collapses
    multiple internal spaces into one.

    WHY:
    "Ali  Khan" (double space) ≠ "Ali Khan" (single space)
    to exact matching. Real data often has extra spaces
    from copy-paste errors or database exports.

    re.sub replaces one or more spaces with single space.
    """
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    return text


# ============================================================
# STEP 3 — REMOVE DIACRITICS
# ============================================================

def remove_diacritics(text):
    """
    Converts accented characters to plain ASCII.

    Examples:
    é → e    (French names)
    ü → u    (German names)
    ñ → n    (Spanish names)
    ø → o    (Scandinavian names)
    ç → c    (Turkish/French names)

    WHY:
    Sanctions lists from different countries use different
    conventions for diacritics. OFAC might store "Muller"
    while EU stores "Müller". Without this step, these
    score poorly despite being the same name.

    unidecode() handles hundreds of character sets
    including Latin, Greek, Cyrillic transliterations.
    """
    if not text:
        return ""
    return unidecode(text)


# ============================================================
# STEP 4 — REMOVE PUNCTUATION
# ============================================================

def remove_punctuation(text):
    """
    Removes punctuation that varies across sources.

    Examples:
    "Al-Hassan" → "Al Hassan"
    "O'Brien"   → "O Brien"
    "bin-Laden" → "bin Laden"

    WHY:
    Hyphens in names are inconsistent — some sources use
    them, others do not. "Al-Hassan" and "Al Hassan" are
    the same name stored differently.

    We keep spaces — they separate name tokens.
    We keep alphanumeric characters.
    We remove everything else.
    """
    if not text:
        return ""
    # Replace hyphens with space — not empty string
    # WHY: "Al-Hassan" → "Al Hassan" not "AlHassan"
    text = text.replace('-', ' ')
    text = text.replace("'", ' ')
    # Remove any remaining non-alphanumeric non-space
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text


# ============================================================
# STEP 5 — TRANSLITERATION PATTERNS
# ============================================================

def apply_transliteration_rules(text):
    """
    Applies common transliteration normalisation rules
    for Arabic names in English.

    WHY:
    Arabic has sounds that do not exist in English.
    Different transliteration systems handle them differently:

    "Usama" vs "Osama"     — Arabic 'u' sound
    "Mohamed" vs "Muhammad" — Arabic 'u' vs 'o'
    "Al" vs "El"           — Arabic definite article
    "Abdul" vs "Abdel"     — Arabic vowel in prefix

    We normalise common variants to one standard form
    so comparison algorithms see consistent input.

    This does not solve all transliteration problems —
    that is why we have phonetic matching and embeddings.
    This handles the most common systematic variations.
    """
    if not text:
        return ""

    # Common Arabic transliteration normalisations
    # Format: (pattern, replacement)
    # WHY REGEX: handles word boundaries correctly
    #            "osama" → "usama" but not "dose" → "duse"

    rules = [
        # Definite article variants
        (r'\bal\b', 'al'),      # Al, AL, al → al
        (r'\bel\b', 'al'),      # El → al (Egyptian Arabic)
        (r'\bul\b', 'al'),      # Ul → al

        # Common prefix variants
        (r'\babdul\b', 'abdal'),    # Abdul/Abdel → abdal
        (r'\babdel\b', 'abdal'),
        (r'\babdal\b', 'abdal'),

        # Common vowel variants in first syllable
        (r'\bosama\b', 'usama'),    # Osama → Usama
        (r'\busama\b', 'usama'),    # already Usama

        # Common suffix variants
        (r'ullah$', 'ulla'),        # Abdullah → Abdulla
        (r'allah$', 'ulla'),

        # Double letters — sometimes single in one source
        (r'([a-z])\1+', r'\1'),    # aa → a, ll → l etc
    ]

    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text)

    return text


# ============================================================
# STEP 6 — TOKENISE
# ============================================================

def tokenise(text):
    """
    Splits normalised text into individual word tokens.

    WHY:
    Many algorithms work better on individual tokens
    than on the full name string.
    "Usama Bin Laden" → ["usama", "bin", "laden"]

    Tokens can be compared individually, reordered,
    or used to generate blocking keys.

    Returns list of non-empty tokens.
    """
    if not text:
        return []
    return [token for token in text.split() if token]


# ============================================================
# MASTER NORMALISATION FUNCTION
# ============================================================

def normalise_name(name):
    """
    Runs a name through all normalisation steps in order.

    Pipeline:
    1. Lowercase
    2. Remove diacritics
    3. Strip whitespace
    4. Remove punctuation
    5. Apply transliteration rules
    6. Strip again (punctuation removal may add spaces)

    Returns:
    - normalised: clean normalised string
    - tokens: list of individual word tokens

    WHY RETURN BOTH:
    Some algorithms need the full string (Levenshtein).
    Others need individual tokens (token overlap, blocking).
    We return both so callers can use what they need.
    """
    if not name:
        return "", []

    # Run pipeline in order
    text = to_lowercase(name)
    text = remove_diacritics(text)
    text = strip_whitespace(text)
    text = remove_punctuation(text)
    text = apply_transliteration_rules(text)
    text = strip_whitespace(text)  # clean up after rules

    tokens = tokenise(text)

    return text, tokens


def normalise_record(record):
    """
    Normalises all name fields in a sanctions record.

    Normalises:
    - Primary name
    - All aliases
    - Leaves DOB, country, passport unchanged
      (these have their own normalisation in scoring)

    Returns new record dict with normalised names.
    WHY NEW DICT: never modify original data
    Always keep raw original — normalised is derived.
    """
    normalised = record.copy()

    # Normalise primary name
    norm_name, tokens = normalise_name(record.get('name', ''))
    normalised['name_normalised']   = norm_name
    normalised['name_tokens']       = tokens

    # Normalise all aliases
    normalised_aliases = []
    for alias in record.get('aliases', []):
        norm_alias, _ = normalise_name(alias)
        normalised_aliases.append(norm_alias)
    normalised['aliases_normalised'] = normalised_aliases

    return normalised


# ============================================================
# TEST THE NORMALISER
# ============================================================

if __name__ == "__main__":

    print("=" * 55)
    print("NAME NORMALISATION TESTS")
    print("=" * 55)

    test_names = [
        ("USAMA BIN LADEN",      "raw OFAC format"),
        ("Osama  bin  Laden",    "double spaces"),
        ("Müller Heinrich",      "German diacritics"),
        ("José García",          "Spanish diacritics"),
        ("AL-HASSAN",            "hyphenated prefix"),
        ("Abdul Rahman",         "Abdul prefix"),
        ("Abdel Rahman",         "Abdel variant"),
        ("Mohammed Al-Zawahiri", "hyphen in surname"),
        ("  Ali Khan  ",         "leading/trailing spaces"),
        ("FATIMA AL-RASHIDI",    "uppercase with hyphen"),
    ]

    for name, description in test_names:
        normalised, tokens = normalise_name(name)
        print(f"\nOriginal:   '{name}'  ({description})")
        print(f"Normalised: '{normalised}'")
        print(f"Tokens:     {tokens}")

    print()
    print("=" * 55)
    print("NORMALISATION SIMILARITY IMPROVEMENT")
    print("=" * 55)
    print()

    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    from sanctions import levenshtein_similarity

    pairs = [
        ("Abdul Rahman", "Abdel Rahman"),
        ("AL-HASSAN",    "Al Hassan"),
        ("Müller",       "Muller"),
        ("Mohammed",     "Muhammad"),
    ]

    for name1, name2 in pairs:
        raw_score  = levenshtein_similarity(name1, name2)

        norm1, _ = normalise_name(name1)
        norm2, _ = normalise_name(name2)
        norm_score = levenshtein_similarity(norm1, norm2)

        improvement = norm_score - raw_score
        print(f"'{name1}' vs '{name2}'")
        print(f"  Raw score:        {raw_score:.2f}")
        print(f"  Normalised score: {norm_score:.2f}"
              f"  {'↑ improved' if improvement > 0 else '→ same'}")
        print()