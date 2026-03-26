# Learning Journal — Sanctions Entity Resolution

---

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