# src/ingest.py
#
# WHY THIS FILE EXISTS:
# All previous work used synthetic data we created manually.
# This file downloads REAL sanctions data from official
# government sources and converts it into the same format
# our pipeline already understands.
#
# WHAT THIS FILE DOES:
# 1. Downloads OFAC SDN XML from US Treasury website
# 2. Parses the XML structure into Python dictionaries
# 3. Normalises fields to match our synthetic record format
# 4. Saves to data/ofac_records.json for reuse
#
# WHY XML:
# OFAC publishes their list as XML — a structured format
# where data is wrapped in tags like HTML.
# Example:
# <sdnEntry>
#   <firstName>OSAMA</firstName>
#   <lastName>BIN LADEN</lastName>
#   <dob>1957</dob>
# </sdnEntry>
#
# WHY SAVE TO JSON:
# Downloading 10MB every time is slow and puts load
# on government servers. We download once, save locally,
# load from disk on every subsequent run.
# This is called CACHING.
#
# REAL OFAC URL:
# https://sanctionslist.ofac.treas.gov/Home/DownloadFile?type=sdnXml

import requests
import xml.etree.ElementTree as ET
import json
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(__file__))


# ============================================================
# OFAC XML STRUCTURE
# ============================================================
# The OFAC SDN XML has this structure:
#
# <sdnList>
#   <sdnEntry>
#     <uid>1234</uid>
#     <lastName>BIN LADEN</lastName>
#     <firstName>USAMA</firstName>
#     <sdnType>Individual</sdnType>
#     <akaList>
#       <aka>
#         <uid>5678</uid>
#         <type>a.k.a.</type>
#         <lastName>BIN LADIN</lastName>
#         <firstName>OSAMA</firstName>
#       </aka>
#     </akaList>
#     <dobList>
#       <dob>
#         <uid>9012</uid>
#         <dobDate>1957</dobDate>
#       </dob>
#     </dobList>
#     <citizenshipList>
#       <citizenship>
#         <uid>3456</uid>
#         <country>Saudi Arabia</country>
#       </citizenship>
#     </citizenshipList>
#     <idList>
#       <id>
#         <uid>7890</uid>
#         <idType>Passport</idType>
#         <idNumber>A1234567</idNumber>
#       </id>
#     </idList>
#   </sdnEntry>
# </sdnList>

# OFAC XML namespace — required for parsing
# WHY NAMESPACE:
# OFAC XML uses a namespace prefix on all tags.
# Without specifying it, ET.find() returns nothing.
OFAC_NAMESPACE = '{https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML}'


# ============================================================
# DOWNLOAD
# ============================================================

def download_ofac_xml(save_path="data/ofac_sdn.xml"):
    """
    Downloads the OFAC SDN list XML file.

    WHY SAVE RAW XML:
    We always keep the original downloaded file.
    If our parser has a bug — we can reparse without
    re-downloading. Raw data is never thrown away.

    Returns True if successful, False if failed.
    """
    url = "https://www.treasury.gov/ofac/downloads/sdn.xml"

    print(f"Downloading OFAC SDN list from:")
    print(f"  {url}")
    print()

    try:
        # stream=True — download in chunks not all at once
        # WHY: file is ~10MB — streaming prevents memory issues
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        # Create data directory if it does not exist
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Write file in chunks
        total_bytes = 0
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                total_bytes += len(chunk)

        size_mb = total_bytes / (1024 * 1024)
        print(f"Downloaded: {size_mb:.1f} MB")
        print(f"Saved to:   {save_path}")
        return True

    except requests.exceptions.Timeout:
        print("ERROR: Download timed out after 60 seconds")
        print("Check your internet connection")
        return False

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Download failed — {e}")
        return False


# ============================================================
# PARSE
# ============================================================

def parse_ofac_xml(xml_path="data/ofac_sdn.xml"):
    """
    Parses OFAC SDN XML into list of record dictionaries.

    Converts XML structure into our standard format:
    {
        'id':       'OFAC-12345',
        'source':   'OFAC',
        'name':     'USAMA BIN LADEN',
        'aliases':  ['OSAMA BIN LADIN', ...],
        'dob':      '1957',
        'country':  'Saudi Arabia',
        'passport': 'A1234567',
        'notes':    'sdnType: Individual'
    }

    WHY MATCH OUR FORMAT:
    Our pipeline — blocking, scoring, graph — all expect
    records in this format. By converting OFAC data to
    the same format, we can run the full pipeline on
    real data without changing any other file.
    This is called the ADAPTER PATTERN.
    """
    print(f"Parsing XML from: {xml_path}")

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"ERROR: XML parsing failed — {e}")
        return []
    except FileNotFoundError:
        print(f"ERROR: File not found — {xml_path}")
        return []

    records = []
    ns      = OFAC_NAMESPACE

    # Find all sdnEntry elements
    entries = root.findall(f"{ns}sdnEntry")
    print(f"Found {len(entries)} entries in XML")
    print("Parsing...")

    for entry in entries:

        # ── Basic fields ──────────────────────────────────
        uid      = entry.findtext(f"{ns}uid", "")
        last_name  = entry.findtext(f"{ns}lastName", "")
        first_name = entry.findtext(f"{ns}firstName", "")
        sdn_type   = entry.findtext(f"{ns}sdnType", "")

        # Build full name — last name first for individuals
        # WHY: OFAC stores names as lastName + firstName
        if first_name:
            full_name = f"{first_name} {last_name}".strip()
        else:
            full_name = last_name.strip()

        if not full_name:
            continue  # skip entries with no name

        # ── Aliases ───────────────────────────────────────
        aliases    = []
        aka_list   = entry.find(f"{ns}akaList")
        if aka_list is not None:
            for aka in aka_list.findall(f"{ns}aka"):
                aka_last  = aka.findtext(f"{ns}lastName", "")
                aka_first = aka.findtext(f"{ns}firstName", "")
                aka_type  = aka.findtext(f"{ns}type", "")

                if aka_first:
                    aka_name = f"{aka_first} {aka_last}".strip()
                else:
                    aka_name = aka_last.strip()

                if aka_name and aka_name != full_name:
                    aliases.append(aka_name)

   # ── Date of birth ─────────────────────────────────
        # WHY DIFFERENT TAG NAMES:
        # OFAC changed their XML schema.
        # Real tag is dateOfBirthList → dateOfBirthItem → dateOfBirth
        # Format: "10 Dec 1948" — we extract year only for consistency
        dob = None
        dob_list = entry.find(f"{ns}dateOfBirthList")
        if dob_list is not None:
            dob_elem = dob_list.find(f"{ns}dateOfBirthItem")
            if dob_elem is not None:
                dob_raw = dob_elem.findtext(f"{ns}dateOfBirth")
                if dob_raw:
                    # Extract year from "10 Dec 1948" format
                    # WHY YEAR ONLY: different entries have different
                    # precision — some have full date, some year only
                    # Year is most reliable common denominator
                    parts = dob_raw.strip().split()
                    for part in parts:
                        if len(part) == 4 and part.isdigit():
                            dob = part
                            break
                    # If no 4-digit year found — store raw value
                    if not dob:
                        dob = dob_raw.strip()

        # ── Country / Citizenship ─────────────────────────
        country           = None
        citizenship_list  = entry.find(f"{ns}citizenshipList")
        if citizenship_list is not None:
            citizenship = citizenship_list.find(
                f"{ns}citizenship"
            )
            if citizenship is not None:
                country = citizenship.findtext(
                    f"{ns}country"
                )

        # Also check nationality list if no citizenship
        if not country:
            nationality_list = entry.find(
                f"{ns}nationalityList"
            )
            if nationality_list is not None:
                nationality = nationality_list.find(
                    f"{ns}nationality"
                )
                if nationality is not None:
                    country = nationality.findtext(
                        f"{ns}country"
                    )

        # ── Passport / ID ─────────────────────────────────
        passport  = None
        id_list   = entry.find(f"{ns}idList")
        if id_list is not None:
            for id_elem in id_list.findall(f"{ns}id"):
                id_type = id_elem.findtext(
                    f"{ns}idType", ""
                ).lower()
                # Look for passport specifically
                if "passport" in id_type:
                    passport = id_elem.findtext(
                        f"{ns}idNumber"
                    )
                    break

        # ── Build record ──────────────────────────────────
        record = {
            'id':       f"OFAC-{uid}",
            'source':   'OFAC',
            'name':     full_name.upper(),
            'aliases':  aliases,
            'dob':      dob,
            'country':  country,
            'passport': passport,
            'notes':    f"sdnType: {sdn_type}",
        }

        records.append(record)

    print(f"Successfully parsed: {len(records)} records")
    return records


# ============================================================
# SAVE AND LOAD
# ============================================================

def save_records(records, save_path="data/ofac_records.json"):
    """
    Saves parsed records to JSON file.

    WHY JSON not CSV:
    Our records have nested lists (aliases).
    CSV cannot store nested data cleanly.
    JSON handles nested structures natively.

    WHY SAVE AT ALL:
    Parsing 12,000 XML entries takes a few seconds.
    Downloading takes 30-60 seconds.
    Saving to JSON means: download once, parse once,
    load instantly on every subsequent run.
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    size_kb = os.path.getsize(save_path) / 1024
    print(f"Saved {len(records)} records to: {save_path}")
    print(f"File size: {size_kb:.0f} KB")


def load_records(load_path="data/ofac_records.json"):
    """
    Loads previously saved records from JSON.

    WHY THIS FUNCTION:
    Other files (pipeline.py, blocking.py) can call
    load_records() to get real OFAC data without
    knowing anything about XML or downloading.
    Clean separation of concerns.
    """
    if not os.path.exists(load_path):
        print(f"No cached records found at: {load_path}")
        print("Run ingest.py first to download and parse")
        return []

    with open(load_path, 'r', encoding='utf-8') as f:
        records = json.load(f)

    print(f"Loaded {len(records)} records from: {load_path}")
    return records


# ============================================================
# MAIN — DOWNLOAD, PARSE, SAVE, REPORT
# ============================================================

if __name__ == "__main__":

    print("=" * 55)
    print("OFAC SDN LIST INGEST")
    print("=" * 55)
    print()
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Download
    print("STEP 1: DOWNLOAD")
    print("-" * 55)
    success = download_ofac_xml("data/ofac_sdn.xml")

    if not success:
        print()
        print("Download failed. Cannot continue.")
        print("Check internet connection and try again.")
        sys.exit(1)

    # Step 2: Parse
    print()
    print("STEP 2: PARSE")
    print("-" * 55)
    records = parse_ofac_xml("data/ofac_sdn.xml")

    if not records:
        print("Parsing produced no records.")
        print("Check the XML file and namespace.")
        sys.exit(1)

    # Step 3: Save
    print()
    print("STEP 3: SAVE")
    print("-" * 55)
    save_records(records, "data/ofac_records.json")

    # Step 4: Report
    print()
    print("=" * 55)
    print("INGEST SUMMARY")
    print("=" * 55)

    # Count fields present
    with_dob      = sum(1 for r in records if r['dob'])
    with_country  = sum(1 for r in records if r['country'])
    with_passport = sum(1 for r in records if r['passport'])
    with_aliases  = sum(1 for r in records if r['aliases'])

    print(f"Total records:        {len(records)}")
    print(f"With DOB:             {with_dob}"
          f" ({with_dob/len(records)*100:.0f}%)")
    print(f"With country:         {with_country}"
          f" ({with_country/len(records)*100:.0f}%)")
    print(f"With passport:        {with_passport}"
          f" ({with_passport/len(records)*100:.0f}%)")
    print(f"With aliases:         {with_aliases}"
          f" ({with_aliases/len(records)*100:.0f}%)")

    print()
    print("SAMPLE RECORDS:")
    print()
    for record in records[:3]:
        print(f"  ID:       {record['id']}")
        print(f"  Name:     {record['name']}")
        print(f"  Aliases:  {record['aliases'][:2]}")
        print(f"  DOB:      {record['dob']}")
        print(f"  Country:  {record['country']}")
        print(f"  Passport: {record['passport']}")
        print()

    print(f"Finished: "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("Real OFAC data ready.")
    print("Run pipeline.py to screen against real data.")