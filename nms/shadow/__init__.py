"""Shadow trial ledger and close package.

This package provides two layers:

* :mod:`nms.shadow.ledger` — the **first step** toward
  no-cash test trading. It records deterministic,
  append-only, no-cash shadow trial intents from
  validated ``MarketContext`` artifacts.
* :mod:`nms.shadow.close` — the **second step**. It
  records a separate, local-only close record from an
  existing shadow trial record plus an operator-provided
  ``close_price``.

Neither layer is paper trading. Neither is live trading.
Neither is broker integration. Neither is order placement
or order routing. Neither is PnL / win rate / risk-adjusted /
forward return / Sharpe / expected return / profit.

See :mod:`nms.shadow.ledger` and :mod:`nms.shadow.close` for
the implementations and :doc:`docs/shadow-trial-ledger` and
:doc:`docs/shadow-trial-close` for the contracts.
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
    "DEFAULT_CLOSE_LEDGER_PATH",
    "DEFAULT_LEDGER_PATH",
    "SHADOW_CLOSE_NON_CLAIMS",
    "SHADOW_CLOSE_NOT_EXECUTABLE",
    "SHADOW_CLOSE_SCHEMA_VERSION",
    "SHADOW_TRIAL_NON_CLAIMS",
    "SHADOW_TRIAL_NOT_EXECUTABLE",
    "SHADOW_TRIAL_SCHEMA_VERSION",
    "ShadowTrialCloseError",
    "ShadowTrialCloseRecord",
    "ShadowTrialLedgerError",
    "ShadowTrialRecord",
    "ShadowTrialScoreSnapshot",
    "append_shadow_trial_close_record_jsonl",
    "append_shadow_trial_record_jsonl",
    "build_shadow_trial_close_record",
    "build_shadow_trial_record",
    "load_market_context_from_artifact_for_shadow_trial",
    "shadow_trial_close_record_to_json_text",
    "shadow_trial_close_record_to_ordered_dict",
    "shadow_trial_record_to_json_text",
    "shadow_trial_record_to_ordered_dict",
    "sha256_file",
]
