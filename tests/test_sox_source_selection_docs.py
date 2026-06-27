"""Tests for the SOX / semiconductor source-selection contract.

These tests enforce the SOX source-selection contract documented in
``docs/sox-source-selection.md``. They do **not** test any SOX
adapter, because no SOX adapter is approved yet.

The tests are documentation-level: they read the source-selection
document, the parent data-adapter-contract document, and the
repository tree, and they assert that:

* The source-selection document exists and contains the required
  structural pieces (decision block, exact-vs-proxy distinction,
  SOXX / SMH mention, no-adapter-yet language, no-raw-data
  language, no-broker / no-auth language).
* The parent data-adapter-contract links to the source-selection
  document.
* No ``nms/data/*sox*`` adapter file exists in the repository.
* No ``scripts/*sox*`` file exists in the repository.
* ``pyproject.toml`` does not introduce any forbidden market-data
  runtime dependency.
* No GitHub workflow references the SOX source-selection doc.
* No raw SOX / SOXX / SMH / PHLX / Nasdaq Semiconductor data is
  committed under ``fixtures/``, ``exports/``, or ``reports/``.

All checks are pure filesystem / static checks. **No subprocess
calls are performed**, in line with the PR's ``no_subprocess: yes``
safety claim.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOX_DOC = REPO_ROOT / "docs" / "sox-source-selection.md"
DATA_ADAPTER_CONTRACT = REPO_ROOT / "docs" / "data-adapter-contract.md"
NMS_DATA_DIR = REPO_ROOT / "nms" / "data"
SCRIPTS_DIR = REPO_ROOT / "scripts"
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
FIXTURES_DIR = REPO_ROOT / "fixtures"
EXPORTS_DIR = REPO_ROOT / "exports"
REPORTS_DIR = REPO_ROOT / "reports"


# --- Source-selection doc tests -------------------------------------------


class SoxSourceSelectionDocTests(unittest.TestCase):
    """Enforce the structural requirements of the SOX source
    selection document.
    """

    def setUp(self) -> None:
        self.text = SOX_DOC.read_text(encoding="utf-8")

    def test_doc_exists(self) -> None:
        self.assertTrue(
            SOX_DOC.exists(),
            f"Missing source-selection document: {SOX_DOC}",
        )

    def test_doc_contains_decision_block(self) -> None:
        self.assertIn(
            "sox_source_decision",
            self.text,
            "Source-selection document must contain a "
            "sox_source_decision block.",
        )

    def test_doc_distinguishes_exact_vs_proxy(self) -> None:
        # Must contain both 'exact' (in the exact-vs-proxy sense)
        # and 'proxy' as explicit terms.
        self.assertIn("exact", self.text.lower())
        self.assertIn("proxy", self.text.lower())
        # The exact-index and proxy-etf rubrics should both appear.
        self.assertTrue(
            "exact_or_proxy" in self.text or "exact" in self.text,
            "Document must call out exact vs proxy.",
        )

    def test_doc_mentions_sox(self) -> None:
        self.assertIn("SOX", self.text)

    def test_doc_mentions_soxx(self) -> None:
        self.assertIn("SOXX", self.text)

    def test_doc_mentions_smh(self) -> None:
        self.assertIn("SMH", self.text)

    def test_doc_states_soxx_smh_are_proxies_not_exact_sox(self) -> None:
        # SOXX and SMH must be explicitly labeled as proxies /
        # ETFs, not as the exact SOX index. The check looks at
        # the candidate YAML blocks (each starting with "- name:")
        # and asserts that any block mentioning SOXX or SMH is
        # labeled as a proxy (exact_or_proxy: proxy) and the
        # recommended_status is not 'preferred'.
        # We split on lines that start a new candidate block or a
        # new section header (any '#') so the candidate YAML is
        # isolated from the surrounding prose and headings.
        lines = self.text.splitlines()
        blocks: list[str] = []
        current: list[str] = []
        for line in lines:
            if line.startswith("- name:") and current:
                blocks.append("\n".join(current))
                current = [line]
            elif line.startswith("- name:"):
                current = [line]
            elif line.lstrip().startswith("#") and current:
                blocks.append("\n".join(current))
                current = []
            else:
                current.append(line)
        if current:
            blocks.append("\n".join(current))

        for token in ("SOXX", "SMH"):
            relevant = [
                b
                for b in blocks
                if token in b and "- name:" in b
            ]
            self.assertTrue(
                relevant,
                f"No candidate block in the doc mentions {token}.",
            )
            for block in relevant:
                self.assertIn(
                    "exact_or_proxy: proxy",
                    block,
                    f"{token} candidate must be labeled "
                    f"exact_or_proxy: proxy. Block:\n{block}",
                )
                # The recommended_status of the SOXX / SMH
                # candidate block must be 'defer' or 'reject' —
                # not 'preferred' or 'acceptable_proxy'. The
                # contract decision in §4 is defer_adapter, so
                # the candidate block must defer, not just
                # quietly allow it.
                self.assertIn(
                    "recommended_status: defer",
                    block,
                    f"{token} candidate must be deferred, not "
                    f"preferred. Block:\n{block}",
                )
                # And the block must contain a sentence
                # explaining that it is not the SOX index.
                # Markdown bold may be present, so we strip `**`
                # before checking.
                stripped = block.replace("**", "")
                self.assertTrue(
                    "not the SOX index" in stripped
                    or "not the PHLX Semiconductor Sector Index" in stripped
                    or "not the PHLX" in stripped,
                    f"{token} candidate must state it is not the "
                    f"SOX index. Block:\n{block}",
                )

    def test_doc_states_no_adapter_approved_yet(self) -> None:
        # The defer_adapter decision must be explicit.
        self.assertIn("defer_adapter", self.text)
        # And the body must say no adapter is approved.
        self.assertTrue(
            "no adapter" in self.text.lower()
            or "no SOX adapter" in self.text
            or "no SOX / semiconductor source" in self.text
            or "not yet" in self.text.lower()
            or "deferred" in self.text.lower(),
            "Document must say no SOX adapter is approved yet.",
        )

    def test_doc_states_no_raw_sox_or_proxy_data_committed(self) -> None:
        # Must forbid committing raw index data.
        self.assertIn("raw", self.text.lower())
        # And must explicitly mention 'no raw' or equivalent.
        self.assertTrue(
            "no raw" in self.text.lower()
            or "must not be committed" in self.text.lower()
            or "may be committed" in self.text.lower(),
            "Document must say no raw SOX / SOXX / SMH data is "
            "committed.",
        )

    def test_doc_states_no_broker_auth_cookie_paid_source(self) -> None:
        # Must forbid broker / auth / cookie / paid source.
        for token in ("broker", "auth", "cookie", "paid"):
            self.assertIn(
                token,
                self.text.lower(),
                f"Document must mention the forbidden term {token!r}.",
            )
        # And there must be an explicit rejection sentence.
        self.assertTrue(
            "reject" in self.text.lower(),
            "Document must reject broker / paid source explicitly.",
        )


# --- Parent contract doc tests -------------------------------------------


class DataAdapterContractLinkTests(unittest.TestCase):
    """Enforce that ``docs/data-adapter-contract.md`` links to the
    SOX source-selection document.
    """

    def test_parent_contract_links_to_sox_doc(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        self.assertIn(
            "sox-source-selection.md",
            text,
            "data-adapter-contract.md must link to "
            "sox-source-selection.md.",
        )

    def test_parent_contract_section_8_5_present(self) -> None:
        text = DATA_ADAPTER_CONTRACT.read_text(encoding="utf-8")
        # We require an explicit "8.5" future-SOX section.
        self.assertIn(
            "8.5",
            text,
            "data-adapter-contract.md must contain a §8.5 future-SOX "
            "section.",
        )


# --- Repository-state tests -----------------------------------------------


class SoxScopeRepositoryStateTests(unittest.TestCase):
    """Enforce that this PR is source-selection only: no SOX adapter
    is added, no new runtime dependency, no workflow changes, no raw
    SOX / SOXX / SMH data committed.

    All checks are pure filesystem / static checks. No subprocess
    calls are performed.
    """

    def test_no_sox_adapter_file_exists_under_nms_data(self) -> None:
        # No nms/data/*sox* file may exist in the repository.
        # The test is a static filesystem check (no git diff).
        if not NMS_DATA_DIR.exists():
            return
        bad = [
            str(p)
            for p in NMS_DATA_DIR.rglob("*")
            if p.is_file() and "sox" in p.name.lower()
        ]
        self.assertEqual(
            bad,
            [],
            f"No nms/data/*sox* file may be added: {bad}",
        )

    def test_no_sox_script_file_exists(self) -> None:
        # No scripts/*sox* file may exist in the repository.
        # The test is a static filesystem check (no git diff).
        if not SCRIPTS_DIR.exists():
            return
        bad = [
            str(p)
            for p in SCRIPTS_DIR.rglob("*")
            if p.is_file() and "sox" in p.name.lower()
        ]
        self.assertEqual(
            bad,
            [],
            f"No scripts/*sox* file may be added: {bad}",
        )

    def test_pyproject_has_no_forbidden_market_data_dependency(self) -> None:
        # pyproject.toml must not introduce any forbidden
        # market-data runtime dependency. This is a static
        # filesystem / static-text check, not a git diff.
        text = PYPROJECT.read_text(encoding="utf-8")
        for token in (
            "requests",
            "httpx",
            "aiohttp",
            "yfinance",
            "pandas-datareader",
        ):
            self.assertNotIn(
                token,
                text,
                f"pyproject.toml must not introduce {token!r} as a "
                f"runtime dependency.",
            )

    def test_workflows_do_not_reference_sox_source_selection(self) -> None:
        # No GitHub workflow should reference the SOX
        # source-selection doc. This is a static filesystem /
        # static-text check. The actual "no workflow file
        # changed in this PR" check is done at PR review time
        # via the changed-files list and CI report, not by
        # running git diff inside a unit test.
        if not WORKFLOWS_DIR.exists():
            return
        for fp in WORKFLOWS_DIR.rglob("*"):
            if not fp.is_file():
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            self.assertNotIn(
                "sox-source-selection",
                text.lower(),
                f"Workflow file must not reference sox-source-selection: "
                f"{fp}",
            )

    def test_no_raw_sox_data_committed(self) -> None:
        # No raw downloaded SOX / SOXX / SMH / PHLX / Nasdaq
        # Semiconductor data may be committed under fixtures,
        # exports, or reports.
        for d in (FIXTURES_DIR, EXPORTS_DIR, REPORTS_DIR):
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
                for token in (
                    "SOX",
                    "SOXX",
                    "SMH",
                    "PHLX Semiconductor",
                    "NASDAQ Semiconductor",
                ):
                    self.assertNotIn(
                        token,
                        txt,
                        f"Raw SOX-related data committed in {fp} "
                        f"(matched {token!r}).",
                    )


if __name__ == "__main__":
    unittest.main()
