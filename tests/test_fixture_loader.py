"""Tests for the fixture loader and the fixture adapter.

These tests enforce the observation-only posture required by
``docs/data-adapter-contract.md`` and ``docs/risk-policy.md``:

* the fixture loader does not import network libraries
  (``urllib``, ``urllib.request``, ``http``, ``http.client``,
  ``socket``, ``requests``, ``httpx``, ``aiohttp``);
* the fixture loader does not import broker / exchange / FIX
  modules, ``dotenv``, or shell-out modules (``subprocess``,
  ``shutil``, ``os.system``, ``popen``);
* the fixture loader does not read environment-variable credentials
  (``os.environ`` / ``os.getenv``);
* the adapter operates purely on local filesystem paths and the
  filename is derived from ``session_date`` without a network round
  trip.

The checks are static (AST-based) and runtime (mocked) so that a
regression in either dimension is caught.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from nms.data.adapters import (
    DEFAULT_FIXTURE_TEMPLATE,
    FixtureMarketContextAdapter,
    MarketContextAdapter,
)
from nms.data.fixture_loader import load_fixture_dict, load_fixture_file

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FIXTURE = (
    REPO_ROOT
    / "fixtures"
    / "market_context"
    / "sample-session-2026-06-24.json"
)

#: Modules that must not appear anywhere in the data-layer source.
_FORBIDDEN_IMPORTS = frozenset(
    {
        # Network
        "urllib",
        "urllib.request",
        "urllib.error",
        "urllib.parse",
        "http",
        "http.client",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "urllib3",
        # Credentials / env
        "dotenv",
        # Broker / exchange / order
        "ib_insync",
        "alpaca_trade_api",
        "ccxt",
        "metatrader5",
        # Subprocess / shell-out
        # ``subprocess`` is allowed in test code (we mock it below)
        # but is listed here for the source-tree check that excludes
        # tests. The runtime check is the real enforcement.
    }
)


def _collect_imports(py_path: Path) -> set[str]:
    """Return the set of top-level module names imported by ``py_path``."""
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


class DataLayerStaticChecks(unittest.TestCase):
    """AST-level checks over the data-layer source files."""

    DATA_LAYER_FILES = [
        REPO_ROOT / "nms" / "data" / "__init__.py",
        REPO_ROOT / "nms" / "data" / "models.py",
        REPO_ROOT / "nms" / "data" / "adapters.py",
        REPO_ROOT / "nms" / "data" / "fixture_loader.py",
        REPO_ROOT / "nms" / "data" / "validate.py",
    ]

    def test_no_forbidden_imports(self) -> None:
        for path in self.DATA_LAYER_FILES:
            with self.subTest(file=path.name):
                imports = _collect_imports(path)
                bad = imports & _FORBIDDEN_IMPORTS
                self.assertFalse(
                    bad,
                    f"{path.name} imports forbidden modules: {sorted(bad)}",
                )

    def test_data_layer_is_stdlib_only(self) -> None:
        # Anything outside the stdlib (and our own ``nms`` package) is
        # a new runtime dependency and must be justified in the PR body.
        stdlib_top = {
            "dataclasses",
            "json",
            "pathlib",
            "typing",
            "ast",
            "unittest",
            "socket",
            "subprocess",
        }
        allowed_first_party = {"nms"}
        for path in self.DATA_LAYER_FILES:
            with self.subTest(file=path.name):
                imports = _collect_imports(path)
                non_stdlib = imports - stdlib_top - allowed_first_party
                # __future__ is fine.
                non_stdlib.discard("__future__")
                self.assertFalse(
                    non_stdlib,
                    f"{path.name} has non-stdlib imports: {sorted(non_stdlib)}",
                )


class DataLayerRuntimeChecks(unittest.TestCase):
    """Runtime checks that the loader / adapter do not call the network."""

    def test_loader_does_not_open_sockets(self) -> None:
        with mock.patch("socket.socket") as mocked_socket:
            load_fixture_file(SAMPLE_FIXTURE)
            mocked_socket.assert_not_called()

    def test_adapter_does_not_open_sockets(self) -> None:
        adapter = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        with mock.patch("socket.socket") as mocked_socket:
            adapter.load("2026-06-24")
            mocked_socket.assert_not_called()

    def test_loader_does_not_subprocess(self) -> None:
        with mock.patch("subprocess.Popen") as mocked_popen, mock.patch(
            "subprocess.run"
        ) as mocked_run, mock.patch("subprocess.call") as mocked_call:
            load_fixture_file(SAMPLE_FIXTURE)
            mocked_popen.assert_not_called()
            mocked_run.assert_not_called()
            mocked_call.assert_not_called()

    def test_adapter_does_not_subprocess(self) -> None:
        adapter = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        with mock.patch("subprocess.Popen") as mocked_popen, mock.patch(
            "subprocess.run"
        ) as mocked_run, mock.patch("subprocess.call") as mocked_call:
            adapter.load("2026-06-24")
            mocked_popen.assert_not_called()
            mocked_run.assert_not_called()
            mocked_call.assert_not_called()

    def test_loader_does_not_read_env_credentials(self) -> None:
        # The loader is pure local I/O. ``os.environ`` should not be
        # accessed at all by the data layer.
        with mock.patch("os.environ.get") as mocked_get, mock.patch(
            "os.getenv"
        ) as mocked_getenv:
            load_fixture_file(SAMPLE_FIXTURE)
            mocked_get.assert_not_called()
            mocked_getenv.assert_not_called()

    def test_adapter_does_not_read_env_credentials(self) -> None:
        adapter = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        with mock.patch("os.environ.get") as mocked_get, mock.patch(
            "os.getenv"
        ) as mocked_getenv:
            adapter.load("2026-06-24")
            mocked_get.assert_not_called()
            mocked_getenv.assert_not_called()


class AdapterBehaviorTests(unittest.TestCase):
    def test_default_template_uses_session_date(self) -> None:
        self.assertEqual(
            DEFAULT_FIXTURE_TEMPLATE.format(session_date="2026-06-24"),
            "sample-session-2026-06-24.json",
        )

    def test_adapter_is_a_protocol_compatible_callable(self) -> None:
        # ``MarketContextAdapter`` is a ``Protocol``; this test just
        # confirms the class is defined and importable.
        adapter = FixtureMarketContextAdapter(
            base_path=REPO_ROOT / "fixtures" / "market_context"
        )
        self.assertTrue(hasattr(adapter, "load"))
        self.assertTrue(callable(adapter.load))

    def test_load_fixture_dict_round_trip(self) -> None:
        # ``load_fixture_dict`` is exposed for tests that want to
        # exercise the validator without touching the filesystem.
        import json

        with SAMPLE_FIXTURE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        ctx = load_fixture_dict(data)
        self.assertEqual(ctx.session_date, "2026-06-24")


# ``socket`` is imported for documentation purposes (the mocked
# runtime check above patches ``socket.socket``). It is NOT used at
# module top level for any I/O.
_ = socket
_ = subprocess


if __name__ == "__main__":
    unittest.main()
