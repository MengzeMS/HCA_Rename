"""
Pipeline integration tests and unit tests.

Run from claim_cleaner/ directory:
    python -m pytest tests/test_pipeline.py -v
"""
from __future__ import annotations

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
# Full pipeline integration test
# ================================================================== #

class TestFullPipeline:
    def test_pipeline_produces_expected_output(self, config: MasterConfig, tmp_path: Path) -> None:
        if not RAW_INPUT_PATH.exists():
            pytest.skip("test_input_raw.csv not found")
        if not EXPECTED_OUTPUT_PATH.exists():
            pytest.skip("test_expected_output.csv not found")

        # Copy input to tmp_path so output lands there
        import shutil
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

        # Compare key columns
        for col in ["Indication", "Service Provider", "Dosage Amount", "BU"]:
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

        import shutil
        input_copy = tmp_path / "test_input_raw.csv"
        shutil.copy(RAW_INPUT_PATH, input_copy)

        result = run_pipeline(input_copy, config, fuzzy_threshold=2)
        actual = pd.read_csv(result["output_path"], dtype=str)
        raw = pd.read_csv(RAW_INPUT_PATH, dtype=str)

        assert len(actual) == len(raw)

    def test_row_id_sequential(self, config: MasterConfig, tmp_path: Path) -> None:
        if not RAW_INPUT_PATH.exists():
            pytest.skip("test_input_raw.csv not found")

        import shutil
        input_copy = tmp_path / "test_input_raw.csv"
        shutil.copy(RAW_INPUT_PATH, input_copy)

        result = run_pipeline(input_copy, config, fuzzy_threshold=2)
        actual = pd.read_csv(result["output_path"], dtype=str)

        row_ids = actual["RowID"].astype(int).tolist()
        assert row_ids == list(range(1, len(actual) + 1))

    def test_match_log_columns(self, config: MasterConfig, tmp_path: Path) -> None:
        if not RAW_INPUT_PATH.exists():
            pytest.skip("test_input_raw.csv not found")

        import shutil
        input_copy = tmp_path / "test_input_raw.csv"
        shutil.copy(RAW_INPUT_PATH, input_copy)

        result = run_pipeline(input_copy, config, fuzzy_threshold=2)
        log = pd.read_csv(result["log_path"], dtype=str)

        expected_cols = {"RowID", "Raw_Service_Provider", "Clean_Service_Provider",
                         "Match_Type", "Match_Details"}
        assert expected_cols.issubset(set(log.columns))
