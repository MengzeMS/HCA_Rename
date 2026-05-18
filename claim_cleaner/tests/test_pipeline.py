"""
Pipeline integration tests and unit tests.

Run from claim_cleaner/ directory:
    python -m pytest tests/test_pipeline.py -v
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure imports resolve from claim_cleaner/
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_manager import MasterConfig, ConfigError
from pipeline.step_indication import IndicationStep
from pipeline.step_provider import ProviderStep
from pipeline.step_dosage import DosageStep
from pipeline.step_bu import BUStep
from pipeline.orchestrator import run_pipeline
from pipeline.utils import load_input_file, InputError, REQUIRED_COLUMNS
from matching.normalizer import post_match_cleanup, remove_legal_suffixes, normalize_for_fuzzy
from matching.cell_parser import parse_segments
from matching.exact_match import ExactMatcher
from matching.name_match import NameMatcher, _strip_titles
from matching.fuzzy_match import FuzzyMatcher

# ------------------------------------------------------------------ #
# Fixture paths
# ------------------------------------------------------------------ #

BASE = Path(__file__).parent.parent
MASTER_CONFIG_PATH = BASE / "config_files" / "master_config.xlsx"
RAW_INPUT_PATH = BASE / "tests" / "test_input_raw.csv"
EXPECTED_OUTPUT_PATH = BASE / "tests" / "test_expected_output.csv"
ALT_INPUT_PATH = BASE / "tests" / "test_alt_input.csv"
ALT_EXPECTED_PATH = BASE / "tests" / "test_alt_expected.csv"


@pytest.fixture(scope="module")
def config() -> MasterConfig:
    if not MASTER_CONFIG_PATH.exists():
        pytest.skip("master_config.xlsx not found — run tests/create_test_data.py first")
    return MasterConfig(MASTER_CONFIG_PATH)


# ================================================================== #
# Config loading tests
# ================================================================== #

class TestConfigLoading:
    def test_loads_successfully(self, config: MasterConfig) -> None:
        assert config.indication_rules is not None
        assert len(config.indication_rules) > 0

    def test_all_sheets_present(self, config: MasterConfig) -> None:
        assert len(config.name_rules) > 0
        assert len(config.dosage_rules) > 0
        assert len(config.bu_rules) > 0
        assert len(config.hcp_universe) > 0

    def test_hcp_sheet_name(self, config: MasterConfig) -> None:
        assert config.hcp_sheet_name.startswith("HCP_universe")

    def test_missing_file_raises(self) -> None:
        with pytest.raises(ConfigError):
            MasterConfig("/nonexistent/path/master.xlsx")


# ================================================================== #
# Indication step tests
# ================================================================== #

class TestIndicationStep:
    @pytest.fixture(autouse=True)
    def setup(self, config: MasterConfig) -> None:
        self.step = IndicationStep(config.indication_rules)

    def test_exact_match_with_trailing_spaces(self) -> None:
        # Raw value has trailing spaces — exact match expected
        assert self.step.transform("Eosinophilic Asthma without exacerbations  ") == \
               "Eosinophilic Asthma without exacerbations"

    def test_zz_other_maps_to_unknown(self) -> None:
        assert self.step.transform("ZZ - other  ") == "Unknown"
        assert self.step.transform("ZZ - other") == "Unknown"

    def test_profound_mapping(self) -> None:
        raw = "Prostate Cancer (mCRPC) post NHA 2L BRCA+/ATM+ (PROfound)  "
        assert self.step.transform(raw) == "PROfound"

    def test_blank_maps_to_unknown(self) -> None:
        assert self.step.transform("") == "Unknown"
        assert self.step.transform("   ") == "Unknown"

    def test_unrecognized_kept_trimmed(self) -> None:
        assert self.step.transform("  Some weird value  ") == "Some weird value"

    def test_topaz1_mapping(self) -> None:
        raw = "Metastatic distal cholangiocarcinoma (TOPAZ-1)  "
        assert self.step.transform(raw) == "TOPAZ-1"


# ================================================================== #
# Provider step tests
# ================================================================== #

class TestExactMatcher:
    @pytest.fixture(autouse=True)
    def setup(self, config: MasterConfig) -> None:
        self.matcher = ExactMatcher(config.name_rules)

    def test_exact_match(self) -> None:
        assert self.matcher.match("Fiechter & Partner. Aathal") == "Fiechter & Partner"

    def test_no_match_returns_none(self) -> None:
        assert self.matcher.match("Totally Unknown Provider XYZ") is None

    def test_ks_graubuenden(self) -> None:
        assert self.matcher.match("KS Graubünden") == "Kantonsspital Graubünden"

    def test_farmacia_sa(self) -> None:
        assert self.matcher.match("Farmacia delle Semine SA") == "Farmacia delle Semine"

    def test_spital_thurgau_ag(self) -> None:
        assert self.matcher.match("Spital Thurgau AG") == "Spital Thurgau"


class TestNameMatcher:
    @pytest.fixture(autouse=True)
    def setup(self, config: MasterConfig) -> None:
        self.matcher = NameMatcher(config.hcp_universe)

    def test_abbreviated_first_name(self) -> None:
        # "Dr. med. G. Rüttimann, Wohlen" → after segment parsing → "Dr. med. G. Rüttimann"
        # Abbreviated: G matches Gottfried, Rüttimann matches
        result = self.matcher.match("G. Rüttimann")
        assert result == "Lungenpraxis Wohlen"

    def test_full_name_match(self) -> None:
        result = self.matcher.match("Gottfried Rüttimann")
        assert result == "Lungenpraxis Wohlen"

    def test_no_match_for_institution(self) -> None:
        # Institution keywords → not a person
        result = self.matcher.match("Kantonsspital Bern")
        assert result is None


class TestProviderStep:
    @pytest.fixture(autouse=True)
    def setup(self, config: MasterConfig) -> None:
        self.step = ProviderStep(config.name_rules, config.hcp_universe, fuzzy_threshold=2)
        self.step.build_code_mapping(pd.Series([]))

    def test_empty_value(self) -> None:
        result = self.step.process_row("")
        assert result.match_type == "empty"
        assert result.cleaned == "Unknown"

    def test_question_mark(self) -> None:
        result = self.step.process_row("?")
        assert result.match_type == "empty"

    def test_leer(self) -> None:
        result = self.step.process_row("leer")
        assert result.match_type == "empty"

    def test_exact_override(self) -> None:
        result = self.step.process_row("Fiechter & Partner. Aathal")
        assert result.match_type == "exact-override"
        assert result.cleaned == "Fiechter & Partner"

    def test_exact_override_with_sa(self) -> None:
        result = self.step.process_row("Farmacia delle Semine SA")
        assert result.match_type == "exact-override"
        assert result.cleaned == "Farmacia delle Semine"

    def test_exact_with_comma_location(self) -> None:
        result = self.step.process_row("Spital STS, Thun")
        assert result.match_type == "exact-override"
        assert result.cleaned == "Spital STS"

    def test_doctor_name_resolves(self) -> None:
        result = self.step.process_row("Dr. med. G. Rüttimann, Wohlen")
        assert result.match_type == "exact-override"
        assert result.cleaned == "Lungenpraxis Wohlen"

    def test_spital_thurgau_ag_resolves(self) -> None:
        result = self.step.process_row("Spital Thurgau AG")
        assert result.match_type == "exact-override"
        assert result.cleaned == "Spital Thurgau"


# ================================================================== #
# Dosage step tests
# ================================================================== #

class TestDosageStep:
    @pytest.fixture(autouse=True)
    def setup(self, config: MasterConfig) -> None:
        self.step = DosageStep(config.dosage_rules)

    def test_exact_match(self) -> None:
        assert self.step._extract("FASENRA Inj Lös 30 mg/ml Fertspr") == "30"

    def test_lynparza_150(self) -> None:
        assert self.step._extract("LYNPARZA Filmtabl 150 mg") == "150"

    def test_regex_fallback(self) -> None:
        # Not in table, but contains mg
        assert self.step._extract("SomeDrug 75 mg Filmtabl") == "75"

    def test_no_match_blank(self) -> None:
        assert self.step._extract("UnknownDrug") == ""

    def test_decimal_dosage(self) -> None:
        assert self.step._extract("ZOLADEX LA SafeSystem 10.8 mg") == "10.8"

    def test_imfinzi_500(self) -> None:
        assert self.step._extract("IMFINZI Inf Konz 500 mg/10ml") == "500"


# ================================================================== #
# BU step tests
# ================================================================== #

class TestBUStep:
    @pytest.fixture(autouse=True)
    def setup(self, config: MasterConfig) -> None:
        self.step = BUStep(config.bu_rules)

    def test_fasenra_bbu(self) -> None:
        assert self.step._assign("FASENRA Inj Lös 30 mg/ml Fertspr") == "BBU"

    def test_lynparza_obu(self) -> None:
        assert self.step._assign("LYNPARZA Filmtabl 150 mg") == "OBU"

    def test_unknown_pack(self) -> None:
        assert self.step._assign("Unknown Pack XYZ") == "Unknown BU"

    def test_imfinzi_obu(self) -> None:
        assert self.step._assign("IMFINZI Inf Konz 500 mg/10ml") == "OBU"


# ================================================================== #
# Normalizer tests
# ================================================================== #

class TestNormalizer:
    def test_remove_ag(self) -> None:
        assert remove_legal_suffixes("Farmacia delle Semine SA") == "Farmacia delle Semine"

    def test_remove_gmbh(self) -> None:
        assert remove_legal_suffixes("Some Company GmbH") == "Some Company"

    def test_remove_ag_case(self) -> None:
        assert remove_legal_suffixes("Tucare AG") == "Tucare"

    def test_post_cleanup_removes_location_after_comma(self) -> None:
        result = post_match_cleanup("Spital STS, Thun")
        assert result == "Spital STS"

    def test_post_cleanup_pharmacy_keeps_location(self) -> None:
        # Pharmacies should keep location after comma
        result = post_match_cleanup("Loë Apotheke, Chur")
        assert "Apotheke" in result

    def test_hoch_mapping(self) -> None:
        result = post_match_cleanup("Kantonsspital St. Gallen")
        assert result == "HOCH"

    def test_bilingual_bienne_to_biel(self) -> None:
        result = post_match_cleanup("Spital Bienne")
        assert "Biel" in result


# ================================================================== #
# Cell parser tests
# ================================================================== #

class TestCellParser:
    def test_multiline_filters_address(self) -> None:
        raw = "Dr. Smith\n8805 Richterswil"
        segs = parse_segments(raw)
        assert "Dr. Smith" in segs
        assert not any("8805" in s for s in segs)

    def test_comma_split(self) -> None:
        segs = parse_segments("Dr. Müller, Zürich")
        assert len(segs) >= 1
        assert "Dr. Müller" in segs[0] or any("Müller" in s for s in segs)

    def test_single_value_returned_as_is(self) -> None:
        segs = parse_segments("Apotheke Gelterkinden")
        assert segs == ["Apotheke Gelterkinden"]

    def test_empty_returns_empty(self) -> None:
        assert parse_segments("") == []


# ================================================================== #
# Flexible column schema tests
# ================================================================== #

class TestFlexibleColumns:
    """Verify the pipeline handles flexible input column schemas."""

    def test_only_three_required_columns(self) -> None:
        """Only Indication, Service Provider, Pack are required."""
        assert set(REQUIRED_COLUMNS) == {"Indication", "Service Provider", "Pack"}
        assert len(REQUIRED_COLUMNS) == 3

    def test_extra_columns_pass_through(self, config: MasterConfig, tmp_path: Path) -> None:
        """Extra columns not in standard schema are preserved in output."""
        if not ALT_INPUT_PATH.exists():
            pytest.skip("test_alt_input.csv not found — run tests/create_test_data.py first")

        input_copy = tmp_path / "test_alt_input.csv"
        shutil.copy(ALT_INPUT_PATH, input_copy)

        result = run_pipeline(
            input_path=input_copy,
            config=config,
            fuzzy_threshold=2,
        )

        actual = pd.read_csv(result["output_path"], dtype=str)
        # Extra columns should be present
        assert "Smart MIPID" in actual.columns
        assert "Documentstatus" in actual.columns

    def test_missing_optional_columns_ok(self, config: MasterConfig, tmp_path: Path) -> None:
        """Missing non-required columns don't raise errors."""
        if not ALT_INPUT_PATH.exists():
            pytest.skip("test_alt_input.csv not found — run tests/create_test_data.py first")

        input_copy = tmp_path / "test_alt_input_missing.csv"
        shutil.copy(ALT_INPUT_PATH, input_copy)

        # Should not raise — missing "Price basis" and "Art 71 Rating" are fine
        result = run_pipeline(
            input_path=input_copy,
            config=config,
            fuzzy_threshold=2,
        )
        assert Path(result["output_path"]).exists()

    def test_output_preserves_original_column_order(
        self, config: MasterConfig, tmp_path: Path
    ) -> None:
        """Output: RowID first, then original cols in original order, then Dosage Amount + BU."""
        if not ALT_INPUT_PATH.exists():
            pytest.skip("test_alt_input.csv not found — run tests/create_test_data.py first")

        # Read alt input to know expected column order
        alt_input = pd.read_csv(ALT_INPUT_PATH, dtype=str)
        original_cols = list(alt_input.columns)

        input_copy = tmp_path / "test_order_check.csv"
        shutil.copy(ALT_INPUT_PATH, input_copy)

        result = run_pipeline(
            input_path=input_copy,
            config=config,
            fuzzy_threshold=2,
        )

        actual = pd.read_csv(result["output_path"], dtype=str)
        actual_cols = list(actual.columns)

        # First column must be RowID
        assert actual_cols[0] == "RowID", f"First column should be RowID, got {actual_cols[0]}"

        # Last two columns must be Dosage Amount and BU
        assert actual_cols[-1] == "BU", f"Last column should be BU, got {actual_cols[-1]}"
        assert actual_cols[-2] == "Dosage Amount", (
            f"Second-to-last column should be Dosage Amount, got {actual_cols[-2]}"
        )

        # Middle columns must match original order
        middle_cols = actual_cols[1:-2]
        assert middle_cols == original_cols, (
            f"Middle columns {middle_cols} do not match original order {original_cols}"
        )

    def test_alt_format_pipeline(self, config: MasterConfig, tmp_path: Path) -> None:
        """Alternative column format with Smart MIPID and Documentstatus processes correctly."""
        if not ALT_INPUT_PATH.exists():
            pytest.skip("test_alt_input.csv not found — run tests/create_test_data.py first")
        if not ALT_EXPECTED_PATH.exists():
            pytest.skip("test_alt_expected.csv not found — run tests/create_test_data.py first")

        input_copy = tmp_path / "test_alt_input.csv"
        shutil.copy(ALT_INPUT_PATH, input_copy)

        result = run_pipeline(
            input_path=input_copy,
            config=config,
            fuzzy_threshold=2,
        )

        assert Path(result["output_path"]).exists()

        actual = pd.read_csv(result["output_path"], dtype=str)
        expected = pd.read_csv(ALT_EXPECTED_PATH, dtype=str)

        # Compare key transformed columns
        for col in ["Indication", "Service Provider", "Dosage Amount", "BU"]:
            actual_col = actual[col].fillna("").str.strip().tolist()
            expected_col = expected[col].fillna("").str.strip().tolist()
            mismatches = [
                (i + 1, a, e)
                for i, (a, e) in enumerate(zip(actual_col, expected_col))
                if a != e
            ]
            assert mismatches == [], (
                f"Column '{col}' mismatches:\n"
                + "\n".join(f"  Row {r}: got '{a}' expected '{e}'" for r, a, e in mismatches)
            )

        # Verify extra columns are preserved
        assert "Smart MIPID" in actual.columns
        assert "Documentstatus" in actual.columns

        # Verify columns that are absent in alt input are not added
        assert "Price basis" not in actual.columns
        assert "Art 71 Rating" not in actual.columns


# ================================================================== #
# Column count / no-drop guarantee tests
# ================================================================== #

class TestColumnPreservation:
    """Verify that EVERY original column is preserved in output (never dropped)."""

    def _run_with_n_cols(
        self, config: MasterConfig, tmp_path: Path, extra_cols: dict
    ) -> tuple[int, int, list[str]]:
        """
        Build a minimal valid CSV with the required 3 columns + extra_cols,
        run the pipeline, and return (input_col_count, output_col_count, output_cols).
        """
        import csv

        base = {
            "Indication": "ZZ - other  ",
            "Service Provider": "Apotheke Gelterkinden",
            "Pack": "LYNPARZA Filmtabl 150 mg",
        }
        row = {**base, **extra_cols}
        headers = list(row.keys())
        csv_path = tmp_path / "col_test.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerow(row)

        result = run_pipeline(csv_path, config, fuzzy_threshold=2)
        actual_df = pd.read_csv(result["output_path"], dtype=str)
        return len(headers), len(actual_df.columns), list(actual_df.columns)

    def test_21_input_columns_gives_24_output(
        self, config: MasterConfig, tmp_path: Path
    ) -> None:
        """21 input columns → 21 + RowID + Dosage Amount + BU = 24 output columns."""
        extra = {f"ExtraCol{i}": f"val{i}" for i in range(18)}  # 3 required + 18 extra = 21
        n_in, n_out, out_cols = self._run_with_n_cols(config, tmp_path, extra)
        assert n_in == 21, f"Expected 21 input columns, got {n_in}"
        assert n_out == 24, (
            f"Expected 24 output columns (21 + 3), got {n_out}. Columns: {out_cols}"
        )

    def test_15_input_columns_gives_18_output(
        self, config: MasterConfig, tmp_path: Path
    ) -> None:
        """15 input columns → 15 + RowID + Dosage Amount + BU = 18 output columns."""
        extra = {f"ExtraCol{i}": f"val{i}" for i in range(12)}  # 3 required + 12 extra = 15
        n_in, n_out, out_cols = self._run_with_n_cols(config, tmp_path, extra)
        assert n_in == 15, f"Expected 15 input columns, got {n_in}"
        assert n_out == 18, (
            f"Expected 18 output columns (15 + 3), got {n_out}. Columns: {out_cols}"
        )

    def test_3_required_columns_only_gives_6_output(
        self, config: MasterConfig, tmp_path: Path
    ) -> None:
        """Minimal input (3 required columns only) → 3 + 3 = 6 output columns."""
        n_in, n_out, out_cols = self._run_with_n_cols(config, tmp_path, {})
        assert n_in == 3, f"Expected 3 input columns, got {n_in}"
        assert n_out == 6, (
            f"Expected 6 output columns (3 + 3), got {n_out}. Columns: {out_cols}"
        )

    def test_no_original_column_is_ever_dropped(
        self, config: MasterConfig, tmp_path: Path
    ) -> None:
        """Every column in input must appear in output at its original position (+1 for RowID)."""
        extra = {"ColA": "a", "ColB": "b", "ColC": "c"}
        _, _, out_cols = self._run_with_n_cols(config, tmp_path, extra)
        for col in ["Indication", "Service Provider", "Pack", "ColA", "ColB", "ColC"]:
            assert col in out_cols, f"Column '{col}' was dropped from output!"

    def test_output_column_order_rowid_first_dosage_bu_last(
        self, config: MasterConfig, tmp_path: Path
    ) -> None:
        """RowID is always first; Dosage Amount and BU are always the last two columns."""
        extra = {"Before": "x", "After": "y"}
        _, _, out_cols = self._run_with_n_cols(config, tmp_path, extra)
        assert out_cols[0] == "RowID", f"First column must be RowID, got '{out_cols[0]}'"
        assert out_cols[-2] == "Dosage Amount", f"Second-to-last must be Dosage Amount, got '{out_cols[-2]}'"
        assert out_cols[-1] == "BU", f"Last column must be BU, got '{out_cols[-1]}'"


# ================================================================== #
# Bug-fix regression tests (Bugs 1–6)
# ================================================================== #

class TestBugFixes:
    """Regression tests for the 6 service-provider matching bugs."""

    # ---- Bug 1: period truncation ----

    def test_bug1_med_zentrum_brugg_not_truncated(self) -> None:
        """post_match_cleanup must NOT truncate 'Med. Zentrum Brugg' to 'Med'."""
        result = post_match_cleanup("Med. Zentrum Brugg")
        assert result == "Med. Zentrum Brugg", (
            f"Expected 'Med. Zentrum Brugg', got '{result}'"
        )

    def test_bug1_name_with_period_mid_string_preserved(self) -> None:
        """Names like 'Kantonsspital St. Gallen' must not lose text after the period."""
        result = post_match_cleanup("Kantonsspital St. Gallen")
        assert result == "HOCH"  # maps to HOCH — not truncated to "Kantonsspital St"

    def test_bug1_trailing_period_stripped(self) -> None:
        """A trailing period at the very end of the string is stripped."""
        result = post_match_cleanup("Spital Linth.")
        assert result == "HOCH"  # trailing period removed → "Spital Linth" → HOCH

    def test_bug1_praxis_with_period_location_preserved(self) -> None:
        """'Praxis Müller. Zürich' — the '. Zürich' must NOT be stripped (only trailing dot)."""
        result = post_match_cleanup("Praxis Müller. Zürich")
        # The mid-string period must not cause truncation
        assert "Müller" in result, f"Name truncated: got '{result}'"

    # ---- Bug 2: chardet encoding (functional smoke test) ----

    def test_bug2_utf8_csv_loads_correctly(self, tmp_path: Path) -> None:
        """CSV files written as UTF-8 with special chars must load without mojibake."""
        from pipeline.utils import load_input_file

        csv_content = "Indication,Service Provider,Pack\nAsthma,Spital Zürich,FASENRA\n"
        csv_path = tmp_path / "test_encoding.csv"
        csv_path.write_bytes(csv_content.encode("utf-8"))
        df = load_input_file(csv_path)
        assert df["Service Provider"].iloc[0] == "Spital Zürich"

    def test_bug2_utf8_bom_csv_loads_correctly(self, tmp_path: Path) -> None:
        """CSV with UTF-8 BOM (Excel export format) must load without mojibake."""
        from pipeline.utils import load_input_file

        csv_content = "Indication,Service Provider,Pack\nAsthma,Apotheke Zürich,FASENRA\n"
        csv_path = tmp_path / "test_bom.csv"
        csv_path.write_bytes(b"\xef\xbb\xbf" + csv_content.encode("utf-8"))
        df = load_input_file(csv_path)
        assert df["Service Provider"].iloc[0] == "Apotheke Zürich"

    def test_bug2_output_uses_utf8_bom(self, tmp_path: Path) -> None:
        """Output CSV must start with UTF-8 BOM so Excel opens it correctly."""
        from output.writer import write_output
        import pandas as pd

        df = pd.DataFrame({"RowID": [1], "Service Provider": ["Spital Zürich"]})
        out = write_output(df, tmp_path / "input.csv")
        assert out.read_bytes()[:3] == b"\xef\xbb\xbf", "Output CSV missing UTF-8 BOM"

    # ---- Bug 3: trailing dash stripping ----

    def test_bug3_trailing_dash_stripped(self) -> None:
        """'Lindenhofgruppe AG -' → 'Lindenhofgruppe' (trailing dash + AG suffix removed)."""
        result = post_match_cleanup("Lindenhofgruppe AG -")
        assert result == "Lindenhofgruppe", f"Expected 'Lindenhofgruppe', got '{result}'"

    def test_bug3_trailing_dash_without_suffix(self) -> None:
        """'Lindenhofgruppe -' → 'Lindenhofgruppe'."""
        result = post_match_cleanup("Lindenhofgruppe -")
        assert result == "Lindenhofgruppe", f"Expected 'Lindenhofgruppe', got '{result}'"

    def test_bug3_trailing_dash_no_space(self) -> None:
        """'SomeName-' → 'SomeName' (no space before dash)."""
        result = post_match_cleanup("SomeName-")
        assert result == "SomeName", f"Expected 'SomeName', got '{result}'"

    # ---- Bug 4: case-insensitive exact matching ----

    def test_bug4_exact_match_lowercase_input(self, config: MasterConfig) -> None:
        """ExactMatcher must match lowercase input against mixed-case rule."""
        matcher = ExactMatcher(config.name_rules)
        # "Spital Thurgau AG" is in the rules; lowercase input must still match
        result = matcher.match("spital thurgau ag")
        assert result == "Spital Thurgau", f"Case-insensitive match failed, got '{result}'"

    def test_bug4_exact_match_uppercase_input(self, config: MasterConfig) -> None:
        """ExactMatcher must match UPPERCASE input against mixed-case rule."""
        matcher = ExactMatcher(config.name_rules)
        result = matcher.match("FARMACIA DELLE SEMINE SA")
        assert result == "Farmacia delle Semine", f"Case-insensitive match failed, got '{result}'"

    def test_bug4_normalize_for_fuzzy_is_lowercase(self) -> None:
        """normalize_for_fuzzy must lowercase its output (makes fuzzy matching case-insensitive)."""
        assert normalize_for_fuzzy("SPITAL Thurgau") == normalize_for_fuzzy("spital thurgau")

    # ---- Bug 5: trailing/leading whitespace ----

    def test_bug5_trailing_spaces_exact_match(self, config: MasterConfig) -> None:
        """Inputs with trailing spaces must still match exactly."""
        matcher = ExactMatcher(config.name_rules)
        result = matcher.match("Spital Thurgau AG   ")
        assert result == "Spital Thurgau", f"Trailing space broke match, got '{result}'"

    def test_bug5_leading_spaces_exact_match(self, config: MasterConfig) -> None:
        """Inputs with leading spaces must still match exactly."""
        matcher = ExactMatcher(config.name_rules)
        result = matcher.match("   Spital Thurgau AG")
        assert result == "Spital Thurgau", f"Leading space broke match, got '{result}'"

    # ---- Bug 6: doctor name extraction and HCP lookup ----

    def test_bug6_strip_titles_dr_med(self) -> None:
        """'Dr. med. Lukas von Rohr' → 'Lukas von Rohr' after title stripping."""
        result = _strip_titles("Dr. med. Lukas von Rohr")
        assert result == "Lukas von Rohr", f"Title stripping failed, got '{result}'"

    def test_bug6_strip_titles_frau_dr(self) -> None:
        """'Frau Dr. Anna Müller' → 'Anna Müller' after title stripping."""
        result = _strip_titles("Frau Dr. Anna Müller")
        assert result == "Anna Müller", f"Title stripping failed, got '{result}'"

    def test_bug6_strip_titles_pd_dr(self) -> None:
        """'PD Dr. Stefan Braun' → 'Stefan Braun' after title stripping."""
        result = _strip_titles("PD Dr. Stefan Braun")
        assert result == "Stefan Braun", f"Title stripping failed, got '{result}'"

    def test_bug6_strip_titles_med_pract(self) -> None:
        """'med. pract. Hans Meier' → 'Hans Meier' after title stripping."""
        result = _strip_titles("med. pract. Hans Meier")
        assert result == "Hans Meier", f"Title stripping failed, got '{result}'"

    def test_bug6_strip_titles_frau_herr(self) -> None:
        """'Herr Peter Schmidt' → 'Peter Schmidt' after title stripping."""
        result = _strip_titles("Herr Peter Schmidt")
        assert result == "Peter Schmidt", f"Title stripping failed, got '{result}'"

    def test_bug6_name_match_with_title(self, config: MasterConfig) -> None:
        """NameMatcher must match 'Dr. med. G. Rüttimann' despite the title prefix."""
        matcher = NameMatcher(config.hcp_universe)
        result = matcher.match("Dr. med. G. Rüttimann")
        assert result == "Lungenpraxis Wohlen", f"Title-prefixed name match failed, got '{result}'"

    def test_bug6_name_match_frau_dr(self, config: MasterConfig) -> None:
        """NameMatcher must match 'Frau Dr. Gottfried Rüttimann' after stripping 'Frau Dr.'."""
        matcher = NameMatcher(config.hcp_universe)
        result = matcher.match("Frau Dr. Gottfried Rüttimann")
        assert result == "Lungenpraxis Wohlen", f"'Frau Dr.' prefix not stripped, got '{result}'"


# ================================================================== #
# Full pipeline integration test
# ================================================================== #

class TestFullPipeline:
    def test_pipeline_produces_expected_output(self, config: MasterConfig, tmp_path: Path) -> None:
        if not RAW_INPUT_PATH.exists():
            pytest.skip("test_input_raw.csv not found")
        if not EXPECTED_OUTPUT_PATH.exists():
            pytest.skip("test_expected_output.csv not found")

        # Copy input to tmp_path so output lands there
        input_copy = tmp_path / "test_input_raw.csv"
        shutil.copy(RAW_INPUT_PATH, input_copy)

        result = run_pipeline(
            input_path=input_copy,
            config=config,
            fuzzy_threshold=2,
        )

        assert Path(result["output_path"]).exists()
        assert Path(result["log_path"]).exists()

        actual = pd.read_csv(result["output_path"], dtype=str)
        expected = pd.read_csv(EXPECTED_OUTPUT_PATH, dtype=str)

        # Compare key columns — robust to output ordering
        for col in ["Indication", "Service Provider", "Dosage Amount", "BU"]:
            assert col in actual.columns, f"Column '{col}' missing from output"
            actual_col = actual[col].fillna("").tolist()
            expected_col = expected[col].fillna("").tolist()
            mismatches = [
                (i + 1, a, e)
                for i, (a, e) in enumerate(zip(actual_col, expected_col))
                if a != e
            ]
            assert mismatches == [], (
                f"Column '{col}' mismatches:\n"
                + "\n".join(f"  Row {r}: got '{a}' expected '{e}'" for r, a, e in mismatches)
            )

    def test_row_count_preserved(self, config: MasterConfig, tmp_path: Path) -> None:
        if not RAW_INPUT_PATH.exists():
            pytest.skip("test_input_raw.csv not found")

        input_copy = tmp_path / "test_input_raw.csv"
        shutil.copy(RAW_INPUT_PATH, input_copy)

        result = run_pipeline(input_copy, config, fuzzy_threshold=2)
        actual = pd.read_csv(result["output_path"], dtype=str)
        raw = pd.read_csv(RAW_INPUT_PATH, dtype=str)

        assert len(actual) == len(raw)

    def test_row_id_sequential(self, config: MasterConfig, tmp_path: Path) -> None:
        if not RAW_INPUT_PATH.exists():
            pytest.skip("test_input_raw.csv not found")

        input_copy = tmp_path / "test_input_raw.csv"
        shutil.copy(RAW_INPUT_PATH, input_copy)

        result = run_pipeline(input_copy, config, fuzzy_threshold=2)
        actual = pd.read_csv(result["output_path"], dtype=str)

        row_ids = actual["RowID"].astype(int).tolist()
        assert row_ids == list(range(1, len(actual) + 1))

    def test_match_log_columns(self, config: MasterConfig, tmp_path: Path) -> None:
        if not RAW_INPUT_PATH.exists():
            pytest.skip("test_input_raw.csv not found")

        input_copy = tmp_path / "test_input_raw.csv"
        shutil.copy(RAW_INPUT_PATH, input_copy)

        result = run_pipeline(input_copy, config, fuzzy_threshold=2)
        log = pd.read_csv(result["log_path"], dtype=str)

        expected_cols = {"RowID", "Raw_Service_Provider", "Clean_Service_Provider",
                         "Match_Type", "Match_Details"}
        assert expected_cols.issubset(set(log.columns))


# ================================================================== #
# Request Data pipeline tests
# ================================================================== #

class TestRequestPipeline:
    """Tests for the Request Data processing mode."""

    @pytest.fixture(scope="class")
    def request_config_path(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Create a minimal request_comparison.xlsx for testing."""
        import openpyxl

        tmp = tmp_path_factory.mktemp("request_config")
        xlsx_path = tmp / "request_comparison.xlsx"

        wb = openpyxl.Workbook()

        # r_indication_rule
        ws = wb.active
        ws.title = "r_indication_rule"
        ws.append(["old_Indication", "new_indication"])
        ws.append(["Asthma raw", "Asthma"])
        ws.append(["Cancer raw", "Oncology"])

        # r_insurance_rule
        ws2 = wb.create_sheet("r_insurance_rule")
        ws2.append(["old_Krankenkasse", "cleaned_insurance_name"])
        ws2.append(["KPT Versicherung AG", "KPT"])
        ws2.append(["CSS Kranken-Versicherung AG", "CSS"])
        ws2.append(["Helsana Versicherungen AG", "Helsana"])

        # r_BU_rule
        ws3 = wb.create_sheet("r_BU_rule")
        ws3.append(["old_Brand", "BU"])
        ws3.append(["FASENRA", "BBU"])
        ws3.append(["LYNPARZA", "OBU"])
        ws3.append(["IMFINZI", "OBU"])

        # r_name_rule
        ws4 = wb.create_sheet("r_name_rule")
        ws4.append(["old_Insitution", "new_Service Provider"])
        ws4.append(["Kantonsspital Bern AG", "Kantonsspital Bern"])
        ws4.append(["Inselspital AG", "Inselspital"])

        wb.save(xlsx_path)
        return xlsx_path

    @pytest.fixture(scope="class")
    def req_config(self, request_config_path: Path):
        from config.config_manager import RequestConfig
        return RequestConfig(request_config_path)

    def test_request_config_loads(self, req_config) -> None:
        assert len(req_config.indication_rules) == 2
        assert len(req_config.insurance_rules) == 3
        assert len(req_config.bu_rules) == 3
        assert len(req_config.name_rules) == 2

    def test_request_config_indication_col_renamed(self, req_config) -> None:
        """new_indication is renamed to new_Indication for IndicationStep compat."""
        assert "new_Indication" in req_config.indication_rules.columns
        assert "new_indication" not in req_config.indication_rules.columns

    def test_request_config_name_rule_col_renamed(self, req_config) -> None:
        """old_Insitution is renamed to old_Service Provider for ProviderStep compat."""
        assert "old_Service Provider" in req_config.name_rules.columns

    def test_request_config_bu_lookup(self, req_config) -> None:
        assert req_config.bu_lookup["fasenra"] == "BBU"
        assert req_config.bu_lookup["lynparza"] == "OBU"

    def test_insurance_step_exact_match(self, req_config) -> None:
        from pipeline.step_insurance import InsuranceStep
        step = InsuranceStep(req_config.insurance_rules)
        cleaned, mt = step.transform("KPT Versicherung AG")
        assert cleaned == "KPT"
        assert mt == "exact"

    def test_insurance_step_case_insensitive(self, req_config) -> None:
        from pipeline.step_insurance import InsuranceStep
        step = InsuranceStep(req_config.insurance_rules)
        cleaned, mt = step.transform("kpt versicherung ag")
        assert cleaned == "KPT"
        assert mt == "exact"

    def test_insurance_step_no_match(self, req_config) -> None:
        from pipeline.step_insurance import InsuranceStep
        step = InsuranceStep(req_config.insurance_rules)
        cleaned, mt = step.transform("Unknown Kasse XYZ")
        assert cleaned == "Unknown Kasse XYZ"
        assert mt == "no-match"

    def test_request_pipeline_runs(self, req_config, tmp_path: Path) -> None:
        from pipeline.request_pipeline import run_request_pipeline

        csv_path = tmp_path / "req_input.csv"
        csv_path.write_text(
            "Decision Date,Krankenkasse,Patient Id,Id,Case Type,Brand,Indication,"
            "Indication Received,Insitution,Applicant,Rating,Participation,Comment,Status\n"
            "01-Jan-2024,KPT Versicherung AG,P001,1,Type A,FASENRA,Asthma raw,"
            "Asthma,Kantonsspital Bern AG,Dr. Smith,A,Yes,Test,Approved\n",
            encoding="utf-8",
        )

        result = run_request_pipeline(csv_path, req_config, fuzzy_threshold=2)
        assert Path(result["output_path"]).exists()
        assert Path(result["log_path"]).exists()
        assert Path(result["insurance_log_path"]).exists()

    def test_request_pipeline_column_order(self, req_config, tmp_path: Path) -> None:
        """RowID first, original cols in order (Insitution→Institution), BU last."""
        from pipeline.request_pipeline import run_request_pipeline
        import pandas as pd

        csv_path = tmp_path / "req_col_order.csv"
        csv_path.write_text(
            "Decision Date,Krankenkasse,Patient Id,Id,Case Type,Brand,Indication,"
            "Indication Received,Insitution,Applicant,Rating,Participation,Comment,Status\n"
            "01-Jan-2024,KPT Versicherung AG,P001,1,A,FASENRA,Asthma raw,"
            "Asthma,Kantonsspital Bern AG,Dr. Smith,A,Yes,Test,Approved\n",
            encoding="utf-8",
        )

        result = run_request_pipeline(csv_path, req_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        cols = list(out.columns)

        assert cols[0] == "RowID", f"First col must be RowID, got {cols[0]}"
        assert cols[-1] == "BU", f"Last col must be BU, got {cols[-1]}"
        assert "Dosage Amount" not in cols, "Dosage Amount must not appear in Request output"

    def test_request_pipeline_typo_fixed(self, req_config, tmp_path: Path) -> None:
        """'Insitution' column renamed to 'Institution' in output."""
        from pipeline.request_pipeline import run_request_pipeline
        import pandas as pd

        csv_path = tmp_path / "req_typo.csv"
        csv_path.write_text(
            "Decision Date,Krankenkasse,Patient Id,Id,Case Type,Brand,Indication,"
            "Indication Received,Insitution,Applicant,Rating,Participation,Comment,Status\n"
            "01-Jan-2024,CSS Kranken-Versicherung AG,P002,2,A,IMFINZI,Cancer raw,"
            "Oncology,Inselspital AG,Dr. Jones,B,No,,Pending\n",
            encoding="utf-8",
        )

        result = run_request_pipeline(csv_path, req_config)
        out = pd.read_csv(result["output_path"], dtype=str)

        assert "Institution" in out.columns, "Output must have 'Institution' column"
        assert "Insitution" not in out.columns, "'Insitution' typo must not appear in output"

    def test_request_pipeline_krankenkasse_cleaned(self, req_config, tmp_path: Path) -> None:
        """Krankenkasse column values are replaced with cleaned insurance names."""
        from pipeline.request_pipeline import run_request_pipeline
        import pandas as pd

        csv_path = tmp_path / "req_kk.csv"
        csv_path.write_text(
            "Decision Date,Krankenkasse,Patient Id,Id,Case Type,Brand,Indication,"
            "Indication Received,Insitution,Applicant,Rating,Participation,Comment,Status\n"
            "01-Jan-2024,CSS Kranken-Versicherung AG,P003,3,A,FASENRA,Asthma raw,"
            "Asthma,Kantonsspital Bern AG,Dr. A,A,Yes,,Approved\n",
            encoding="utf-8",
        )

        result = run_request_pipeline(csv_path, req_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["Krankenkasse"].iloc[0] == "CSS"

    def test_request_pipeline_bu_assigned(self, req_config, tmp_path: Path) -> None:
        """BU is assigned from Brand via r_BU_rule."""
        from pipeline.request_pipeline import run_request_pipeline
        import pandas as pd

        csv_path = tmp_path / "req_bu.csv"
        csv_path.write_text(
            "Decision Date,Krankenkasse,Patient Id,Id,Case Type,Brand,Indication,"
            "Indication Received,Insitution,Applicant,Rating,Participation,Comment,Status\n"
            "01-Jan-2024,KPT Versicherung AG,P004,4,A,LYNPARZA,Asthma raw,"
            "Asthma,Kantonsspital Bern AG,Dr. B,A,Yes,,Approved\n",
            encoding="utf-8",
        )

        result = run_request_pipeline(csv_path, req_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["BU"].iloc[0] == "OBU"

    def test_request_pipeline_row_count(self, req_config, tmp_path: Path) -> None:
        """Output has same row count as input."""
        from pipeline.request_pipeline import run_request_pipeline
        import pandas as pd

        rows = "\n".join(
            f"01-Jan-2024,KPT Versicherung AG,P{i},{i},A,FASENRA,Asthma raw,"
            f"Asthma,Kantonsspital Bern AG,Dr. X,A,Yes,,Approved"
            for i in range(5)
        )
        csv_path = tmp_path / "req_rows.csv"
        csv_path.write_text(
            "Decision Date,Krankenkasse,Patient Id,Id,Case Type,Brand,Indication,"
            "Indication Received,Insitution,Applicant,Rating,Participation,Comment,Status\n"
            + rows + "\n",
            encoding="utf-8",
        )

        result = run_request_pipeline(csv_path, req_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert len(out) == 5
        assert list(out["RowID"].astype(int)) == list(range(1, 6))

    def test_mode_routing_claim(self, config: MasterConfig, tmp_path: Path) -> None:
        """run_pipeline with mode='claim' uses MasterConfig."""
        from pipeline.orchestrator import run_pipeline
        import csv

        csv_path = tmp_path / "mode_claim.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["Indication", "Service Provider", "Pack"]
            )
            writer.writeheader()
            writer.writerow({
                "Indication": "ZZ - other  ",
                "Service Provider": "Apotheke Gelterkinden",
                "Pack": "LYNPARZA Filmtabl 150 mg",
            })

        result = run_pipeline(csv_path, config, mode="claim")
        assert Path(result["output_path"]).exists()
        out = pd.read_csv(result["output_path"], dtype=str)
        assert "Dosage Amount" in out.columns

    def test_mode_routing_request(self, req_config, tmp_path: Path) -> None:
        """run_pipeline with mode='request' uses RequestConfig."""
        from pipeline.orchestrator import run_pipeline

        csv_path = tmp_path / "mode_req.csv"
        csv_path.write_text(
            "Decision Date,Krankenkasse,Patient Id,Id,Case Type,Brand,Indication,"
            "Indication Received,Insitution,Applicant,Rating,Participation,Comment,Status\n"
            "01-Jan-2024,KPT Versicherung AG,P1,1,A,FASENRA,Asthma raw,"
            "Asthma,Kantonsspital Bern AG,Dr. X,A,Yes,,Approved\n",
            encoding="utf-8",
        )

        result = run_pipeline(csv_path, req_config, mode="request")
        out = pd.read_csv(result["output_path"], dtype=str)
        assert "Dosage Amount" not in out.columns
        assert "BU" in out.columns
        assert "Institution" in out.columns


class TestEnhertuPipeline:
    """Tests for the Enhertu Data processing mode."""

    @pytest.fixture(scope="class")
    def enhertu_config_path(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Create a minimal enhertu_config.xlsx for testing."""
        import openpyxl

        tmp = tmp_path_factory.mktemp("enhertu_config")
        xlsx_path = tmp / "enhertu_config.xlsx"

        wb = openpyxl.Workbook()

        ws = wb.active
        ws.title = "insurance_rule"
        ws.append(["Versicherung", "cleaned_insurance_name"])
        ws.append(["Groupe Mutuel Versicherungen GMA", "GMA"])
        ws.append(["CSS Kranken-Versicherung AG", "CSS"])
        ws.append(["Helsana Versicherungen AG", "Helsana"])

        ws2 = wb.create_sheet("indication_rule")
        ws2.append(["Indikationscode", "cleaned_indication"])
        ws2.append(["21338.02", "Breast Cancer HER2+"])
        ws2.append(["99001", "Gastric Cancer"])

        wb.save(xlsx_path)
        return xlsx_path

    @pytest.fixture(scope="class")
    def enhertu_config(self, enhertu_config_path: Path):
        from config.config_manager import EnhertuConfig
        return EnhertuConfig(enhertu_config_path)

    def test_enhertu_config_loads(self, enhertu_config) -> None:
        assert len(enhertu_config.insurance_rules) == 3
        assert len(enhertu_config.indication_rules) == 2

    def test_enhertu_pipeline_adds_rowid_brand_bu(self, enhertu_config, tmp_path: Path) -> None:
        """Pipeline adds RowID, Brand='Enhertu', BU='OBU' to output."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline

        csv_path = tmp_path / "enhertu_basic.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "Groupe Mutuel Versicherungen GMA,21338.02\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)
        out = pd.read_csv(result["output_path"], dtype=str)

        assert "RowID" in out.columns
        assert out["RowID"].iloc[0] == "1"
        assert "Brand" in out.columns
        assert out["Brand"].iloc[0] == "Enhertu"
        assert "BU" in out.columns
        assert out["BU"].iloc[0] == "OBU"

    def test_enhertu_insurance_exact_match(self, enhertu_config, tmp_path: Path) -> None:
        """Insurance name is cleaned via exact match."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline

        csv_path = tmp_path / "enhertu_ins.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "Groupe Mutuel Versicherungen GMA,21338.02\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["Versicherung"].iloc[0] == "GMA"

    def test_enhertu_insurance_trailing_spaces(self, enhertu_config, tmp_path: Path) -> None:
        """Insurance matching handles trailing spaces."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline

        csv_path = tmp_path / "enhertu_ins_spaces.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "Groupe Mutuel Versicherungen GMA   ,21338.02\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["Versicherung"].iloc[0] == "GMA"

    def test_enhertu_indication_exact_match(self, enhertu_config, tmp_path: Path) -> None:
        """Indication code is replaced with cleaned_indication on exact match."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline

        csv_path = tmp_path / "enhertu_ind.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "CSS Kranken-Versicherung AG,21338.02\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["Indikationscode"].iloc[0] == "Breast Cancer HER2+"

    def test_enhertu_indication_numeric_normalization(self, enhertu_config, tmp_path: Path) -> None:
        """Trailing zeros in indication codes match the same rule (21338.020 == 21338.02)."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline

        csv_path = tmp_path / "enhertu_norm.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "CSS Kranken-Versicherung AG,21338.020\n"
            "Helsana Versicherungen AG,21338.0200\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["Indikationscode"].iloc[0] == "Breast Cancer HER2+"
        assert out["Indikationscode"].iloc[1] == "Breast Cancer HER2+"

    def test_enhertu_indication_normalize_code_unit(self) -> None:
        """_normalize_code converts float-string representation consistently."""
        from pipeline.enhertu_pipeline import _normalize_code

        assert _normalize_code("21338.02") == _normalize_code("21338.020")
        assert _normalize_code("21338.02") == _normalize_code("21338.0200")
        assert _normalize_code("99001") == _normalize_code("99001.0")
        assert _normalize_code("") == ""
        assert _normalize_code("nan") == ""

    def test_enhertu_original_columns_preserved(self, enhertu_config, tmp_path: Path) -> None:
        """All original columns appear in output, plus RowID, Brand, BU."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline

        csv_path = tmp_path / "enhertu_cols.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode,ExtraCol,AnotherCol\n"
            "GMA,21338.02,foo,bar\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)
        out = pd.read_csv(result["output_path"], dtype=str)

        for col in ["RowID", "Versicherung", "Indikationscode", "ExtraCol", "AnotherCol", "Brand", "BU"]:
            assert col in out.columns, f"Missing column: {col}"

        assert list(out.columns) == ["RowID", "Versicherung", "Indikationscode", "ExtraCol", "AnotherCol", "Brand", "BU"]

    def test_enhertu_output_files_in_correct_dirs(self, enhertu_config, tmp_path: Path, monkeypatch) -> None:
        """Output CSV goes to processed_data/ and logs go to Logs/."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline
        import config.settings as settings_mod

        processed_dir = tmp_path / "processed_data"
        logs_dir = tmp_path / "Logs"
        processed_dir.mkdir()
        logs_dir.mkdir()

        monkeypatch.setattr(settings_mod, "get_app_output_dirs", lambda: (processed_dir, logs_dir))

        csv_path = tmp_path / "enhertu_dirs.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "CSS Kranken-Versicherung AG,99001\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)

        assert Path(result["output_path"]).parent == processed_dir
        assert Path(result["insurance_log_path"]).parent == logs_dir
        assert Path(result["indication_log_path"]).parent == logs_dir

    def test_enhertu_indication_no_match_passthrough(self, enhertu_config, tmp_path: Path) -> None:
        """Unknown indication codes pass through unchanged."""
        from pipeline.enhertu_pipeline import run_enhertu_pipeline

        csv_path = tmp_path / "enhertu_nomatch.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "CSS Kranken-Versicherung AG,99999\n",
            encoding="utf-8",
        )

        result = run_enhertu_pipeline(csv_path, enhertu_config)
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["Indikationscode"].iloc[0] == "99999"

    def test_enhertu_mode_routing(self, enhertu_config, tmp_path: Path) -> None:
        """run_pipeline with mode='enhertu' uses EnhertuConfig and returns Brand/BU."""
        from pipeline.orchestrator import run_pipeline

        csv_path = tmp_path / "enhertu_route.csv"
        csv_path.write_text(
            "Versicherung,Indikationscode\n"
            "Groupe Mutuel Versicherungen GMA,21338.02\n",
            encoding="utf-8",
        )

        result = run_pipeline(csv_path, enhertu_config, mode="enhertu")
        out = pd.read_csv(result["output_path"], dtype=str)
        assert out["Brand"].iloc[0] == "Enhertu"
        assert out["BU"].iloc[0] == "OBU"
        assert "insurance_counts" in result
        assert "indication_counts" in result
