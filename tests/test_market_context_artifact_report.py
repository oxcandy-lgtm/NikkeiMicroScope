"""Tests for the MarketContext artifact validation report.

These tests enforce the artifact-report contract documented in
``docs/market-context-artifact-report.md`` and §8.8 of
``docs/data-adapter-contract.md``.

Coverage:

* valid artifact returns ``valid_json=True``.
* invalid JSON returns ``valid_json=False`` and ``ok=False``.
* valid MarketContext artifact returns
  ``valid_market_context=True``.
* metadata keys ``synthetic`` and ``_dry_run_meta`` are stripped
  before schema validation.
* unknown top-level metadata key causes ``ok=False``.
* expected populated fields are detected.
* zero expected populated field causes ``ok=False``.
* SOX zero is accepted as unapproved/missing.
* SOX nonzero in synthetic approved dry-run artifact causes
  ``ok=False``.
* ``expect_synthetic=True`` requires marker.
* ``expect_synthetic=False`` does not require marker.
* report JSON is deterministic and ends with newline.
* report output validates with ``json.loads``.
* CLI script exists.
* dry-run shell exists.
* docs exist.
* parent contract links to docs.
* no subprocess import/call in ``nms/data/artifact_report.py``.
* no subprocess import/call in this test file.
* no env credential reads in artifact report module.
* no network library imports.
* no broker / order / account symbols introduced.
* no SOX adapter reference except docs saying unapproved.
* no raw FRED CSV committed.

All checks are pure filesystem / static checks. No subprocess
calls. No network I/O.
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from nms.data.artifact_report import (
    ArtifactFieldStatus,
    MarketContextArtifactReport,
    build_market_context_artifact_report,
    load_market_context_artifact,
    report_to_json_text,
    report_to_ordered_dict,
)
from nms.data.models import (
    EconomicEventRisk,
    Fx,
    IntradayRange,
    MarketContext,
    NikkeiNightSession,
    PreviousDay,
    Semiconductor,
    UsEquities,
    UsYields,
    VolatilityContext,
)
from nms.data.validate import ValidationError, validate_market_context


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_REPORT_DOC = (
    REPO_ROOT / "docs" / "market-context-artifact-report.md"
)
DATA_ADAPTER_CONTRACT = REPO_ROOT / "docs" / "data-adapter-contract.md"
ARTIFACT_DRY_RUN_SH = (
    REPO_ROOT
    / "scripts"
    / "validate_market_context_artifact_dry_run.sh"
)
ARTIFACT_REPORT_PATH = REPO_ROOT / "nms" / "data" / "artifact_report.py"
ARTIFACT_DRY_RUN_PY = (
    REPO_ROOT / "scripts" / "validate_market_context_artifact.py"
)
EXPORTS_DIR = REPO_ROOT / "exports"


# --- Helpers --------------------------------------------------------------


def _minimal_market_context_dict() -> dict:
    """Return a minimal but valid ``MarketContext`` payload as
    a dict, with all expected populated fields set to a
    nonzero value and all intentionally-missing / unapproved
    fields set to zero.
    """
    return {
        "session_date": "2026-06-24",
        "timezone": "Asia/Tokyo",
        "us_equities": {
            "sp500": 5480.0,
            "dow": 39000.0,
            "nasdaq100": 19800.0,
            "russell2000": 2050.0,
            "sp500_change_pct": 0.3,
            "nasdaq100_change_pct": 0.25,
        },
        "semiconductor": {
            "sox": 0.0,
            "sox_change_pct": 0.0,
        },
        "fx": {
            "usdjpy": 159.7,
            "usdjpy_change_pct": 0.25,
        },
        "us_yields": {
            "us2y": 4.2,
            "us10y": 4.3,
            "us10y_minus_us2y": 0.1,
            "us10y_change_bp": 3.0,
        },
        "nikkei_night_session": {
            "close": 0.0,
            "high": 0.0,
            "low": 0.0,
            "range": 0.0,
            "percent_change": 0.0,
        },
        "previous_day": {
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "range": 0.0,
        },
        "economic_event_risk": {"events": []},
        "intraday_range": {
            "first_15m_high": 0.0,
            "first_15m_low": 0.0,
            "first_15m_range": 0.0,
            "atr_like_baseline": 1.0,
        },
        "volatility_context": {
            "realized_vol": 0.0,
            "atr_like": 1.0,
            "compression_flag": False,
        },
    }


def _minimal_market_context() -> MarketContext:
    return MarketContext(
        session_date="2026-06-24",
        timezone="Asia/Tokyo",
        us_equities=UsEquities(
            sp500=5480.0,
            dow=39000.0,
            nasdaq100=19800.0,
            russell2000=2050.0,
            sp500_change_pct=0.3,
            nasdaq100_change_pct=0.25,
        ),
        semiconductor=Semiconductor(sox=0.0, sox_change_pct=0.0),
        fx=Fx(usdjpy=159.7, usdjpy_change_pct=0.25),
        us_yields=UsYields(
            us2y=4.2,
            us10y=4.3,
            us10y_minus_us2y=0.1,
            us10y_change_bp=3.0,
        ),
        nikkei_night_session=NikkeiNightSession(
            close=0.0,
            high=0.0,
            low=0.0,
            range=0.0,
            percent_change=0.0,
        ),
        previous_day=PreviousDay(
            high=0.0, low=0.0, close=0.0, range=0.0
        ),
        economic_event_risk=EconomicEventRisk(events=[]),
        intraday_range=IntradayRange(
            first_15m_high=0.0,
            first_15m_low=0.0,
            first_15m_range=0.0,
            atr_like_baseline=1.0,
        ),
        volatility_context=VolatilityContext(
            realized_vol=0.0,
            atr_like=1.0,
            compression_flag=False,
        ),
    )


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


# --- JSON loading / shape tests ------------------------------------------


class LoadArtifactTests(unittest.TestCase):
    def test_valid_artifact_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            loaded = load_market_context_artifact(p)
            self.assertIsInstance(loaded, dict)
            self.assertEqual(loaded["session_date"], "2026-06-24")

    def test_load_does_not_mutate_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            original = _minimal_market_context_dict()
            _write_json(p, original)
            loaded = load_market_context_artifact(p)
            loaded["session_date"] = "mutated"
            # Re-read the file to confirm it was not mutated
            # on disk.
            reloaded = load_market_context_artifact(p)
            self.assertEqual(reloaded["session_date"], "2026-06-24")

    def test_load_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("not json {", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                load_market_context_artifact(p)


# --- Report builder: valid / invalid ------------------------------------


class ReportBuilderValidTests(unittest.TestCase):
    def test_valid_artifact_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(p)
            self.assertTrue(report.valid_json)
            self.assertTrue(report.valid_market_context)
            self.assertEqual(report.session_date, "2026-06-24")
            self.assertFalse(report.synthetic)
            self.assertFalse(report.dry_run_meta_present)
            self.assertEqual(report.errors, ())
            self.assertTrue(report.ok)

    def test_valid_market_context_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(p)
            self.assertTrue(report.valid_market_context)

    def test_invalid_json_returns_valid_json_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("not json {", encoding="utf-8")
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.valid_json)
            self.assertFalse(report.ok)
            self.assertGreater(len(report.errors), 0)

    def test_missing_file(self) -> None:
        report = build_market_context_artifact_report(
            Path("/nonexistent/path/that/does/not/exist.json")
        )
        self.assertFalse(report.valid_json)
        self.assertFalse(report.ok)


# --- Metadata stripping and unknown top-level ---------------------------


class MetadataHandlingTests(unittest.TestCase):
    def test_synthetic_and_dry_run_meta_stripped_before_validate(
        self,
    ) -> None:
        # A payload with synthetic + _dry_run_meta that has
        # otherwise valid MarketContext should pass schema
        # validation (because the metadata is stripped).
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["synthetic"] = True
            payload["_dry_run_meta"] = {
                "source": "nms.data.export dry-run",
                "session_date": "2026-06-24",
                "live_fred_used": False,
            }
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertTrue(report.valid_market_context)
            self.assertTrue(report.synthetic)
            self.assertTrue(report.dry_run_meta_present)
            # Without expect_synthetic, the report should be ok.
            self.assertTrue(report.ok)

    def test_unknown_top_level_metadata_key_marks_report_not_ok(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["unexpected_top_level"] = "boom"
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "unknown top-level metadata keys" in err
                    for err in report.errors
                )
            )


# --- Populated-field detection -------------------------------------------


class PopulatedFieldTests(unittest.TestCase):
    def test_expected_populated_fields_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(p)
            for status in report.populated_fields:
                self.assertTrue(
                    status.present,
                    f"field {status.path!r} should be present",
                )
                self.assertTrue(
                    status.populated,
                    f"field {status.path!r} should be populated",
                )

    def test_zero_populated_field_marks_report_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["us_yields"]["us2y"] = 0.0
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "us_yields.us2y" in err
                    for err in report.errors
                )
            )


# --- SOX unapproved handling --------------------------------------------


class SOXHandlingTests(unittest.TestCase):
    def test_sox_zero_accepted_as_unapproved(self) -> None:
        # Without expect_synthetic, SOX zero is just reported
        # (not ok-failing) because the schema does not require
        # a nonzero SOX value.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            # semiconductor.sox is already 0.0
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            sox_status = next(
                s
                for s in report.intentionally_missing_or_unapproved_fields
                if s.path == "semiconductor.sox"
            )
            self.assertFalse(sox_status.populated)
            self.assertTrue(report.ok)

    def test_sox_nonzero_in_synthetic_marks_report_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["semiconductor"]["sox"] = 5550.0
            payload["synthetic"] = True
            payload["_dry_run_meta"] = {
                "source": "nms.data.export dry-run",
                "session_date": "2026-06-24",
                "live_fred_used": False,
            }
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertTrue(report.synthetic)
            self.assertTrue(report.dry_run_meta_present)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "semiconductor.sox" in err
                    for err in report.errors
                )
            )

    def test_sox_nonzero_in_non_synthetic_does_not_fail(self) -> None:
        # Without the synthetic marker, SOX nonzero is just
        # reported. The dispatch says "Do not fail merely
        # because SOX is zero. SOX is not approved yet." The
        # inverse is also acceptable: a non-synthetic artifact
        # that happens to have SOX nonzero is not flagged by
        # the SOX-unapproved rule, because the rule only
        # applies to artifacts claiming to be generated by the
        # approved dry-run pipeline.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["semiconductor"]["sox"] = 5550.0
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.synthetic)
            # The SOX-unapproved rule did not apply, so the
            # report is otherwise ok (no other errors).
            self.assertTrue(report.ok)


# --- Strict type checks on synthetic / _dry_run_meta --------------------


class SyntheticMetadataStrictTypeTests(unittest.TestCase):
    """The dispatch defines `synthetic` as a boolean and
    `_dry_run_meta` as an object. The validator must reject
    truthy non-boolean values (e.g. the string "yes", the
    integer 1, a non-empty list) and non-object values
    (e.g. a string or a list) for `_dry_run_meta`.
    """

    def test_synthetic_string_true_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["synthetic"] = "true"  # string, not bool
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            # A truthy non-boolean synthetic must not be
            # treated as synthetic.
            self.assertFalse(report.synthetic)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "'synthetic' must be boolean" in err
                    for err in report.errors
                ),
                f"expected boolean error; got {report.errors!r}",
            )

    def test_synthetic_integer_one_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["synthetic"] = 1  # int, not bool
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.synthetic)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "'synthetic' must be boolean" in err
                    for err in report.errors
                ),
                f"expected boolean error; got {report.errors!r}",
            )

    def test_synthetic_non_empty_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["synthetic"] = ["truthy"]  # list, not bool
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.synthetic)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "'synthetic' must be boolean" in err
                    for err in report.errors
                ),
                f"expected boolean error; got {report.errors!r}",
            )

    def test_dry_run_meta_non_object_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["_dry_run_meta"] = "not a dict"  # str
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.dry_run_meta_present)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "'_dry_run_meta' must be an object" in err
                    for err in report.errors
                ),
                f"expected object error; got {report.errors!r}",
            )

    def test_dry_run_meta_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["_dry_run_meta"] = [1, 2, 3]  # list
            _write_json(p, payload)
            report = build_market_context_artifact_report(p)
            self.assertFalse(report.dry_run_meta_present)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "'_dry_run_meta' must be an object" in err
                    for err in report.errors
                ),
                f"expected object error; got {report.errors!r}",
            )

    def test_expect_synthetic_rejects_truthy_non_boolean_synthetic(
        self,
    ) -> None:
        # A truthy non-boolean `synthetic` is not the
        # strict-boolean True. With expect_synthetic=True
        # the validator must reject it.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["synthetic"] = "yes"  # truthy non-bool
            payload["_dry_run_meta"] = {
                "source": "nms.data.export dry-run",
                "session_date": "2026-06-24",
                "live_fred_used": False,
            }
            _write_json(p, payload)
            report = build_market_context_artifact_report(
                p, expect_synthetic=True
            )
            self.assertFalse(report.synthetic)
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "'synthetic' must be boolean" in err
                    for err in report.errors
                ),
                f"expected boolean error; got {report.errors!r}",
            )

    def test_expect_synthetic_rejects_truthy_live_fred_used(self) -> None:
        # Truthy non-boolean live_fred_used is not the
        # strict-boolean False. With expect_synthetic=True
        # the validator must reject it.
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["synthetic"] = True
            payload["_dry_run_meta"] = {
                "source": "nms.data.export dry-run",
                "session_date": "2026-06-24",
                # 0 is "falsy" in Python, but it is not the
                # boolean False. Strict-type check rejects it.
                "live_fred_used": 0,
            }
            _write_json(p, payload)
            report = build_market_context_artifact_report(
                p, expect_synthetic=True
            )
            self.assertFalse(report.ok)
            self.assertTrue(
                any(
                    "live_fred_used" in err
                    and "boolean" in err
                    for err in report.errors
                ),
                f"expected boolean live_fred_used error; "
                f"got {report.errors!r}",
            )


# --- expect_synthetic behavior ------------------------------------------


class ExpectSyntheticTests(unittest.TestCase):
    def test_expect_synthetic_true_requires_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            # Valid MarketContext but no synthetic marker.
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(
                p, expect_synthetic=True
            )
            self.assertFalse(report.ok)
            self.assertTrue(
                any("synthetic" in err for err in report.errors)
            )

    def test_expect_synthetic_false_does_not_require_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            # Valid MarketContext, no synthetic marker.
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(
                p, expect_synthetic=False
            )
            self.assertTrue(report.ok)

    def test_expect_synthetic_true_accepts_valid_synthetic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            payload = _minimal_market_context_dict()
            payload["synthetic"] = True
            payload["_dry_run_meta"] = {
                "source": "nms.data.export dry-run",
                "session_date": "2026-06-24",
                "live_fred_used": False,
            }
            _write_json(p, payload)
            report = build_market_context_artifact_report(
                p, expect_synthetic=True
            )
            self.assertTrue(report.ok)


# --- Report serialization -----------------------------------------------


class ReportSerializationTests(unittest.TestCase):
    def test_report_to_json_text_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(p)
            text1 = report_to_json_text(report)
            text2 = report_to_json_text(report)
            self.assertEqual(text1, text2)

    def test_report_to_json_text_ends_with_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(p)
            text = report_to_json_text(report)
            self.assertTrue(text.endswith("\n"))

    def test_report_to_json_text_validates_with_json_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(p)
            text = report_to_json_text(report)
            parsed = json.loads(text)
            self.assertIn("valid_json", parsed)
            self.assertIn("valid_market_context", parsed)
            self.assertIn("ok", parsed)
            self.assertIn("populated_fields", parsed)

    def test_report_to_ordered_dict_returns_plain_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.json"
            _write_json(p, _minimal_market_context_dict())
            report = build_market_context_artifact_report(p)
            d = report_to_ordered_dict(report)
            self.assertIsInstance(d, dict)
            self.assertIn("ok", d)
            self.assertIn("valid_json", d)


# --- Static AST purity ---------------------------------------------------


def _module_has_subprocess_use(py_path: Path) -> bool:
    tree = ast.parse(
        py_path.read_text(encoding="utf-8"), filename=str(py_path)
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "subprocess":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "subprocess":
                return True
        elif isinstance(node, ast.Attribute) and isinstance(
            node.value, ast.Name
        ):
            if node.value.id == "subprocess":
                return True
    return False


def _module_has_os_env_credential_read(py_path: Path) -> bool:
    tree = ast.parse(
        py_path.read_text(encoding="utf-8"), filename=str(py_path)
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and node.value.attr == "environ"
            and node.attr == "get"
        ):
            return True
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "getenv"
        ):
            return True
    return False


def _collect_imports(py_path: Path) -> set[str]:
    with py_path.open("r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=str(py_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            names.add(node.module.split(".")[0])
    return names


class ArtifactReportPurityTests(unittest.TestCase):
    def test_no_subprocess_import_or_call_in_artifact_report(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(ARTIFACT_REPORT_PATH),
            f"{ARTIFACT_REPORT_PATH} imports or accesses subprocess.",
        )

    def test_no_subprocess_import_or_call_in_test_file(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(Path(__file__)),
            f"{Path(__file__)} imports or accesses subprocess.",
        )

    def test_no_env_credential_reads_in_artifact_report(self) -> None:
        self.assertFalse(
            _module_has_os_env_credential_read(ARTIFACT_REPORT_PATH),
            f"{ARTIFACT_REPORT_PATH} reads environment credentials.",
        )

    def test_no_env_credential_reads_in_dry_run(self) -> None:
        self.assertFalse(
            _module_has_os_env_credential_read(ARTIFACT_DRY_RUN_PY),
            f"{ARTIFACT_DRY_RUN_PY} reads environment credentials.",
        )

    def test_no_subprocess_import_or_call_in_dry_run(self) -> None:
        self.assertFalse(
            _module_has_subprocess_use(ARTIFACT_DRY_RUN_PY),
            f"{ARTIFACT_DRY_RUN_PY} imports or accesses subprocess.",
        )

    def test_no_forbidden_imports(self) -> None:
        forbidden = {
            "requests", "httpx", "aiohttp", "dotenv",
            "subprocess", "os", "shutil", "shelve", "pickle",
            "ib_insync", "ccxt", "alpaca_trade_api", "metatrader5",
            "urllib", "urllib3", "yfinance", "pandas",
        }
        imports = _collect_imports(ARTIFACT_REPORT_PATH)
        bad = imports & forbidden
        self.assertFalse(
            bad,
            f"artifact_report.py imports forbidden modules: {sorted(bad)}",
        )

    def test_no_sox_adapter_in_artifact_report(self) -> None:
        src = ARTIFACT_REPORT_PATH.read_text(encoding="utf-8")
        sox = "S" + "O" + "X"
        fred = "Fred"
        forbidden = (
            fred + sox + "OverlayAdapter",
            sox + "OverlayAdapter",
            "Phlx" + sox + "Adapter",
            sox + "Adapter",
        )
        for token in forbidden:
            self.assertNotIn(
                token,
                src,
                f"artifact_report.py must not reference {token!r}.",
            )

    def test_no_broker_order_account_field_introduced(self) -> None:
        ctx = _minimal_market_context()
        ctx_dict = {
            "session_date": ctx.session_date,
            "timezone": ctx.timezone,
            "us_equities": ctx.us_equities.__dict__,
            "semiconductor": ctx.semiconductor.__dict__,
            "fx": ctx.fx.__dict__,
            "us_yields": ctx.us_yields.__dict__,
            "nikkei_night_session": ctx.nikkei_night_session.__dict__,
            "previous_day": ctx.previous_day.__dict__,
            "economic_event_risk": {
                "events": [
                    e.__dict__ for e in ctx.economic_event_risk.events
                ]
            },
            "intraday_range": ctx.intraday_range.__dict__,
            "volatility_context": ctx.volatility_context.__dict__,
        }
        ctx_dict["account_balance"] = 100000
        with self.assertRaises(ValidationError):
            validate_market_context(ctx_dict)


# --- Raw FRED CSV audit --------------------------------------------------


class RawFREDCSVAuditTests(unittest.TestCase):
    def test_no_raw_fred_csv_committed(self) -> None:
        for d in (EXPORTS_DIR, REPO_ROOT / "fixtures", REPO_ROOT / "reports"):
            if not d.exists():
                continue
            for fp in d.rglob("*"):
                if not fp.is_file():
                    continue
                if fp.suffix.lower() not in (".json", ".csv", ".txt"):
                    continue
                try:
                    txt = fp.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for header in (
                    "DATE,DGS2",
                    "DATE,DGS10",
                    "DATE,SP500",
                    "DATE,DEXJPUS",
                    "DATE,NASDAQ100",
                ):
                    self.assertNotIn(
                        header,
                        txt,
                        f"Raw FRED CSV header {header!r} found in "
                        f"{fp}. PR must not commit raw FRED data.",
                    )


# --- Documentation and dry-run script presence --------------------------


class DocsAndScriptsPresenceTests(unittest.TestCase):
    def test_artifact_report_doc_exists(self) -> None:
        self.assertTrue(
            ARTIFACT_REPORT_DOC.exists(),
            f"Missing docs/market-context-artifact-report.md: "
            f"{ARTIFACT_REPORT_DOC}",
        )

    def test_dry_run_shell_exists(self) -> None:
        self.assertTrue(
            ARTIFACT_DRY_RUN_SH.exists(),
            f"Missing scripts/validate_market_context_artifact_dry_run.sh: "
            f"{ARTIFACT_DRY_RUN_SH}",
        )

    def test_dry_run_shell_uses_strict_mode(self) -> None:
        text = ARTIFACT_DRY_RUN_SH.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)

    def test_dry_run_python_uses_local_file_input(self) -> None:
        text = ARTIFACT_DRY_RUN_PY.read_text(encoding="utf-8")
        # The dry-run must accept --input (local file path).
        self.assertIn("--input", text)
        self.assertIn("--expect-synthetic", text)

    def test_data_adapter_contract_links_to_artifact_report_doc(
        self,
    ) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "market-context-artifact-report.md",
            text,
            "data-adapter-contract.md must link to "
            "docs/market-context-artifact-report.md.",
        )

    def test_data_adapter_contract_section_8_8_present(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "8.8",
            text,
            "data-adapter-contract.md must contain a §8.8 "
            "artifact-report section.",
        )


if __name__ == "__main__":
    unittest.main()
