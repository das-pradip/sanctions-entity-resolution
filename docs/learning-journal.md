# Learning Journal — Sanctions Entity Resolution


## Day 1 — Understanding The Problem

### What I learned today

**Entity Resolution vs Deduplication vs Record Linkage**
- Deduplication: finding duplicate records within one database
- Record Linkage: matching records across two different databases  
- Entity Resolution: the full problem — reconstruct real-world 
  identities from messy, multi-source, noisy records
- We are building entity resolution — the hardest of the three

**The cost of getting it wrong**
- False Positive: blocking an innocent person
  → legal liability, lost business, angry customer
- False Negative: missing a sanctioned entity
  → criminal fine up to $1B+, reputational destruction
- These costs are NOT equal — missing a sanctioned person 
  is catastrophically worse than a false alarm
- This asymmetry shapes every design decision in the system

**Why exact string matching fails**
- "Usama Bin Laden" and "Osama Bin Ladin" are the same person
- Arabic names have no single correct English spelling
- Every bank, every country, every clerk transliterates differently
- Exact matching fails systematically for entire populations:
  Arabic, Chinese, Russian, Persian, Korean names

---

## Day 1 — Data Challenges

### Challenge 1: Name Transliteration
- Same person, completely different string representations
- OFAC: USAMA BIN LADEN
- UN:   OSAMA BIN LADIN  
- EU:   OUSSAMA BEN LADEN
- Solution: match on sound and structure, not string

### Challenge 2: Alias Explosion  
- One sanctioned entity can have 50+ known names
- Abu Bakr Al-Baghdadi had 9+ documented aliases
- Danger: common alias tokens (e.g. "Abu Bakr") match 
  thousands of innocent people
- Solution: accumulate corroborating evidence across 
  multiple fields — name alone is not enough

### Challenge 3: Missing Fields
- OFAC entries often have no DOB, no passport number
- Key insight: missing field = NULL, not zero
- If treated as zero: score is systematically dragged down
  for every incomplete sanctions record → sanctioned people
  with missing data slip through every time
- If treated as NULL: excluded from average, score computed
  only on available evidence

### Challenge 4: Multi-Source Conflicts
- Same person on OFAC, UN, EU — different DOB, different spelling
- Wrong solution: pick one source, discard others
- Right solution: store ALL observed values as an evidence cluster
  DOB variants: [1970, 1971]
  Name variants: [all three spellings]
- At match time: check incoming value against every known variant
- ±2 year tolerance on DOB to handle data entry errors

### Challenge 5: Temporal Drift
- Sanctioned person changes name after marriage
- Name field becomes useless — zero string overlap
- Solution: graph-based linking
  When first matched, store all linked attributes:
  bank account, phone, address, known associates
- In future: new name, same bank account → graph catches it

### Challenge 6: Many-To-Many Ambiguity
- 847 customers named Ali Khan, same nationality, similar DOB
- Passport number is the strongest single differentiator
- But passport not always available (digital banks, old accounts)
- Architectural solution: BLOCKING
  Narrow candidates BEFORE scoring using hard filters
  Phonetic bucket + country + DOB year
  Reduces 847 candidates → 2 genuine candidates for scoring
  Rule: blocking must NEVER eliminate a true match

---

## Key Design Decisions I Understand

| Decision | Why |
|----------|-----|
| NULL not zero for missing fields | Prevents systematic bias against incomplete records |
| Store all DOB/name variants | Each source is an intelligence report, not ground truth |
| Blocking before scoring | O(n²) is impossible at scale — blocking makes it feasible |
| ±2 year DOB tolerance | Deliberate evasion tactic + data entry errors are common |
| Graph linking | Names change, but behavioural fingerprints persist |
| Manual review queue | Uncertain cases need human judgment, not automated decisions |

---

## What I Will Build Next

Phase 2: Algorithm survey
- Exact matching — already understand why it fails
- Levenshtein distance — measure how many edits between two strings
- Phonetic matching — match on how a name sounds, not how it's spelled
- N-gram similarity — token overlap scoring
- Vector embeddings — semantic similarity
- Blocking — candidate generation
- ML scoring — binary classification
- Hybrid pipeline — combining all methods


## Day 2 — Levenshtein Distance Algorithm

### What I learned

**Why Levenshtein Distance:**
- Exact matching returns only True or False — no middle ground
- Levenshtein measures HOW different two strings are
- Returns minimum number of single character edits needed:
  - Substitute: change one character → "Usama" to "Osama"
  - Insert: add a character
  - Delete: remove a character

**Key example:**
- "Abdul Rahman" vs "Abdel Rahman" → distance 1, similarity 0.92
- One character difference — exact match said False
- Levenshtein says 92% similar — same person

**Data structures used:**
- 2D List (Matrix/Grid) — stores subproblem solutions
- Dynamic Programming — reuses previous solutions
  instead of recalculating from scratch each time
- Each cell grid[i][j] = edit distance between
  first i chars of s1 and first j chars of s2
- Bottom-right cell = final answer

**Why we normalise:**
- Raw distance of 2 means different things for short vs long names
- We divide by longest string length
- Converts to 0.0 to 1.0 scale — comparable across all names

**Critical insight:**
- Name similarity alone cannot make a block or clear decision
- 0.60 similarity = uncertain = needs corroborating evidence
- Final score must combine: name + DOB + country + passport
- Missing fields = NULL, excluded from average, not zeroed

**What I will build next:**
- Phonetic matching — catch names that sound same but spell differently
- DOB proximity scoring — ±2 year tolerance
- Combined feature vector — one score from all available fields

---

## Day 2 — Phonetic Matching (Soundex)

### Why Levenshtein alone is not enough
- Levenshtein compares spelling character by character
- Muhammad vs Mohammed → Levenshtein: 0.75 (borderline)
- These names sound identical when spoken
- A bank clerk spells the same spoken name differently
  every time — spelling varies, sound does not

### How Soundex works
Four rules:
1. Keep first letter unchanged
2. Remove all vowels after first letter
3. Replace consonants with sound-group numbers:
   B,F,P,V → 1   (lip sounds)
   C,G,J,K,Q,S,X,Z → 2  (throat/hiss sounds)
   D,T → 3        (tongue sounds)
   L → 4
   M,N → 5        (nasal sounds)
   R → 6
4. Keep exactly 4 characters, pad with zeros

### Key results
- Muhammad → M530 | Mohammed → M530 → similarity 1.00
  Levenshtein said 0.75 — phonetic correctly says 1.00
- Usama → U250 | Osama → O250 → similarity 0.80
  First letter differs due to Arabic vowel transliteration
  Numeric pattern identical — partial credit given

### Critical insight — why combine algorithms
- No single algorithm wins alone
- Levenshtein: strong on spelling variants (1-2 char differences)
- Soundex: strong on sound variants (transliteration)
- Combined signal is always stronger than either alone
- This is why we build a hybrid pipeline

### Soundex limitations I know
- "Yusuf" vs "Joseph" — same name, different languages
  sound differently → Soundex misses this
- Very short names (Ali, Omar) — low information in 4 chars
- This is why we add more algorithms: N-gram, embeddings

### What I will build next
- Algorithm D: N-gram similarity
  Splits names into overlapping character chunks
  Catches partial matches that both Levenshtein and
  Soundex miss

  ---

## Day 2 — N-gram Similarity and Token Overlap

### The problem that motivated this algorithm
"Bin Laden" vs "Laden Bin" — same words, different order
- Exact match:   False   ← wrong
- Levenshtein:   0.11    ← wrong
- Soundex:       fails   ← wrong
- Token overlap: 1.00    ← correct ✅

Root cause: all previous algorithms treat name as one
continuous string read left to right. They cannot handle
reordered tokens.

### How N-grams work
Sliding window of n characters across a string:
"laden" trigrams (n=3): { "lad", "ade", "den" }

WHY n=3:
- n=2 too short: "la" appears in many unrelated names
- n=3 balanced: specific enough, flexible enough
- n=4 too strict: one spelling difference kills match

### Jaccard similarity formula
Jaccard = shared ngrams / total unique ngrams
Rahman  vs Rehman:
  shared = { "hma", "man" } = 2
  union  = 6 total unique trigrams
  score  = 2/6 = 0.33

### Token overlap
Splits names into words, measures word-level overlap
"Bin Laden" vs "Laden Bin":
  tokens1 = { "bin", "laden" }
  tokens2 = { "laden", "bin" }
  shared  = { "bin", "laden" }
  score   = 2/2 = 1.00

### Two levels needed
- Character ngrams: single word spelling variants
  Rahman vs Rehman → 0.33 (partial credit)
- Token overlap: multi-word reordering
  Bin Laden vs Laden Bin → 1.00

### Python concepts used
- set() — unordered collection, no duplicates
  WHY: order does not matter for overlap calculation
- & operator — set intersection (shared items)
- | operator — set union (all unique items)
- .split() — splits string into list of words

### Critical insight — algorithm comparison table
No single algorithm gets all cases right.
Hybrid pipeline combining all algorithms is necessary.
Each algorithm covers the blind spots of the others.


---

## Day 3 — Vector Embeddings (Semantic Similarity)

### What embeddings are
- Convert a name into a list of 384 numbers (a vector)
- Each number = one dimension of meaning
- Names with similar meaning are close together in this space
- Distance between vectors = semantic similarity

### How cosine similarity works
- Measures the angle between two vectors
- Small angle = same direction = similar meaning = high score
- Large angle = different direction = different meaning = low score
- Formula: cos(θ) = (A · B) / (|A| × |B|)
- WHY cosine not euclidean: measures direction not magnitude

### Library used
- sentence-transformers — pre-trained on 1 billion sentence pairs
- Model: all-MiniLM-L6-v2 — small, fast, free, runs locally
- Loaded once at startup — takes ~2 seconds
- Reusing one model object for all comparisons

### Surprising results and why
Osama Bin Laden vs Usama Bin Ladin → 0.49 (expected ~0.90)
WHY: Model treats them as two different proper noun tokens
     seen in different contexts during training
     Levenshtein (0.87) was better here

Ali Khan vs Ahmed Khan → 0.86 (expected ~0.40)
WHY: Both South Asian male names appearing in similar
     contexts in training data — model thinks they are
     semantically related even though different people
     This is a FALSE POSITIVE risk

### When embeddings help vs hurt
STRONG at:
- Common name variants model learned (Muhammad/Mohammed)
- Detecting completely unrelated strings
- Cross-language semantic similarity

WEAK at:
- Transliterated proper nouns (Osama/Usama)
- Distinguishing similar-context names (Ali/Ahmed)
- Unknown aliases with no training data

### The key lesson
No single algorithm wins alone.
Each algorithm covers the blind spots of the others.
Embeddings are one signal among many — not the answer alone.

### Python concepts used
- numpy (np) — mathematical operations on arrays
- np.dot() — dot product of two vectors
- np.linalg.norm() — length of a vector
- np.clip() — keep values within a range
- import at module level — load model once, reuse everywhere

---

## Day 3 — Combined Feature Vector Scorer

### What this function does
Combines all five name algorithms + DOB + country + passport
into one final confidence score and decision.

### Field weights
name:     0.40  — important but can be wrong/variant
passport: 0.25  — strongest single identifier
dob:      0.20  — useful but often missing or wrong
country:  0.15  — corroborating signal

### Name algorithm weights
token_overlap: 0.30  — highest, handles reordering
levenshtein:   0.25  — strong on char differences
phonetic:      0.20  — sound variants
ngram:         0.15  — fills gaps
embedding:     0.10  — lowest, unreliable on proper nouns

### Decision thresholds
score ≥ 0.85 → AUTO BLOCK
score ≥ 0.65 → MANUAL REVIEW
score < 0.65 → CLEAR

### Key results from testing

Test 1 (Usama/Osama Bin Laden): MANUAL REVIEW (0.78)
- Name scored only 0.59 — embeddings dragged it down
- DOB and country both 1.00 — saved the record
- Passport NULL — excluded not zeroed
- If zeroed: score 0.586 → CLEAR → sanctioned person walks through

Test 2 (Ali Khan, different passport): MANUAL REVIEW (0.75)
- Name, DOB, country all 1.00
- Passport 0.00 — conflicting evidence
- Human needed: new passport of same person OR different person?

Test 3 (Missing fields): MANUAL REVIEW (0.85)
- Only name and country available
- Normalised over available weights only
- If zeroed: score drops below 0.65 → CLEAR → dangerous

Test 4 (Passport match): AUTO BLOCK (0.89)
- Passport exact match — strongest signal
- Corroborated by country and DOB proximity
- Correct decision

### The NULL-aware scoring proof
Zeroing missing fields systematically clears sanctioned
entities who have sparse data on sanctions lists.
Sanctioned people deliberately keep details sparse.
NULL-aware scoring is not optional — it is critical.

### What I will build next
- tests/test_matching.py — formal test cases
- Phase 3: synthetic dataset with real OFAC/UN/EU structure
- Phase 4: Precision, Recall, F1 metrics

---

## Day 4 — Synthetic Dataset and Blocking

### Why synthetic data
- Real sanctions data cannot be on public GitHub
- Synthetic data gives us controlled ground truth
- We know exactly which records are the same person
- Ground truth lets us measure precision and recall later

### Dataset structure
- 20 records across OFAC, UN, EU sources
- 10 clusters — groups of same person across sources
- Every real challenge represented:
  transliteration, missing fields, DOB conflicts,
  alias explosion, temporal drift, common names

### What blocking does
Without blocking: 190 pairs to compare (n×(n-1)/2)
With blocking:    53 pairs to compare
Reduction:        72.1% fewer comparisons

### How blocking works
Step 1: Generate blocking keys for every sanctions record
        - Phonetic key from name and all aliases
        - Country key
        - DOB year keys with ±2 tolerance window
Step 2: Build index — blocking_key → list of record IDs
        Built ONCE, lookup is O(1) instant
Step 3: For incoming transaction, generate its blocking keys
        Look up each key in index
        Collect all matching record IDs as candidates
Step 4: Score only the candidates — not all records

### Two blocking quality metrics
Reduction ratio:   72.1% — eliminated 72% of pairs ✅
Pair completeness: 100%  — missed zero true matches ✅

### Critical blocking rule
A blocking rule must NEVER eliminate a true match.
It can only eliminate impossible candidates.
Speed without recall is worthless in compliance.

### Why aliases are indexed
A transaction might use an alias not the primary name.
If only primary name is indexed — alias transactions
slip through the blocking step undetected.
Every alias generates its own blocking keys.

### Data structures used
Dictionary (hash map) — blocking index
  key:   blocking key string
  value: list of record IDs in that bucket
  WHY:   O(1) lookup — instant candidate retrieval

Set — candidate collection
  WHY:   automatically deduplicates
         a record in multiple matching buckets
         is only scored once

### What I will build next
Phase 4: Precision, Recall, F1 metrics
         Measure how well the full pipeline performs
         against our ground truth answer key