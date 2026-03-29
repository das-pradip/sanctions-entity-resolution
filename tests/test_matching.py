# tests/test_matching.py
#
# WHY WE WRITE TESTS:
# Tests prove that our algorithms work correctly and keep
# working correctly as we add more code. Without tests,
# we cannot know if a change we make today breaks something
# that was working yesterday.
#
# HOW TO RUN THESE TESTS:
# python tests/test_matching.py
#
# WHAT A GOOD TEST LOOKS FOR:
# 1. Known matches score ABOVE threshold
# 2. Known non-matches score BELOW threshold
# 3. Edge cases do not crash the system
# 4. NULL fields are handled gracefully

import sys
import os

# WHY THIS LINE:
# Our test file is in the tests/ folder.
# Our code is in the src/ folder.
# Python needs to know where to find our functions.
# sys.path.append tells Python to also look in src/
# Without this, "import sanctions" would fail with ModuleNotFoundError
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sanctions import (
    exact_match,
    levenshtein_similarity,
    phonetic_similarity,
    jaccard_similarity,
    token_overlap_similarity,
    score_records
)

# ============================================================
# TEST RUNNER
# ============================================================
# WHY BUILD OUR OWN SIMPLE RUNNER:
# Python has a library called unittest and pytest for testing.
# We will use those later. For now we build a simple runner
# so you understand WHAT a test framework does internally.
# Later when you use pytest, you will understand why it exists.

passed = 0
failed = 0
errors = []


def test(name, condition, expected=True):
    """
    Runs one test case.

    WHY SEPARATE FUNCTION:
    Every test follows the same pattern:
    - Run a function
    - Check if result matches expectation
    - Report pass or fail
    We avoid repeating this pattern by putting it in a function.
    """
    global passed, failed, errors

    if condition == expected:
        print(f"  ✅ PASS: {name}")
        passed += 1
    else:
        print(f"  ❌ FAIL: {name}")
        print(f"         Expected: {expected}")
        print(f"         Got:      {condition}")
        failed += 1
        errors.append(name)


def run_section(title):
    """Prints a section header."""
    print()
    print("=" * 55)
    print(title)
    print("=" * 55)


# ============================================================
# SECTION 1 — EXACT MATCHING TESTS
# ============================================================

run_section("EXACT MATCHING TESTS")

test(
    "Identical names match",
    exact_match("Osama Bin Laden", "Osama Bin Laden"),
    True
)

test(
    "Case insensitive match",
    exact_match("OSAMA BIN LADEN", "osama bin laden"),
    True
)

test(
    "Whitespace stripped correctly",
    exact_match("  Osama  ", "Osama"),
    True
)

test(
    "Transliteration variant does not exact match",
    exact_match("Usama Bin Laden", "Osama Bin Ladin"),
    False
)

test(
    "Completely different names do not match",
    exact_match("Ali Khan", "Ahmed Hassan"),
    False
)

test(
    "Empty strings match each other",
    exact_match("", ""),
    True
)


# ============================================================
# SECTION 2 — LEVENSHTEIN TESTS
# ============================================================

run_section("LEVENSHTEIN SIMILARITY TESTS")

test(
    "Identical names score 1.0",
    levenshtein_similarity("Ali Khan", "Ali Khan") == 1.0,
    True
)

test(
    "One character difference scores above 0.85",
    levenshtein_similarity("Abdul Rahman", "Abdel Rahman") >= 0.85,
    True
)

test(
    "Two character difference scores above 0.80",
    levenshtein_similarity("Usama Bin Laden", "Osama Bin Ladin") >= 0.80,
    True
)

test(
    "Completely different names score below 0.50",
    levenshtein_similarity("Ali Khan", "Muammar Gaddafi") < 0.50,
    True
)

test(
    "Empty string vs non-empty scores 0.0",
    levenshtein_similarity("", "Ali Khan") == 0.0,
    True
)

test(
    "Reordered tokens score poorly — known limitation",
    levenshtein_similarity("Bin Laden Osama", "Osama Bin Laden") < 0.50,
    True
)


# ============================================================
# SECTION 3 — PHONETIC MATCHING TESTS
# ============================================================

run_section("PHONETIC MATCHING TESTS")

test(
    "Identical names score 1.0 phonetically",
    phonetic_similarity("Ali", "Ali") == 1.0,
    True
)

test(
    "Muhammad and Mohammed score above 0.90",
    phonetic_similarity("Muhammad", "Mohammed") >= 0.90,
    True
)

test(
    "Usama and Osama score above 0.75",
    phonetic_similarity("Usama", "Osama") >= 0.75,
    True
)

test(
    "Smith and Smyth score 1.0 — classic Soundex case",
    phonetic_similarity("Smith", "Smyth") == 1.0,
    True
)

test(
    "Ali and Ahmed score below 0.60",
    phonetic_similarity("Ali", "Ahmed") < 0.60,
    True
)


# ============================================================
# SECTION 4 — N-GRAM TESTS
# ============================================================

run_section("N-GRAM AND TOKEN OVERLAP TESTS")

test(
    "Identical names have Jaccard score 1.0",
    jaccard_similarity("Ali Khan", "Ali Khan") == 1.0,
    True
)

test(
    "Reordered tokens score 1.0 on token overlap",
    token_overlap_similarity("Bin Laden", "Laden Bin") == 1.0,
    True
)

test(
    "Reordered full name scores 1.0 on token overlap",
    token_overlap_similarity("Osama Bin Laden", "Laden Bin Osama") == 1.0,
    True
)

test(
    "Completely different names score below 0.30 on Jaccard",
    jaccard_similarity("Ali Khan", "Muammar Gaddafi") < 0.30,
    True
)

test(
    "Single character difference has partial Jaccard score",
    jaccard_similarity("Rahman", "Rehman") > 0.0,
    True
)


# ============================================================
# SECTION 5 — COMBINED SCORER TESTS
# ============================================================

run_section("COMBINED SCORER TESTS")

# Test: Strong match should auto block or manual review
strong_match_1 = {
    'name':     'Usama Bin Laden',
    'dob':      '1957',
    'country':  'Saudi Arabia',
    'passport': None
}
strong_match_2 = {
    'name':     'Osama Bin Ladin',
    'dob':      '1957',
    'country':  'Saudi Arabia',
    'passport': None
}
score, decision, _, _ = score_records(strong_match_1, strong_match_2)

test(
    "Strong match scores above 0.70",
    score >= 0.70,
    True
)

test(
    "Strong match does not clear automatically",
    decision != "CLEAR",
    True
)

# Test: Passport match triggers auto block
passport_match_1 = {
    'name':     'Hassan Al-Turabi',
    'dob':      '1932',
    'country':  'Sudan',
    'passport': 'SD-4421983'
}
passport_match_2 = {
    'name':     'Hasan Al-Turabi',
    'dob':      '1933',
    'country':  'Sudan',
    'passport': 'SD-4421983'
}
score, decision, _, _ = score_records(passport_match_1, passport_match_2)

test(
    "Passport match scores above 0.85",
    score >= 0.85,
    True
)

test(
    "Passport match triggers AUTO BLOCK",
    decision == "AUTO BLOCK",
    True
)

# Test: NULL fields are excluded not zeroed
null_fields_1 = {
    'name':     'Abdul Rahman',
    'dob':      None,
    'country':  None,
    'passport': None
}
null_fields_2 = {
    'name':     'Abdul Rahman',
    'dob':      None,
    'country':  None,
    'passport': None
}
score, decision, _, _ = score_records(null_fields_1, null_fields_2)

test(
    "Identical names with all NULL fields score above 0.80",
    score >= 0.80,
    True
)

# Test: Different passport is conflicting evidence
diff_passport_1 = {
    'name':     'Ali Khan',
    'dob':      '1975',
    'country':  'Pakistan',
    'passport': 'PK-1111111'
}
diff_passport_2 = {
    'name':     'Ali Khan',
    'dob':      '1975',
    'country':  'Pakistan',
    'passport': 'PK-9999999'
}
score, decision, _, _ = score_records(diff_passport_1, diff_passport_2)

test(
    "Different passport reduces score below auto block",
    score < 0.85,
    True
)

test(
    "Different passport does not auto block",
    decision != "AUTO BLOCK",
    True
)

# Test: DOB tolerance — within 2 years should score 1.0
from sanctions import score_dob

test(
    "DOB within 1 year scores 1.0",
    score_dob("1970", "1971") == 1.0,
    True
)

test(
    "DOB within 2 years scores 1.0",
    score_dob("1970", "1972") == 1.0,
    True
)

test(
    "DOB 3 years apart scores 0.0",
    score_dob("1970", "1973") == 0.0,
    True
)

test(
    "DOB with None returns None — not zero",
    score_dob(None, "1970") is None,
    True
)

test(
    "DOB with both None returns None",
    score_dob(None, None) is None,
    True
)


# ============================================================
# RESULTS SUMMARY
# ============================================================

print()
print("=" * 55)
print("TEST RESULTS SUMMARY")
print("=" * 55)
print(f"  Total tests:  {passed + failed}")
print(f"  Passed:       {passed}  ✅")
print(f"  Failed:       {failed}  ❌")

if failed == 0:
    print()
    print("  ALL TESTS PASSED")
else:
    print()
    print("  FAILED TESTS:")
    for error in errors:
        print(f"  - {error}")

print()