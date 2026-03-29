# Sanctions Entity Resolution System
> Built from scratch by Pradip Das — learning project documenting 
> every design decision and why it was made.

---

## What Problem Does This Solve?

Banks are legally required to check every transaction against 
government sanctions lists — lists of people, companies, and 
countries that are banned from financial transactions.

The challenge: the same sanctioned person appears differently 
across every database:

| Sanctions List | How They Store The Name      |
|----------------|------------------------------|
| OFAC (US)      | USAMA BIN LADEN              |
| UN List        | OSAMA BIN LADIN              |
| EU List        | OUSSAMA BEN LADEN            |
| Bank Record    | Osama bin Laden              |

Simple string matching says these are 4 different people.
They are the same person.

This system solves that problem.

---

## Why Is This Hard?

| Challenge               | Why It Breaks Simple Systems         |
|-------------------------|--------------------------------------|
| Name transliteration    | Arabic/Russian names have no single  |
|                         | correct English spelling             |
| Alias explosion         | One person can have 50+ known names  |
| Missing fields          | No DOB, no passport on many records  |
| Multi-source conflicts  | OFAC says DOB 1970, EU says 1971     |
| Name changes            | Sanctioned person marries, new name  |
| Common names            | 847 customers named Ali Khan         |

---

## What Happens If We Get It Wrong?

| Error Type    | What Happened              | Real Cost                    |
|---------------|----------------------------|------------------------------|
| False Positive| Blocked innocent person    | Legal liability, lost business|
| False Negative| Missed sanctioned entity   | Criminal fine, up to $1B+    |

---

## How This System Works
```
OFAC / UN / EU Lists
        ↓
   [1] INGEST — Download and parse official XML/CSV feeds
        ↓
   [2] NORMALISE — Lowercase, remove diacritics, 
                   transliterate, cluster aliases
        ↓
   [3] BLOCK — Narrow candidates using hard filters
               (phonetic buckets, country, DOB year)
               Reduces O(n²) to manageable set
        ↓
   [4] SCORE — Compare each candidate pair across:
               • Name similarity (Levenshtein)
               • Phonetic matching (Soundex)
               • DOB proximity (±2 years)
               • Passport match
               • Country match
               NULL fields excluded from average
        ↓
   [5] DECIDE
       Score > 0.90 → Auto Block
       Score > 0.70 → Manual Review Queue
       Score < 0.70 → Clear (with audit log)
        ↓
   [6] GRAPH — Link entities through shared attributes
               Catches name changes and new aliases
        ↓
   [7] REVIEW UI — Analyst sees: Record A vs Record B,
                   confidence score, reason string
```

---

## What I Am Building — Phase By Phase

- [x] Phase 0: Understanding the problem and cost of errors
- [x] Phase 1: Data challenges — transliteration, aliases,
               missing fields, multi-source conflicts
- [x] Phase 2: Algorithm survey — exact match, Levenshtein,
               phonetic, n-gram, embeddings, combined scorer
               34 tests passing ✅
- [ ] Phase 3: Experiment setup with synthetic data
- [ ] Phase 4: Precision, Recall, F1 metrics
- [ ] Phase 5: Full system architecture design
- [ ] Phase 6: Incremental build — one component per session
- [ ] Phase 7: Explainability
- [ ] Phase 8: Production thinking

---

## Data Sources

- [OFAC SDN List](https://sanctionslist.ofac.treas.gov/)
- [UN Consolidated List](https://www.un.org/securitycouncil/content/un-sc-consolidated-list)
- [EU Sanctions List](https://www.eeas.europa.eu/eeas/european-union-sanctions_en)

---

## Key Design Decisions And Why

**Why not just use string matching?**
The same person has no canonical string representation across 
languages. You must match on sound, structure, and context.

**Why store all DOB variants instead of one?**
Each source is an intelligence report — potentially incomplete 
or wrong. Storing all observed values maximises detection surface.

**Why is a missing field NULL and not zero?**
Absence of evidence is not evidence of absence. Zeroing a missing 
field systematically drags down scores for incomplete records — 
sanctioned entities deliberately keep their details sparse.

**Why blocking before scoring?**
Without blocking, comparing 1M customers against 10K sanctions 
records = 10 billion comparisons. Blocking reduces this to 
thousands. Speed without sacrificing recall.

---

## How To Run This Project
```bash
# Clone the repository
git clone https://github.com/das-pradip/sanctions-entity-resolution.git
cd sanctions-entity-resolution

# Install dependencies
pip install -r requirements.txt

# Run the matching engine
python src/sanctions.py
```

---

## Author

**Pradip Das**  
Building this project to deeply understand compliance technology 
and entity resolution systems.  
[GitHub](https://github.com/das-pradip)