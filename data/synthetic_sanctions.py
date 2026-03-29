# data/synthetic_sanctions.py
#
# WHY SYNTHETIC DATA:
# Real sanctions data cannot be committed to a public GitHub
# repository for legal and security reasons.
# Synthetic data lets us:
# 1. Control exactly what tricky cases exist
# 2. Know the ground truth — which records ARE the same person
# 3. Test our system against known correct answers
# 4. Share publicly without legal issues
#
# HOW THIS MIRRORS REAL DATA:
# Real OFAC SDN list is published as XML with these fields:
# - uid, lastName, firstName, akaList, dobList,
#   citizenshipList, idList (passport numbers)
# Real UN list uses similar structure but different field names
# Real EU list uses yet another format
# We simulate all three formats and their inconsistencies

# ============================================================
# GROUND TRUTH — WHO IS THE SAME PERSON
# ============================================================
# This is our answer key. In a real system, human analysts
# create this by manually reviewing records.
# Format: list of sets — each set contains IDs of same person

GROUND_TRUTH_CLUSTERS = [
    {"OFAC-001", "UN-001", "EU-001"},   # Usama Bin Laden
    {"OFAC-002", "UN-002"},              # Moammar Gaddafi
    {"OFAC-003", "EU-002"},              # Hassan Al-Turabi
    {"OFAC-004", "UN-003", "EU-003"},   # Ali Hassan Al-Mari
    {"OFAC-005"},                        # Unique — no duplicates
    {"UN-004", "EU-004"},               # Abu Bakr Al-Baghdadi
    {"OFAC-006", "UN-005"},             # Fatima Al-Hassan
    {"OFAC-007"},                        # Unique — no duplicates
    {"EU-005", "UN-006"},               # Ahmed Khalil Ibrahim
    {"OFAC-008", "EU-006"},             # Muhammad Al-Zawahiri
]

# ============================================================
# SYNTHETIC SANCTIONS RECORDS
# ============================================================
# Each record represents one entry from one sanctions list
# Notice deliberate inconsistencies:
# - Different name spellings across sources
# - Missing fields on some records
# - DOB conflicts between sources
# - Different passport numbers (person got new passport)
# - Aliases stored differently across lists

SANCTIONS_RECORDS = [

    # ── CLUSTER 1: Usama Bin Laden ───────────────────────
    # Same person — three different sources, three spellings
    {
        "id":       "OFAC-001",
        "source":   "OFAC",
        "name":     "USAMA BIN LADEN",
        "aliases":  ["UBL", "Abu Abdullah"],
        "dob":      "1957-03-10",
        "country":  "Saudi Arabia",
        "passport": None,
        "notes":    "Primary OFAC entry"
    },
    {
        "id":       "UN-001",
        "source":   "UN",
        "name":     "OSAMA BIN LADIN",
        "aliases":  ["Osama bin Laden", "Abu Abdallah"],
        "dob":      "1957",           # UN only has year
        "country":  "Saudi Arabia",
        "passport": None,
        "notes":    "UN spelling variant"
    },
    {
        "id":       "EU-001",
        "source":   "EU",
        "name":     "OUSSAMA BEN LADEN",
        "aliases":  ["Oussama Ben Laden"],
        "dob":      "1957-03-10",
        "country":  "Saudi Arabia",
        "passport": None,
        "notes":    "EU French transliteration"
    },

    # ── CLUSTER 2: Moammar Gaddafi ───────────────────────
    # Two sources, different transliterations + DOB conflict
    {
        "id":       "OFAC-002",
        "source":   "OFAC",
        "name":     "MOAMMAR GADHAFI",
        "aliases":  ["Muammar Gaddafi", "Colonel Gaddafi"],
        "dob":      "1942-06-07",
        "country":  "Libya",
        "passport": "LY-1234567",
        "notes":    "OFAC primary entry"
    },
    {
        "id":       "UN-002",
        "source":   "UN",
        "name":     "MUAMMAR QADHAFI",
        "aliases":  ["Moammar Kadhafi"],
        "dob":      "1942",           # year only
        "country":  "Libya",
        "passport": None,             # passport unknown on UN list
        "notes":    "UN transliteration variant"
    },

    # ── CLUSTER 3: Hassan Al-Turabi ──────────────────────
    # Passport match despite name spelling difference
    {
        "id":       "OFAC-003",
        "source":   "OFAC",
        "name":     "HASSAN AL-TURABI",
        "aliases":  ["Hassan Abdallah al-Turabi"],
        "dob":      "1932-02-01",
        "country":  "Sudan",
        "passport": "SD-4421983",
        "notes":    "OFAC entry with passport"
    },
    {
        "id":       "EU-002",
        "source":   "EU",
        "name":     "HASAN AL-TURABI",
        "aliases":  ["Hassan al Turabi"],
        "dob":      "1933-02-01",     # one year different
        "country":  "Sudan",
        "passport": "SD-4421983",     # same passport confirms match
        "notes":    "EU entry — DOB conflict but passport matches"
    },

    # ── CLUSTER 4: Ali Hassan Al-Mari ────────────────────
    # Three sources, missing passport everywhere
    {
        "id":       "OFAC-004",
        "source":   "OFAC",
        "name":     "ALI HASSAN AL-MARI",
        "aliases":  ["Abu Ali", "Ali Al-Marri"],
        "dob":      None,             # DOB unknown
        "country":  "Qatar",
        "passport": None,
        "notes":    "OFAC entry — no DOB or passport"
    },
    {
        "id":       "UN-003",
        "source":   "UN",
        "name":     "ALI HASSAN AL-MARRI",
        "aliases":  ["Ali Al-Mari"],
        "dob":      None,
        "country":  "Qatar",
        "passport": None,
        "notes":    "UN spelling variant — all fields missing"
    },
    {
        "id":       "EU-003",
        "source":   "EU",
        "name":     "ALI HASAN AL-MARI",
        "aliases":  ["Ali Hassan"],
        "dob":      "1966",           # EU has partial DOB
        "country":  "Qatar",
        "passport": None,
        "notes":    "EU has year only — others have nothing"
    },

    # ── CLUSTER 5: Unique record (no cross-source match) ─
    {
        "id":       "OFAC-005",
        "source":   "OFAC",
        "name":     "IBRAHIM HASSAN MAHMOUD",
        "aliases":  [],
        "dob":      "1971-09-15",
        "country":  "Egypt",
        "passport": "EG-9876543",
        "notes":    "Unique — only on OFAC"
    },

    # ── CLUSTER 6: Abu Bakr Al-Baghdadi ──────────────────
    # Alias explosion — many known names
    {
        "id":       "UN-004",
        "source":   "UN",
        "name":     "ABU BAKR AL-BAGHDADI",
        "aliases":  [
            "Ibrahim Awad Ibrahim Al-Badri",
            "Abu Dua",
            "Dr. Ibrahim",
            "Caliph Ibrahim",
            "Al-Shabah"
        ],
        "dob":      "1971-07-28",
        "country":  "Iraq",
        "passport": None,
        "notes":    "UN entry with alias explosion"
    },
    {
        "id":       "EU-004",
        "source":   "EU",
        "name":     "IBRAHIM AWAD IBRAHIM AL-BADRI",
        "aliases":  ["Abu Bakr Al-Baghdadi", "Abu Dua"],
        "dob":      "1971",
        "country":  "Iraq",
        "passport": None,
        "notes":    "EU uses birth name not common name"
    },

    # ── CLUSTER 7: Fatima Al-Hassan (temporal drift) ─────
    # Name changed after marriage — tests temporal drift
    {
        "id":       "OFAC-006",
        "source":   "OFAC",
        "name":     "FATIMA AL-HASSAN",
        "aliases":  ["Fatima Hassan"],
        "dob":      "1985-04-12",
        "country":  "Lebanon",
        "passport": "LB-3345612",
        "notes":    "Listed under maiden name"
    },
    {
        "id":       "UN-005",
        "source":   "UN",
        "name":     "FATIMA AL-RASHIDI",    # married name
        "aliases":  ["Fatima Rashidi"],
        "dob":      "1985-04-12",
        "country":  "Lebanon",
        "passport": "LB-7789034",           # new passport after marriage
        "notes":    "UN updated with married name and new passport"
    },

    # ── CLUSTER 8: Unique record ─────────────────────────
    {
        "id":       "OFAC-007",
        "source":   "OFAC",
        "name":     "KHALID SHEIKH MOHAMMED",
        "aliases":  ["KSM", "Mukhtar Al-Baluchi"],
        "dob":      "1964-04-14",
        "country":  "Kuwait",
        "passport": "KW-5512348",
        "notes":    "Unique — only on OFAC"
    },

    # ── CLUSTER 9: Ahmed Khalil Ibrahim ──────────────────
    # Common name — tests many-to-many ambiguity
    {
        "id":       "EU-005",
        "source":   "EU",
        "name":     "AHMED KHALIL IBRAHIM",
        "aliases":  ["Ahmad Khalil"],
        "dob":      "1968-11-20",
        "country":  "Syria",
        "passport": "SY-2234891",
        "notes":    "EU entry"
    },
    {
        "id":       "UN-006",
        "source":   "UN",
        "name":     "AHMAD KHALEEL IBRAHIM",
        "aliases":  ["Ahmed Khalil"],
        "dob":      "1968",
        "country":  "Syria",
        "passport": None,
        "notes":    "UN transliteration — Khalil vs Khaleel"
    },

    # ── CLUSTER 10: Muhammad Al-Zawahiri ─────────────────
    # DOB conflict between sources
    {
        "id":       "OFAC-008",
        "source":   "OFAC",
        "name":     "MUHAMMAD AL-ZAWAHIRI",
        "aliases":  ["Mohammed Al-Zawahiri"],
        "dob":      "1960-09-03",
        "country":  "Egypt",
        "passport": "EG-1122334",
        "notes":    "OFAC primary entry"
    },
    {
        "id":       "EU-006",
        "source":   "EU",
        "name":     "MOHAMMED AL-ZAWAHIRI",
        "aliases":  ["Muhammad Zawahiri"],
        "dob":      "1961-09-03",     # one year different
        "country":  "Egypt",
        "passport": "EG-1122334",     # same passport
        "notes":    "EU — DOB conflict, passport confirms"
    },
]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_all_records():
    """Returns all synthetic sanctions records."""
    return SANCTIONS_RECORDS


def get_record_by_id(record_id):
    """Returns one record by its ID."""
    for record in SANCTIONS_RECORDS:
        if record["id"] == record_id:
            return record
    return None


def get_records_by_source(source):
    """
    Returns all records from one source.

    WHY THIS IS USEFUL:
    When we build the ingest layer, each source
    (OFAC, UN, EU) is processed separately.
    This simulates fetching from one source at a time.
    """
    return [r for r in SANCTIONS_RECORDS if r["source"] == source]


def get_true_matches_for(record_id):
    """
    Returns the IDs of all records that are the
    same person as the given record_id.

    WHY THIS IS IMPORTANT:
    This is our ground truth answer key.
    When we test our matching pipeline, we compare
    its output against this ground truth to measure
    precision and recall.
    """
    for cluster in GROUND_TRUTH_CLUSTERS:
        if record_id in cluster:
            # Return all OTHER records in same cluster
            return cluster - {record_id}
    return set()


def print_dataset_summary():
    """Prints a summary of the synthetic dataset."""
    print("=" * 55)
    print("SYNTHETIC SANCTIONS DATASET SUMMARY")
    print("=" * 55)
    print(f"Total records:    {len(SANCTIONS_RECORDS)}")
    print(f"Total clusters:   {len(GROUND_TRUTH_CLUSTERS)}")
    print()

    sources = {}
    for record in SANCTIONS_RECORDS:
        source = record["source"]
        sources[source] = sources.get(source, 0) + 1

    print("Records by source:")
    for source, count in sources.items():
        print(f"  {source}: {count} records")

    print()
    print("Clusters (same person across sources):")
    for i, cluster in enumerate(GROUND_TRUTH_CLUSTERS):
        size = len(cluster)
        ids  = ", ".join(sorted(cluster))
        print(f"  Cluster {i+1} ({size} records): {ids}")

    print()
    print("Tricky cases built in:")
    print("  - Transliteration variants (Usama/Osama/Oussama)")
    print("  - DOB conflicts (1932 vs 1933)")
    print("  - Missing fields (no DOB, no passport)")
    print("  - Alias explosion (Al-Baghdadi — 5 aliases)")
    print("  - Temporal drift (Fatima maiden vs married name)")
    print("  - Common name ambiguity (Ahmed Khalil Ibrahim)")
    print("  - Passport confirms despite name/DOB difference")


if __name__ == "__main__":
    print_dataset_summary()

    print()
    print("Sample lookups:")
    print()

    # Show ground truth for one record
    record = get_record_by_id("OFAC-001")
    matches = get_true_matches_for("OFAC-001")
    print(f"Record OFAC-001: {record['name']}")
    print(f"True matches:    {matches}")

    print()
    ofac_records = get_records_by_source("OFAC")
    print(f"OFAC has {len(ofac_records)} records")
    un_records = get_records_by_source("UN")
    print(f"UN has {len(un_records)} records")
    eu_records = get_records_by_source("EU")
    print(f"EU has {len(eu_records)} records")