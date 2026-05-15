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
from matching.normalizer import post_match_cleanup, remove_legal_suffixes
from matching.cell_parser import parse_segments
from matching.exact_match import ExactMatcher
from matching.name_match import NameMatcher
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
