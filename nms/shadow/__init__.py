"""Shadow trial ledger, close, replay, and integrity package.

This package provides four layers:

* :mod:`nms.shadow.ledger` — the **first step** toward
  no-cash test trading. It records deterministic,
  append-only, no-cash shadow trial intents from
  validated ``MarketContext`` artifacts.
* :mod:`nms.shadow.close` — the **second step**. It
  records a separate, local-only close record from an
  existing shadow trial record plus an operator-provided
  ``close_price``.
* :mod:`nms.shadow.replay` — the **third step**. It runs
  a local append-only replay over a manifest of
  ``MarketContext`` artifacts and operator-provided
  inputs. It records counts and per-row statuses only. It
  is not a backtest.
* :mod:`nms.shadow.integrity` — the **fourth step**. It
  checks one replay result against local trial / close
  ledgers using counts, statuses, identifiers, and
  duplicate detection only.

None of these layers is paper trading. None is live
trading. None is venue integration. None is order
placement or order routing. None is money-delta / ratio
/ risk-adjusted / forward-return / expected-return /
win-count / equity-curve / portfolio / strategy-
performance. None maintains a capital account or virtual
exposure state.

See :mod:`nms.shadow.ledger`, :mod:`nms.shadow.close`,
:mod:`nms.shadow.replay`, and :mod:`nms.shadow.integrity`
for the implementations and :doc:`docs/shadow-trial-ledger`,
:doc:`docs/shadow-trial-close`,
:doc:`docs/shadow-replay-manifest`, and
:doc:`docs/shadow-replay-integrity-checker` for the
contracts.
"""

from __future__ import annotations

from nms.shadow.close import (
    DEFAULT_CLOSE_LEDGER_PATH,
    SHADOW_CLOSE_NON_CLAIMS,
    SHADOW_CLOSE_NOT_EXECUTABLE,
    SHADOW_CLOSE_SCHEMA_VERSION,
    ShadowTrialCloseError,
    ShadowTrialCloseRecord,
    append_shadow_trial_close_record_jsonl,
    build_shadow_trial_close_record,
    shadow_trial_close_record_to_json_text,
    shadow_trial_close_record_to_ordered_dict,
)
from nms.shadow.integrity import (
    SHADOW_REPLAY_INTEGRITY_NON_CLAIMS,
    SHADOW_REPLAY_INTEGRITY_REPORT_SCHEMA_VERSION,
    ShadowReplayIntegrityIssue,
    ShadowReplayIntegrityReport,
    build_shadow_replay_integrity_report,
    shadow_replay_integrity_report_to_json_text,
    shadow_replay_integrity_report_to_ordered_dict,
    write_shadow_replay_integrity_report_json,
)
from nms.shadow.ledger import (
    DEFAULT_LEDGER_PATH,
    SHADOW_TRIAL_NON_CLAIMS,
    SHADOW_TRIAL_NOT_EXECUTABLE,
    SHADOW_TRIAL_SCHEMA_VERSION,
    ShadowTrialLedgerError,
    ShadowTrialRecord,
    ShadowTrialScoreSnapshot,
    append_shadow_trial_record_jsonl,
    build_shadow_trial_record,
    load_market_context_from_artifact_for_shadow_trial,
    shadow_trial_record_to_json_text,
    shadow_trial_record_to_ordered_dict,
    sha256_file,
)
from nms.shadow.replay import (
    ROW_STATUS_CLOSE_CREATED,
    ROW_STATUS_ROW_ERROR,
    ROW_STATUS_TRIAL_CREATED,
    SHADOW_REPLAY_INPUT_SCHEMA_VERSION,
    SHADOW_REPLAY_NON_CLAIMS,
    SHADOW_REPLAY_RESULT_SCHEMA_VERSION,
    ShadowReplayError,
    ShadowReplayResultManifest,
    ShadowReplayRow,
    ShadowReplayRowResult,
    load_shadow_replay_input_manifest,
    run_shadow_replay_manifest,
    shadow_replay_result_to_json_text,
    shadow_replay_result_to_ordered_dict,
    write_shadow_replay_result_json,
)


__all__ = [
    "DEFAULT_CLOSE_LEDGER_PATH",
    "DEFAULT_LEDGER_PATH",
    "ROW_STATUS_CLOSE_CREATED",
    "ROW_STATUS_ROW_ERROR",
    "ROW_STATUS_TRIAL_CREATED",
    "SHADOW_CLOSE_NON_CLAIMS",
    "SHADOW_CLOSE_NOT_EXECUTABLE",
    "SHADOW_CLOSE_SCHEMA_VERSION",
    "SHADOW_REPLAY_INPUT_SCHEMA_VERSION",
    "SHADOW_REPLAY_INTEGRITY_NON_CLAIMS",
    "SHADOW_REPLAY_INTEGRITY_REPORT_SCHEMA_VERSION",
    "SHADOW_REPLAY_NON_CLAIMS",
    "SHADOW_REPLAY_RESULT_SCHEMA_VERSION",
    "SHADOW_TRIAL_NON_CLAIMS",
    "SHADOW_TRIAL_NOT_EXECUTABLE",
    "SHADOW_TRIAL_SCHEMA_VERSION",
    "ShadowReplayError",
    "ShadowReplayIntegrityIssue",
    "ShadowReplayIntegrityReport",
    "ShadowReplayResultManifest",
    "ShadowReplayRow",
    "ShadowReplayRowResult",
    "ShadowTrialCloseError",
    "ShadowTrialCloseRecord",
    "ShadowTrialLedgerError",
    "ShadowTrialRecord",
    "ShadowTrialScoreSnapshot",
    "append_shadow_trial_close_record_jsonl",
    "append_shadow_trial_record_jsonl",
    "build_shadow_replay_integrity_report",
    "build_shadow_trial_close_record",
    "build_shadow_trial_record",
    "load_market_context_from_artifact_for_shadow_trial",
    "load_shadow_replay_input_manifest",
    "run_shadow_replay_manifest",
    "shadow_replay_integrity_report_to_json_text",
    "shadow_replay_integrity_report_to_ordered_dict",
    "shadow_replay_result_to_json_text",
    "shadow_replay_result_to_ordered_dict",
    "shadow_trial_close_record_to_json_text",
    "shadow_trial_close_record_to_ordered_dict",
    "shadow_trial_record_to_json_text",
    "shadow_trial_record_to_ordered_dict",
    "sha256_file",
    "write_shadow_replay_integrity_report_json",
    "write_shadow_replay_result_json",
]
