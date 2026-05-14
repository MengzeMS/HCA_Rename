"""
Script to generate test fixtures:
  - config_files/master_config.xlsx  (master config with all required sheets)
  - tests/test_input_raw.csv         (raw test input)
  - tests/test_expected_output.csv   (expected cleaned output)

Run once: python tests/create_test_data.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

BASE = Path(__file__).parent.parent
CONFIG_DIR = BASE / "config_files"
TESTS_DIR = BASE / "tests"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
TESTS_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ #
# Master config sheets
# ------------------------------------------------------------------ #

indication_rule = pd.DataFrame(
    {
        "old_Indication": [
            " ",
            "  ",
            "1L CLL (in-Limitatio)  ",
            "1L CLL (off-Limitatio)",
            "1L CLL (off-Limitatio)  ",
            "ZZ - other  ",
            "ZZ - other",
            "Eosinophilic Asthma without exacerbations  ",
            "Eosinophilic Asthma without exacerbations",
            "Prostate Cancer (mCRPC) post NHA 2L BRCA+/ATM+ (PROfound)  ",
            "Prostate Cancer (mCRPC) post NHA 2L BRCA+/ATM+ (PROfound)",
            "Metastatic distal cholangiocarcinoma (TOPAZ-1)  ",
            "Metastatic Breast Cancer, HR+, HER2-, BRCA+ (OlympiAD)  ",
            "Adjuvant Breast Cancer, triple negative BRCA+ (OlympiA)  ",
            "ES SCLC 1L plus platinum–etoposide (CASPIAN)  ",
            "Advanced Ovarian Cancer 1L with Bev after platinum CTx+Bev (PAOLA-1)  ",
            "Ovarian Cancer, PSR 2L+  ",
            "Severe Asthma with exacerbations as add on  ",
            "Combination with Entresto  ",
            "Prostate Cancer  ",
            "Tezspire-off-Limitatio  ",
            "NSCLC EGFR+ 1L (Monotherapie) (FLAURA) (SL)  ",
        ],
        "new_Indication": [
            "Unknown",
            "Unknown",
            "1L CLL (in-Limitatio)",
            "1L CLL (off-Limitatio)",
            "1L CLL (off-Limitatio)",
            "Unknown",
            "Unknown",
            "Eosinophilic Asthma without exacerbations",
            "Eosinophilic Asthma without exacerbations",
            "PROfound",
            "PROfound",
            "TOPAZ-1",
            "OlympiAD",
            "OlympiA",
            "CASPIAN",
            "PAOLA-1",
            "Ovarian Cancer, PSR 2L+",
            "Severe Asthma with exacerbations as add on",
            "Combination with Entresto",
            "Prostate Cancer",
            "Tezspire-off-Limitatio",
            "FLAURA",
        ],
    }
)

dosage_rule = pd.DataFrame(
    {
        "Pack": [
            "FASENRA Inj Lös 30 mg/ml Fertspr",
            "LYNPARZA Filmtabl 150 mg",
            "FASENRA Pen Inj Lös 30 mg/ml",
            "TAGRISSO Filmtabl 80 mg",
            "FORXIGA Filmtabl 5 mg",
            "IMFINZI Inf Konz 500 mg/10ml",
            "CALQUENCE Kaps 100 mg",
            "TEZSPIRE Inj Lös 210 mg/1.91ml Fertspr",
            "IMFINZI Inf Konz 120 mg/2.4ml",
            "CALQUENCE Filmtabl 100 mg",
            "LYNPARZA Filmtabl 100 mg",
            "ZOLADEX LA SafeSystem 10.8 mg",
        ],
        "Dosage Amount": [30, 150, 30, 80, 5, 500, 100, 210, 120, 100, 100, 10.8],
    }
)

bu_rule = pd.DataFrame(
    {
        "Pack": [
            "FASENRA Inj Lös 30 mg/ml Fertspr",
            "LYNPARZA Filmtabl 150 mg",
            "FASENRA Pen Inj Lös 30 mg/ml",
            "TAGRISSO Filmtabl 80 mg",
            "FORXIGA Filmtabl 5 mg",
            "IMFINZI Inf Konz 500 mg/10ml",
            "CALQUENCE Kaps 100 mg",
            "TEZSPIRE Inj Lös 210 mg/1.91ml Fertspr",
            "IMFINZI Inf Konz 120 mg/2.4ml",
            "CALQUENCE Filmtabl 100 mg",
            "LYNPARZA Filmtabl 100 mg",
            "ZOLADEX LA SafeSystem 10.8 mg",
        ],
        "BU": [
            "BBU", "OBU", "BBU", "OBU", "BBU", "OBU",
            "OBU", "BBU", "OBU", "OBU", "OBU", "OBU",
        ],
    }
)

name_rule = pd.DataFrame(
    {
        "old_Service Provider": [
            "Fiechter & Partner. Aathal",
            "Apotheke Gelterkinden",
            "Spital STS, Thun",
            "Farmacia delle Semine SA",
            "KS Graubünden",
            "Dr. med. G. Rüttimann, Wohlen",
            "Dr. med. M. Reichlin, Zürich",
            "Tucare AG, Dietikon",
            "Luzerner Kantonsspital",
            "Dr. med. S. Balli, Solothurn",
            "Fiechter & Partner, Aathal",
            "KS St. Gallen",
            "Dr.med. E. Müller, Zürich",
            "Tucare AG",
            "KS Baselland, Liestal",
            "Loë Apotheke, Chur",
            "Kantonsspital St. Gallen",
            "Spitalregion Fürstenland Toggenburg",
        ],
        "new_Service Provider": [
            "Fiechter & Partner",
            "Apotheke Gelterkinden",
            "Spital STS",
            "Farmacia delle Semine",
            "Kantonsspital Graubünden",
            "Lungenpraxis Wohlen",
            "Sanacare Gruppenpraxis St. Gallen",
            "Tucare",
            "LUKS",
            "Groupe Médical de la Gare",
            "Fiechter & Partner",
            "HOCH",
            "Praxis Dr. med. Müller Erich",
            "Tucare",
            "Kantonsspital Baselland",
            "Loë Apotheke",
            "HOCH",
            "HOCH",
        ],
    }
)

hcp_universe = pd.DataFrame(
    {
        "HCA": [
            "Feldenkraislehrerin SFV",
            "Shiatsu und Energiearbeit",
            "Alterswohnheim Büttenberg",
            "Gygax Anni, Krankenpflegerin",
            "Fachschwester",
            "Gemeindekrankenpflege",
            "Marchon Marguerite, Dipl. Hauspflegerin",
            "dipl. Krankenschwester",
            "Gemeindekrankenpflege",
            "Schaub Rosmarie, Gemeindekrankenschwester",
            "Lungenpraxis Wohlen",
            "Praxis Dr. med. Müller Erich",
            "Sanacare Gruppenpraxis St. Gallen",
        ],
        "LastName_c": [
            "Rytz", "König - Kurth", "Djuranovic", "Gygax", "Fasel",
            "Howald", "Marchon", "Reber", "Rieger", "Schaub",
            "Rüttimann", "Müller", "Reichlin",
        ],
        "FirstName_c": [
            "Annemarie", "Heidy", "Jozefina", "Anni", "Anneliese",
            "Hanni", "Marguerite", "Klara", "Emma", "Rosmarie",
            "Gottfried", "Erich", "Martin",
        ],
    }
)

# Write master_config.xlsx
master_path = CONFIG_DIR / "master_config.xlsx"
with pd.ExcelWriter(master_path, engine="openpyxl") as writer:
    indication_rule.to_excel(writer, sheet_name="indication_rule", index=False)
    dosage_rule.to_excel(writer, sheet_name="dosage_rule", index=False)
    bu_rule.to_excel(writer, sheet_name="BU_rule", index=False)
    name_rule.to_excel(writer, sheet_name="name_rule", index=False)
    hcp_universe.to_excel(writer, sheet_name="HCP_universe_2026_April", index=False)

print(f"✓ Written: {master_path}")

# ------------------------------------------------------------------ #
# Raw test input CSV
# ------------------------------------------------------------------ #

raw_input = pd.DataFrame(
    {
        "Insurance ID":         ["AGS"] * 8,
        "Insurance carrier":    [" "] * 8,
        "Invoice-ID":           ["AGS-ASZ-I0001"] * 8,
        "Invoice Type":         ["Article71"] * 8,
        "Patient-ID":           [178205, 178205, 216073, 216073, 21878, 228410, 295756, 548006],
        "Patient ID insurance": [178205, 178205, 216073, 216073, 21878, 228410, 295756, 548006],
        "Brand": [
            "Fasenra", "Fasenra", "Lynparza", "Lynparza",
            "Lynparza", "Fasenra Pen", "Fasenra Pen", "Fasenra",
        ],
        "Indication Code": [""] * 8,
        "Indication": [
            "Eosinophilic Asthma without exacerbations  ",
            "Eosinophilic Asthma without exacerbations  ",
            "ZZ - other  ",
            "ZZ - other  ",
            "Prostate Cancer (mCRPC) post NHA 2L BRCA+/ATM+ (PROfound)  ",
            "ZZ - other  ",
            "ZZ - other  ",
            "ZZ - other  ",
        ],
        "Indication original": [
            "Astma bronchiale", "Astma bronchiale",
            "High-grade seröses Ovarial-CA FIGO IIIX R1",
            "High-grade seröses Ovarial-CA FIGO IIIX R1",
            "Metastasiertes Prostata-CA",
            "Eosinophile Pneumonie",
            "Klein-lymphozytisches Lymphom",
            "Eosinophiles late onset Asthma bronchiale",
        ],
        "Service Provider": [
            "Fiechter & Partner. Aathal",
            "Fiechter & Partner. Aathal",
            "Apotheke Gelterkinden",
            "Apotheke Gelterkinden",
            "Spital STS, Thun",
            "Farmacia delle Semine SA",
            "KS Graubünden",
            "Dr. med. G. Rüttimann, Wohlen",
        ],
        "Pack": [
            "FASENRA Inj Lös 30 mg/ml Fertspr",
            "FASENRA Inj Lös 30 mg/ml Fertspr",
            "LYNPARZA Filmtabl 150 mg",
            "LYNPARZA Filmtabl 150 mg",
            "LYNPARZA Filmtabl 150 mg",
            "FASENRA Pen Inj Lös 30 mg/ml",
            "FASENRA Pen Inj Lös 30 mg/ml",
            "FASENRA Inj Lös 30 mg/ml Fertspr",
        ],
        "Invoice Date": ["02.09.2022"] * 8,
        "Treatment Date": [
            "28.03.2022", "21.04.2022", "11.02.2022", "21.03.2022",
            "07.03.2022", "18.01.2022", "17.02.2022", "16.11.2021",
        ],
        "Amount": [1, 1, 1, 1, 3, 1, 1, 1],
        "Price basis": ["PP"] * 8,
        "Price total": [
            "2319.39 CHF", "2319.39 CHF", "4989.53 CHF", "4989.53 CHF",
            "14968.59 CHF", "2319.39 CHF", "2319.39 CHF", "2319.39 CHF",
        ],
        "Discount total": [
            "521.06 CHF", "521.06 CHF", "1072.05 CHF", "1072.05 CHF",
            "3216.15 CHF", "521.06 CHF", "521.06 CHF", "521.06 CHF",
        ],
        "Discount %": [
            "22.47 %", "22.47 %", "21.49 %", "21.49 %",
            "21.49 %", "22.47 %", "22.47 %", "22.47 %",
        ],
        "Art 71 Rating": ["A", "A", "A", "A", "B", "B", "B", "B"],
        "Line Invoice": [12, 13, 10, 11, 9, 5, 8, 6],
        "Invoice status": ["Paid"] * 8,
    }
)

raw_input_path = TESTS_DIR / "test_input_raw.csv"
raw_input.to_csv(raw_input_path, index=False, encoding="utf-8")
print(f"✓ Written: {raw_input_path}")

# ------------------------------------------------------------------ #
# Expected output CSV
# ------------------------------------------------------------------ #

expected_output = pd.DataFrame(
    {
        "RowID": [1, 2, 3, 4, 5, 6, 7, 8],
        "Insurance ID": ["AGS"] * 8,
        "Insurance carrier": [" "] * 8,
        "Invoice-ID": ["AGS-ASZ-I0001"] * 8,
        "Invoice Type": ["Article71"] * 8,
        "Patient-ID": [178205, 178205, 216073, 216073, 21878, 228410, 295756, 548006],
        "Patient ID insurance": [178205, 178205, 216073, 216073, 21878, 228410, 295756, 548006],
        "Brand": [
            "Fasenra", "Fasenra", "Lynparza", "Lynparza",
            "Lynparza", "Fasenra Pen", "Fasenra Pen", "Fasenra",
        ],
        "Indication Code": [""] * 8,
        "Indication": [
            "Eosinophilic Asthma without exacerbations",
            "Eosinophilic Asthma without exacerbations",
            "Unknown",
            "Unknown",
            "PROfound",
            "Unknown",
            "Unknown",
            "Unknown",
        ],
        "Indication original": [
            "Astma bronchiale", "Astma bronchiale",
            "High-grade seröses Ovarial-CA FIGO IIIX R1",
            "High-grade seröses Ovarial-CA FIGO IIIX R1",
            "Metastasiertes Prostata-CA",
            "Eosinophile Pneumonie",
            "Klein-lymphozytisches Lymphom",
            "Eosinophiles late onset Asthma bronchiale",
        ],
        "Service Provider": [
            "Fiechter & Partner",
            "Fiechter & Partner",
            "Apotheke Gelterkinden",
            "Apotheke Gelterkinden",
            "Spital STS",
            "Farmacia delle Semine",
            "Kantonsspital Graubünden",
            "Lungenpraxis Wohlen",
        ],
        "Pack": [
            "FASENRA Inj Lös 30 mg/ml Fertspr",
            "FASENRA Inj Lös 30 mg/ml Fertspr",
            "LYNPARZA Filmtabl 150 mg",
            "LYNPARZA Filmtabl 150 mg",
            "LYNPARZA Filmtabl 150 mg",
            "FASENRA Pen Inj Lös 30 mg/ml",
            "FASENRA Pen Inj Lös 30 mg/ml",
            "FASENRA Inj Lös 30 mg/ml Fertspr",
        ],
        "Invoice Date": ["02.09.2022"] * 8,
        "Treatment Date": [
            "28.03.2022", "21.04.2022", "11.02.2022", "21.03.2022",
            "07.03.2022", "18.01.2022", "17.02.2022", "16.11.2021",
        ],
        "Amount": [1, 1, 1, 1, 3, 1, 1, 1],
        "Price basis": ["PP"] * 8,
        "Price total": [
            "2319.39 CHF", "2319.39 CHF", "4989.53 CHF", "4989.53 CHF",
            "14968.59 CHF", "2319.39 CHF", "2319.39 CHF", "2319.39 CHF",
        ],
        "Discount total": [
            "521.06 CHF", "521.06 CHF", "1072.05 CHF", "1072.05 CHF",
            "3216.15 CHF", "521.06 CHF", "521.06 CHF", "521.06 CHF",
        ],
        "Discount %": [
            "22.47 %", "22.47 %", "21.49 %", "21.49 %",
            "21.49 %", "22.47 %", "22.47 %", "22.47 %",
        ],
        "Art 71 Rating": ["A", "A", "A", "A", "B", "B", "B", "B"],
        "Line Invoice": [12, 13, 10, 11, 9, 5, 8, 6],
        "Invoice status": ["Paid"] * 8,
        "Dosage Amount": ["30", "30", "150", "150", "150", "30", "30", "30"],
        "BU": ["BBU", "BBU", "OBU", "OBU", "OBU", "BBU", "BBU", "BBU"],
    }
)

expected_path = TESTS_DIR / "test_expected_output.csv"
expected_output.to_csv(expected_path, index=False, encoding="utf-8")
print(f"✓ Written: {expected_path}")

print("\nAll test fixtures created successfully.")
