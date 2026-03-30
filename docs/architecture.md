# System Architecture — Sanctions Entity Resolution Pipeline

> Pradip Das — designed and built from scratch

---

## Full Data Flow
```
┌─────────────────────────────────────────────────┐
│               DATA SOURCES                      │
│                                                 │
│   OFAC (US)      UN List       EU List          │
│   ~12,000        ~700          ~2,000 entries   │
│   XML feed       XML/PDF       XML feed         │
└────────┬─────────────┬──────────────┬───────────┘
         │             │              │
         ▼             ▼              ▼
┌─────────────────────────────────────────────────┐
│           [1] INGEST LAYER                      │
│                                                 │
│  Download from official government URLs         │
│  Parse XML/CSV into Python dictionaries         │
│  Assign unique ID: OFAC-001, UN-001, EU-001     │
│  Tag each record with source                    │
│  Store raw records before any modification      │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│           [2] NORMALISATION                     │
│                                                 │
│  src/normaliser.py                              │
│                                                 │
│  Step 1: Lowercase                              │
│          "OSAMA" → "osama"                      │
│  Step 2: Remove diacritics                      │
│          "Müller" → "muller"                    │
│  Step 3: Strip whitespace                       │
│          "Ali  Khan" → "Ali Khan"               │
│  Step 4: Remove punctuation                     │
│          "Al-Hassan" → "Al Hassan"              │
│  Step 5: Transliteration rules                  │
│          "Abdel" → "abdal"                      │
│          "Osama" → "usama"                      │
│  Step 6: Tokenise                               │
│          "usama bin laden" →                    │
│          ["usama", "bin", "laden"]              │
│                                                 │
│  Result:                                        │
│  "USAMA BIN LADEN" and "Osama  bin  Laden"      │
│  both normalise to "usama bin laden"            │
│  Levenshtein now scores these 1.00              │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│           [3] BLOCKING INDEX                    │
│                                                 │
│  src/blocking.py                                │
│                                                 │
│  Built ONCE at startup from full database       │
│  O(1) lookup per transaction                    │
│                                                 │
│  Three blocking key types per record:           │
│  ├── Phonetic key (name + all aliases)          │
│  │   "usama" → PHONETIC:U250                    │
│  │   "osama" → PHONETICNUM:250 (same bucket)    │
│  ├── Country key                                │
│  │   COUNTRY:saudi arabia                       │
│  └── DOB year bucket (±2 tolerance)             │
│      DOB:1955, DOB:1956, DOB:1957,              │
│      DOB:1958, DOB:1959                         │
│                                                 │
│  Measured performance:                          │
│  Reduction ratio:    72.1%                      │
│  Pair completeness:  100.0%                     │
└─────────────────────┬───────────────────────────┘
                      │
         ┌────────────┘
         │  INCOMING TRANSACTION
         ▼
┌─────────────────────────────────────────────────┐
│           [4] CANDIDATE GENERATION              │
│                                                 │
│  For incoming transaction:                      │
│  1. Generate blocking keys                      │
│  2. Look up each key in index                   │
│  3. Collect matching record IDs                 │
│  4. Deduplicate with set                        │
│  5. Skip self-comparison                        │
│                                                 │
│  Output: 5-50 candidates from 10,000+ records   │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│           [5] FEATURE EXTRACTION + SCORING      │
│                                                 │
│  src/sanctions.py                               │
│                                                 │
│  NAME SIMILARITY          weight: 0.40          │
│  ├── Token overlap         0.30                 │
│  ├── Levenshtein           0.25                 │
│  ├── Soundex phonetic      0.20                 │
│  ├── N-gram Jaccard        0.15                 │
│  └── Vector embeddings     0.10                 │
│                                                 │
│  ALIAS EXPANSION                                │
│  All name×alias combinations checked            │
│  Best score used                                │
│                                                 │
│  DOB PROXIMITY            weight: 0.20          │
│  ±2 year tolerance                              │
│                                                 │
│  COUNTRY MATCH            weight: 0.15          │
│  Exact match only                               │
│                                                 │
│  PASSPORT MATCH           weight: 0.25          │
│  Strongest single signal                        │
│                                                 │
│  NULL HANDLING                                  │
│  Missing fields excluded from average           │
│  Never zeroed                                   │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│           [6] DECISION ENGINE                   │
│                                                 │
│  Score ≥ 0.85 → AUTO BLOCK                      │
│  Score ≥ 0.65 → MANUAL REVIEW                   │
│  Score < 0.65 → CLEAR                           │
│                                                 │
│  OVERRIDE CONDITIONS                            │
│  DOB exact + Country exact → MANUAL REVIEW      │
│  Passport exact match      → MANUAL REVIEW      │
│                                                 │
│  WHY OVERRIDES:                                 │
│  Catches temporal drift cases                   │
│  Fatima AL-HASSAN → AL-RASHIDI after marriage   |
│  Different name, different passport             │
│  Same DOB + country → must be reviewed          │
└──────────┬──────────────────┬───────────────────┘
           │                  │
           ▼                  ▼
┌─────────────────┐  ┌────────────────────────────┐
│  AUTO BLOCK     │  │   MANUAL REVIEW QUEUE      │
│                 │  │                            │
│ Transaction     │  │ Analyst sees:              │
│ blocked         │  │ ├── Record A vs Record B   │
│ immediately     │  │ ├── Confidence score       │
│                 │  │ ├── Name analysis:         │
│ Compliance      │  │ │   Levenshtein: 0.87      │
│ officer         │  │ │   Phonetic: 0.80         │
│ notified        │  │ │   Token overlap: 0.20    │
│                 │  │ ├── Field scores:          │
│                 │  │ │   DOB: 1.00 exact match  │
│                 │  │ │   Country: 1.00          │
│                 │  │ │   Passport: NULL         │
│                 │  │ └── Required action        │
└─────────────────┘  └──────────────┬─────────────┘
                                     │
                     Analyst confirms match
                                     │
                                     ▼
                     ┌──────────────────────────────┐
                     │   [7] GRAPH STORE            │
                     │                              │
                     │  Entity nodes linked by:     │
                     │  ├── Shared DOB              │
                     │  ├── Shared country          │
                     │  ├── Confirmed aliases       │
                     │  └── Shared associates       │
                     │                              │
                     │  WHY GRAPH:                  │
                     │  Names change after marriage │
                     │  Passports expire            │
                     │  Graph connections persist   │
                     │  Catches temporal drift      │
                     └──────────────────────────────┘
```

---

## Files And Responsibilities
```
src/normaliser.py      ← Step 2: normalise names
src/blocking.py        ← Step 3: build index, get candidates
src/sanctions.py       ← Step 5: all scoring algorithms
src/pipeline.py        ← Step 4+6: run full pipeline, evaluate
data/synthetic_sanctions.py  ← synthetic test dataset
tests/test_matching.py       ← 34 automated tests
docs/learning-journal.md     ← design reasoning documented
```

---

## Performance On Synthetic Dataset
```
Records:              20 across OFAC, UN, EU
Clusters (truth):     10 groups of same person
Blocking reduction:   72.1%
Pair completeness:    100.0%
Precision:            1.00
Recall:               1.00
F1 Score:             1.00
```

---

## Why Each Design Decision Was Made

### NULL not zero for missing fields
Zeroing missing fields drags scores down for records
with sparse data. Sanctioned entities deliberately
keep their details sparse. This would systematically
let dangerous entities through. NULL excludes the
field from the average entirely.

### Five algorithms not one
Each algorithm covers different failure modes:
- Levenshtein: 1-3 character transliteration differences
- Phonetic: sound-alike variants (Muhammad/Mohammed)
- Token overlap: reordered name tokens (Bin Laden/Laden Bin)
- N-gram: partial character chunk matches
- Embeddings: semantic similarity (lowest weight —
  unreliable on transliterated proper nouns)

### Alias expansion
Primary names fail when sources use different names.
Abu Bakr Al-Baghdadi vs Ibrahim Awad Ibrahim Al-Badri
— same person, zero surface similarity.
All alias combinations are checked, best score used.

### Override conditions
DOB exact + country exact forces manual review even
when name similarity is low. This catches temporal
drift — name changes after marriage — where name
algorithms fail but corroborating fields confirm.

### Blocking before scoring
Without blocking: O(n×m) — 100 billion daily comparisons
With blocking: small candidate set — thousands
Blocking must never eliminate true matches.
We verified: 100% pair completeness maintained.