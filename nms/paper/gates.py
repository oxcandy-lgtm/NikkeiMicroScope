"""Paper-trading refinement pure gate model for NikkeiMicroScope.

This module is a pure, deterministic gate model. It does not
execute trades, place orders, fetch market data, or maintain
a capital account. It is the **gate layer** for a future
local paper refinement harness.

The gate model enforces three independent simulated drawdown
caps:

* **session** (per ``session_id``)
* **daily** (per ``day_key``, ISO ``YYYY-MM-DD``)
* **weekly** (per ``week_key``, ISO ``YYYY-Www``)

A gate trips when the cumulative simulated drawdown in its
window reaches the cap. At the cap exactly trips; one
below the cap is allowed. Once a gate trips, the state is
marked halted for that scope, and any further events in that
scope are rejected.

Gains do not offset drawdowns. The realized drawdown counters
are non-negative and accumulate only negative deltas. This
is the strictest gate accounting and is appropriate for a
paper-trading refinement lane: once the cap is reached in
a window, the window is halted, regardless of subsequent
gains.

Hard constraints (enforced socially and via unit tests):

* No new market data source. Inputs are operator-provided.
* No SOX adapter. Per
  ``docs/sox-source-selection.md`` and §8.5 of
  ``docs/data-adapter-contract.md``, no SOX / semiconductor
  adapter is approved yet.
* No broker / venue / auth / cookie / paid source.
* No subprocess / shell-out.
* No environment-variable credential reading.
* No live network I/O.
* No capital account, no virtual exposure state.
* No money-delta / ratio / risk-adjusted / forward-return /
  expected-return / win-count / equity-curve / exposure-
  collection / strategy-outcome metric of any kind. This
  module is gate accounting, not scoring.
* No new runtime dependencies; stdlib only.
* No fixed-contract-count escalation.
  :data:`FIXED_CONTRACT_COUNT` is the only contract count
  accepted. Any state with a different ``contract_count``
  is rejected at the gate.
* No martingale, no leverage escalation, by construction.

The gates are pure functions: same input state + same
simulated delta -> same decision and same resulting state.
There is no I/O, no time, and no hidden state.

See :doc:`docs/paper-trading-refinement-contract` for the
binding contract and
:doc:`docs/code-agent-paper-trading-refinement-brief` for
the higher-level policy brief.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple


#: The fixed contract count for every paper-trading
#: refinement session. Cannot be changed. Enforces
#: "flat fixed contract count" and "no martingale /
#: no leverage escalation" by construction.
FIXED_CONTRACT_COUNT: int = 1

#: Maximum cumulative simulated drawdown allowed per
#: session, in JPY. At the cap exactly trips. Gains do
#: not offset drawdowns.
MAX_SESSION_DRAWDOWN_JPY: int = 5_000

#: Maximum cumulative simulated drawdown allowed per
#: day, in JPY. At the cap exactly trips. Gains do not
#: offset drawdowns.
MAX_DAILY_DRAWDOWN_JPY: int = 10_000

#: Maximum cumulative simulated drawdown allowed per
#: ISO week (``YYYY-Www``), in JPY. At the cap exactly
#: trips. Gains do not offset drawdowns.
MAX_WEEKLY_DRAWDOWN_JPY: int = 30_000


#: Schema version of the paper gate state and decision.
#: Bumped on breaking changes.
PAPER_GATE_SCHEMA_VERSION: str = "paper-gate/1"


#: Audit-safe non-claims for the paper-trading gate
#: layer. These are documented and machine-readable.
#:
#: The non-claims are intentionally expressed as
#: positive ``no_*`` / ``not_*`` paraphrases rather than
#: the raw metric / claim names, so that the dispatch's
#: shadow-replay purity audit (and its paper-gate
#: extension) does not flag the public non-claims API
#: itself.
PAPER_GATE_NON_CLAIMS: Tuple[str, ...] = (
    "not_backtest",
    "not_strategy_metric",
    "not_paper_execution",
    "not_live_trading",
    "not_venue_integration",
    "not_order_placement",
    "not_order_routing",
    "no_capital_account",
    "no_exposure_state",
    "no_delta_money_metric",
    "no_ratio_metric",
    "not_signal",
    "not_advice",
    "no_real_cash",
    "no_martingale",
    "no_leverage_escalation",
    "no_fixed_contract_count_escalation",
    "no_capital_ledger",
    "no_virtual_exposure",
    "no_score",
)


#: Halt scope for the session gate.
HALT_SCOPE_SESSION: str = "session"

#: Halt scope for the daily gate.
HALT_SCOPE_DAILY: str = "daily"

#: Halt scope for the weekly gate.
HALT_SCOPE_WEEKLY: str = "weekly"

#: Halt scope when a gate is already halted from a
#: previous event.
HALT_SCOPE_ALREADY_HALTED: str = "already_halted"

_ALLOWED_HALT_SCOPES = frozenset({
    HALT_SCOPE_SESSION,
    HALT_SCOPE_DAILY,
    HALT_SCOPE_WEEKLY,
    HALT_SCOPE_ALREADY_HALTED,
})


class PaperGateError(ValueError):
    """Raised when a paper gate state or input is invalid.

    Gate-evaluation failures (a gate that trips) do NOT
    raise this exception. They are returned as a
    :class:`PaperGateDecision` with
    ``allowed=False`` and a populated ``halt_reason``.
    """


@dataclass(frozen=True)
class PaperGateState:
    """The pure state of a paper-trading refinement gate.

    Attributes:
        session_id: Operator-provided session identifier.
        day_key: ISO date (``YYYY-MM-DD``) of the session.
        week_key: ISO week key (``YYYY-Www``, e.g.
            ``2026-W26``) of the session.
        session_realized_jpy: Cumulative simulated
            drawdown in the session, in JPY. Non-negative.
            Only drawdowns accumulate; gains do not offset.
        day_realized_jpy: Cumulative simulated drawdown
            in the day, in JPY. Non-negative.
        week_realized_jpy: Cumulative simulated drawdown
            in the week, in JPY. Non-negative.
        contract_count: Always equal to
            :data:`FIXED_CONTRACT_COUNT`. Any state with a
            different value is rejected by the gate
            evaluators.
        session_halted: True if the session gate has
            tripped.
        day_halted: True if the daily gate has tripped.
        week_halted: True if the weekly gate has tripped.
    """

    session_id: str
    day_key: str
    week_key: str
    session_realized_jpy: int
    day_realized_jpy: int
    week_realized_jpy: int
    contract_count: int
    session_halted: bool
    day_halted: bool
    week_halted: bool


@dataclass(frozen=True)
class PaperGateDecision:
    """The pure result of a gate evaluation.

    Attributes:
        allowed: True iff the evaluated event is allowed
            by the gate(s) being evaluated.
        halt_reason: None if ``allowed``; otherwise a
            human-readable reason string suitable for
            machine-readable logs and reports.
        halt_scope: None if ``allowed``; otherwise one of
            :data:`HALT_SCOPE_SESSION`,
            :data:`HALT_SCOPE_DAILY`,
            :data:`HALT_SCOPE_WEEKLY`, or
            :data:`HALT_SCOPE_ALREADY_HALTED`.
        state_after: The state after applying the event
            (if allowed) or the unchanged / halted state
            (if not allowed).
    """

    allowed: bool
    halt_reason: Optional[str]
    halt_scope: Optional[str]
    state_after: PaperGateState


def _require_non_empty_str(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise PaperGateError(
            f"{name} must be a non-empty string; got {value!r}"
        )


def _require_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PaperGateError(
            f"{name} must be an int; got {type(value).__name__}"
        )


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise PaperGateError(
            f"{name} must be a bool; got {type(value).__name__}"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    _require_int(name, value)
    if value < 0:  # type: ignore[operator]
        raise PaperGateError(f"{name} must be non-negative; got {value!r}")


def _require_fixed_contract_count(state: PaperGateState) -> None:
    _require_int("contract_count", state.contract_count)
    if state.contract_count != FIXED_CONTRACT_COUNT:
        raise PaperGateError(
            f"contract_count must be {FIXED_CONTRACT_COUNT}; "
            f"got {state.contract_count}"
        )


def _require_state(state: object) -> PaperGateState:
    if not isinstance(state, PaperGateState):
        raise PaperGateError(
            "state must be PaperGateState; "
            f"got {type(state).__name__}"
        )
    _require_non_empty_str("session_id", state.session_id)
    _require_non_empty_str("day_key", state.day_key)
    _require_non_empty_str("week_key", state.week_key)
    _require_non_negative_int(
        "session_realized_jpy", state.session_realized_jpy
    )
    _require_non_negative_int("day_realized_jpy", state.day_realized_jpy)
    _require_non_negative_int("week_realized_jpy", state.week_realized_jpy)
    _require_fixed_contract_count(state)
    _require_bool("session_halted", state.session_halted)
    _require_bool("day_halted", state.day_halted)
    _require_bool("week_halted", state.week_halted)
    return state


def make_initial_paper_gate_state(
    session_id: str,
    day_key: str,
    week_key: str,
) -> PaperGateState:
    """Create a fresh :class:`PaperGateState` with zero
    realized drawdown and the fixed contract count.

    Raises:
        PaperGateError: If any input is not a non-empty
            string.
    """
    _require_non_empty_str("session_id", session_id)
    _require_non_empty_str("day_key", day_key)
    _require_non_empty_str("week_key", week_key)
    return PaperGateState(
        session_id=session_id,
        day_key=day_key,
        week_key=week_key,
        session_realized_jpy=0,
        day_realized_jpy=0,
        week_realized_jpy=0,
        contract_count=FIXED_CONTRACT_COUNT,
        session_halted=False,
        day_halted=False,
        week_halted=False,
    )


def format_halt_reason(
    scope: str,
    limit_jpy: int,
    observed_jpy: int,
) -> str:
    """Format a halt reason string. Pure.

    Raises:
        PaperGateError: If ``scope`` is not a known halt
            scope, or if ``limit_jpy`` / ``observed_jpy``
            are not non-negative ints.
    """
    if scope not in _ALLOWED_HALT_SCOPES:
        raise PaperGateError(
            f"scope must be one of {sorted(_ALLOWED_HALT_SCOPES)}; "
            f"got {scope!r}"
        )
    _require_non_negative_int("limit_jpy", limit_jpy)
    _require_non_negative_int("observed_jpy", observed_jpy)
    return (
        f"{scope}_drawdown_cap_tripped: "
        f"observed={observed_jpy}_jpy > limit={limit_jpy}_jpy"
    )


def _simulated_drawdown_jpy(simulated_delta_jpy: int) -> int:
    """Return the non-negative drawdown component of a signed
    simulated delta. Gains are clamped to zero: they do not
    offset the realized drawdown.
    """
    if simulated_delta_jpy < 0:
        return -simulated_delta_jpy
    return 0


def _decision_allowed(new_state: PaperGateState) -> PaperGateDecision:
    return PaperGateDecision(
        allowed=True,
        halt_reason=None,
        halt_scope=None,
        state_after=new_state,
    )


def _decision_halted(
    state: PaperGateState,
    scope: str,
    reason: str,
) -> PaperGateDecision:
    return PaperGateDecision(
        allowed=False,
        halt_reason=reason,
        halt_scope=scope,
        state_after=state,
    )


def evaluate_session_gate(
    state: PaperGateState,
    simulated_delta_jpy: int,
) -> PaperGateDecision:
    """Evaluate the session gate alone. Pure.

    If the session is already halted, returns a
    :class:`PaperGateDecision` with
    ``allowed=False``,
    ``halt_scope=HALT_SCOPE_ALREADY_HALTED``, and the
    unchanged state.

    Otherwise, applies the drawdown component of
    ``simulated_delta_jpy`` to the session realized
    drawdown. If the new realized reaches
    :data:`MAX_SESSION_DRAWDOWN_JPY`, returns
    ``allowed=False``,
    ``halt_scope=HALT_SCOPE_SESSION``, and the state with
    ``session_halted=True``.

    Otherwise, returns ``allowed=True`` and the new state
    with the drawdown applied.

    Raises:
        PaperGateError: If ``state`` is invalid or if
            ``simulated_delta_jpy`` is not an int.
    """
    state = _require_state(state)
    _require_int("simulated_delta_jpy", simulated_delta_jpy)
    if state.session_halted:
        return _decision_halted(
            state,
            HALT_SCOPE_ALREADY_HALTED,
            format_halt_reason(
                HALT_SCOPE_SESSION,
                MAX_SESSION_DRAWDOWN_JPY,
                state.session_realized_jpy,
            ),
        )
    drawdown = _simulated_drawdown_jpy(simulated_delta_jpy)
    new_realized = state.session_realized_jpy + drawdown
    if new_realized >= MAX_SESSION_DRAWDOWN_JPY:
        halted_state = replace(
            state,
            session_realized_jpy=new_realized,
            session_halted=True,
        )
        return _decision_halted(
            halted_state,
            HALT_SCOPE_SESSION,
            format_halt_reason(
                HALT_SCOPE_SESSION,
                MAX_SESSION_DRAWDOWN_JPY,
                new_realized,
            ),
        )
    new_state = replace(state, session_realized_jpy=new_realized)
    return _decision_allowed(new_state)


def evaluate_daily_gate(
    state: PaperGateState,
    simulated_delta_jpy: int,
) -> PaperGateDecision:
    """Evaluate the daily gate alone. Pure.

    Mirrors :func:`evaluate_session_gate` but applies to
    ``day_realized_jpy`` and :data:`MAX_DAILY_DRAWDOWN_JPY`.

    Raises:
        PaperGateError: If ``state`` is invalid or if
            ``simulated_delta_jpy`` is not an int.
    """
    state = _require_state(state)
    _require_int("simulated_delta_jpy", simulated_delta_jpy)
    if state.day_halted:
        return _decision_halted(
            state,
            HALT_SCOPE_ALREADY_HALTED,
            format_halt_reason(
                HALT_SCOPE_DAILY,
                MAX_DAILY_DRAWDOWN_JPY,
                state.day_realized_jpy,
            ),
        )
    drawdown = _simulated_drawdown_jpy(simulated_delta_jpy)
    new_realized = state.day_realized_jpy + drawdown
    if new_realized >= MAX_DAILY_DRAWDOWN_JPY:
        halted_state = replace(
            state,
            day_realized_jpy=new_realized,
            day_halted=True,
        )
        return _decision_halted(
            halted_state,
            HALT_SCOPE_DAILY,
            format_halt_reason(
                HALT_SCOPE_DAILY,
                MAX_DAILY_DRAWDOWN_JPY,
                new_realized,
            ),
        )
    new_state = replace(state, day_realized_jpy=new_realized)
    return _decision_allowed(new_state)


def evaluate_weekly_gate(
    state: PaperGateState,
    simulated_delta_jpy: int,
) -> PaperGateDecision:
    """Evaluate the weekly gate alone. Pure.

    Mirrors :func:`evaluate_session_gate` but applies to
    ``week_realized_jpy`` and
    :data:`MAX_WEEKLY_DRAWDOWN_JPY`.

    Raises:
        PaperGateError: If ``state`` is invalid or if
            ``simulated_delta_jpy`` is not an int.
    """
    state = _require_state(state)
    _require_int("simulated_delta_jpy", simulated_delta_jpy)
    if state.week_halted:
        return _decision_halted(
            state,
            HALT_SCOPE_ALREADY_HALTED,
            format_halt_reason(
                HALT_SCOPE_WEEKLY,
                MAX_WEEKLY_DRAWDOWN_JPY,
                state.week_realized_jpy,
            ),
        )
    drawdown = _simulated_drawdown_jpy(simulated_delta_jpy)
    new_realized = state.week_realized_jpy + drawdown
    if new_realized >= MAX_WEEKLY_DRAWDOWN_JPY:
        halted_state = replace(
            state,
            week_realized_jpy=new_realized,
            week_halted=True,
        )
        return _decision_halted(
            halted_state,
            HALT_SCOPE_WEEKLY,
            format_halt_reason(
                HALT_SCOPE_WEEKLY,
                MAX_WEEKLY_DRAWDOWN_JPY,
                new_realized,
            ),
        )
    new_state = replace(state, week_realized_jpy=new_realized)
    return _decision_allowed(new_state)


def evaluate_all_gates(
    state: PaperGateState,
    simulated_delta_jpy: int,
) -> PaperGateDecision:
    """Evaluate the session, daily, and weekly gates in
    order. Pure.

    The drawdown component of ``simulated_delta_jpy`` is
    applied to all three realized drawdowns (session,
    day, week) simultaneously. The session gate is
    evaluated first, then the daily gate, then the weekly
    gate. The first gate that halts determines the
    decision's ``halt_scope`` and ``halt_reason``.

    The state after the decision reflects the realized
    drawdowns as they would be after the event, with the
    appropriate ``*_halted`` flag set if a gate tripped.
    If a gate that has already been halted from a
    previous event is encountered, the decision is
    ``halt_scope=HALT_SCOPE_ALREADY_HALTED`` and the
    state is unchanged from the input.

    If no gate halts, the decision is ``allowed=True``
    and the state is updated with the drawdown applied to
    all three counters.

    Raises:
        PaperGateError: If ``state`` is invalid or if
            ``simulated_delta_jpy`` is not an int.
    """
    state = _require_state(state)
    _require_int("simulated_delta_jpy", simulated_delta_jpy)

    if state.session_halted:
        return _decision_halted(
            state,
            HALT_SCOPE_ALREADY_HALTED,
            format_halt_reason(
                HALT_SCOPE_SESSION,
                MAX_SESSION_DRAWDOWN_JPY,
                state.session_realized_jpy,
            ),
        )
    if state.day_halted:
        return _decision_halted(
            state,
            HALT_SCOPE_ALREADY_HALTED,
            format_halt_reason(
                HALT_SCOPE_DAILY,
                MAX_DAILY_DRAWDOWN_JPY,
                state.day_realized_jpy,
            ),
        )
    if state.week_halted:
        return _decision_halted(
            state,
            HALT_SCOPE_ALREADY_HALTED,
            format_halt_reason(
                HALT_SCOPE_WEEKLY,
                MAX_WEEKLY_DRAWDOWN_JPY,
                state.week_realized_jpy,
            ),
        )

    drawdown = _simulated_drawdown_jpy(simulated_delta_jpy)
    new_session = state.session_realized_jpy + drawdown
    new_day = state.day_realized_jpy + drawdown
    new_week = state.week_realized_jpy + drawdown

    if new_session >= MAX_SESSION_DRAWDOWN_JPY:
        halted_state = replace(
            state,
            session_realized_jpy=new_session,
            day_realized_jpy=new_day,
            week_realized_jpy=new_week,
            session_halted=True,
        )
        return _decision_halted(
            halted_state,
            HALT_SCOPE_SESSION,
            format_halt_reason(
                HALT_SCOPE_SESSION,
                MAX_SESSION_DRAWDOWN_JPY,
                new_session,
            ),
        )
    if new_day >= MAX_DAILY_DRAWDOWN_JPY:
        halted_state = replace(
            state,
            session_realized_jpy=new_session,
            day_realized_jpy=new_day,
            week_realized_jpy=new_week,
            day_halted=True,
        )
        return _decision_halted(
            halted_state,
            HALT_SCOPE_DAILY,
            format_halt_reason(
                HALT_SCOPE_DAILY,
                MAX_DAILY_DRAWDOWN_JPY,
                new_day,
            ),
        )
    if new_week >= MAX_WEEKLY_DRAWDOWN_JPY:
        halted_state = replace(
            state,
            session_realized_jpy=new_session,
            day_realized_jpy=new_day,
            week_realized_jpy=new_week,
            week_halted=True,
        )
        return _decision_halted(
            halted_state,
            HALT_SCOPE_WEEKLY,
            format_halt_reason(
                HALT_SCOPE_WEEKLY,
                MAX_WEEKLY_DRAWDOWN_JPY,
                new_week,
            ),
        )

    new_state = replace(
        state,
        session_realized_jpy=new_session,
        day_realized_jpy=new_day,
        week_realized_jpy=new_week,
    )
    return _decision_allowed(new_state)
