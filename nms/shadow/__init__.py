"""Shadow trial ledger package.

The shadow trial ledger is the **first step** toward no-cash
test trading. It records deterministic, append-only, no-cash
shadow trial intents from validated ``MarketContext``
artifacts. It is not paper trading. It is not live trading. It
is not broker integration. It is not order placement or order
routing. It is not PnL / win rate / Sharpe / expected return.

See :mod:`nms.shadow.ledger` for the implementation and
:doc:`docs/shadow-trial-ledger` for the contract.
"""

from __future__ import annotations

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


__all__ = [
    "DEFAULT_LEDGER_PATH",
    "SHADOW_TRIAL_NON_CLAIMS",
    "SHADOW_TRIAL_NOT_EXECUTABLE",
    "SHADOW_TRIAL_SCHEMA_VERSION",
    "ShadowTrialLedgerError",
    "ShadowTrialRecord",
    "ShadowTrialScoreSnapshot",
    "append_shadow_trial_record_jsonl",
    "build_shadow_trial_record",
    "load_market_context_from_artifact_for_shadow_trial",
    "shadow_trial_record_to_json_text",
    "shadow_trial_record_to_ordered_dict",
    "sha256_file",
]
