"""Schema validator for :class:`MarketContext` payloads.

The validator is intentionally strict at MVP:

* All required top-level fields must be present.
* Numeric fields must be ``int`` or ``float`` (not strings, not ``None``).
* ``economic_event_risk.events`` must be a list.
* ``timezone`` must be ``"Asia/Tokyo"`` (the MVP canonical value).
* The schema must not imply live execution, broker integration, or
  account state. The validator enforces this by checking that the
  set of top-level field names is exactly the documented set.

The validator is pure: no I/O, no environment reads, no network.
"""

from __future__ import annotations

from typing import Any, Mapping

from nms.data.models import (
    MVP_TIMEZONE,
    EconomicEventRisk,
    EventItem,
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


#: The set of allowed top-level keys. Anything outside this set is
#: rejected. This is a defense-in-depth check that prevents the
#: schema from silently growing to include account / broker / order
#: fields.
_ALLOWED_TOP_KEYS = frozenset(
    {
        "session_date",
        "timezone",
        "us_equities",
        "semiconductor",
        "fx",
        "us_yields",
        "nikkei_night_session",
        "previous_day",
        "economic_event_risk",
        "intraday_range",
        "volatility_context",
    }
)


class ValidationError(ValueError):
    """Raised when a payload does not match the MarketContext schema."""


def _require(mapping: Mapping[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ValidationError(f"missing required field: {key!r}")
    return mapping[key]


def _is_number(v: Any) -> bool:
    # ``bool`` is a subclass of ``int`` in Python; we reject it
    # explicitly because it is almost always a schema bug.
    if isinstance(v, bool):
        return False
    return isinstance(v, (int, float))


def _require_number(mapping: Mapping[str, Any], key: str) -> float:
    v = _require(mapping, key)
    if not _is_number(v):
        raise ValidationError(
            f"field {key!r} must be a number (int or float), got {type(v).__name__}"
        )
    return float(v)


def _require_str(mapping: Mapping[str, Any], key: str) -> str:
    v = _require(mapping, key)
    if not isinstance(v, str):
        raise ValidationError(
            f"field {key!r} must be a string, got {type(v).__name__}"
        )
    return v


def _require_sub_mapping(
    mapping: Mapping[str, Any], key: str
) -> Mapping[str, Any]:
    v = _require(mapping, key)
    if not isinstance(v, Mapping):
        raise ValidationError(
            f"field {key!r} must be a mapping, got {type(v).__name__}"
        )
    return v


def _build_us_equities(d: Mapping[str, Any]) -> UsEquities:
    return UsEquities(
        sp500=_require_number(d, "sp500"),
        dow=_require_number(d, "dow"),
        nasdaq100=_require_number(d, "nasdaq100"),
        russell2000=_require_number(d, "russell2000"),
    )


def _build_semiconductor(d: Mapping[str, Any]) -> Semiconductor:
    return Semiconductor(sox=_require_number(d, "sox"))


def _build_fx(d: Mapping[str, Any]) -> Fx:
    return Fx(usdjpy=_require_number(d, "usdjpy"))


def _build_us_yields(d: Mapping[str, Any]) -> UsYields:
    return UsYields(
        us2y=_require_number(d, "us2y"),
        us10y=_require_number(d, "us10y"),
        us10y_minus_us2y=_require_number(d, "us10y_minus_us2y"),
    )


def _build_nikkei_night(d: Mapping[str, Any]) -> NikkeiNightSession:
    return NikkeiNightSession(
        close=_require_number(d, "close"),
        high=_require_number(d, "high"),
        low=_require_number(d, "low"),
        range=_require_number(d, "range"),
        percent_change=_require_number(d, "percent_change"),
    )


def _build_previous_day(d: Mapping[str, Any]) -> PreviousDay:
    return PreviousDay(
        high=_require_number(d, "high"),
        low=_require_number(d, "low"),
        close=_require_number(d, "close"),
        range=_require_number(d, "range"),
    )


def _build_economic_event_risk(d: Mapping[str, Any]) -> EconomicEventRisk:
    raw_events = _require(d, "events")
    if not isinstance(raw_events, list):
        raise ValidationError(
            f"field 'events' must be a list, got {type(raw_events).__name__}"
        )
    items: list[EventItem] = []
    for i, ev in enumerate(raw_events):
        if not isinstance(ev, Mapping):
            raise ValidationError(
                f"events[{i}] must be a mapping, got {type(ev).__name__}"
            )
        name = _require_str(ev, "name")
        time_jst = ev.get("time_jst", "")
        impact = ev.get("impact", "")
        if not isinstance(time_jst, str):
            raise ValidationError(
                f"events[{i}].time_jst must be a string, got {type(time_jst).__name__}"
            )
        if not isinstance(impact, str):
            raise ValidationError(
                f"events[{i}].impact must be a string, got {type(impact).__name__}"
            )
        items.append(EventItem(name=name, time_jst=time_jst, impact=impact))
    return EconomicEventRisk(events=items)


def _build_intraday_range(d: Mapping[str, Any]) -> IntradayRange:
    return IntradayRange(
        first_15m_high=_require_number(d, "first_15m_high"),
        first_15m_low=_require_number(d, "first_15m_low"),
        first_15m_range=_require_number(d, "first_15m_range"),
        atr_like_baseline=_require_number(d, "atr_like_baseline"),
    )


def _build_volatility_context(d: Mapping[str, Any]) -> VolatilityContext:
    flag = _require(d, "compression_flag")
    if not isinstance(flag, bool):
        raise ValidationError(
            "field 'compression_flag' must be a boolean, got "
            f"{type(flag).__name__}"
        )
    return VolatilityContext(
        realized_vol=_require_number(d, "realized_vol"),
        atr_like=_require_number(d, "atr_like"),
        compression_flag=flag,
    )


def validate_market_context(data: Mapping[str, Any]) -> MarketContext:
    """Validate a parsed payload and return a :class:`MarketContext`.

    Raises :class:`ValidationError` for any structural problem.
    """
    if not isinstance(data, Mapping):
        raise ValidationError(
            f"top-level value must be a mapping, got {type(data).__name__}"
        )

    extra = set(data.keys()) - _ALLOWED_TOP_KEYS
    if extra:
        raise ValidationError(
            "unexpected top-level fields: "
            + ", ".join(sorted(repr(k) for k in extra))
        )

    session_date = _require_str(data, "session_date")
    timezone = _require_str(data, "timezone")
    if timezone != MVP_TIMEZONE:
        raise ValidationError(
            f"field 'timezone' must be {MVP_TIMEZONE!r} for MVP, got {timezone!r}"
        )

    return MarketContext(
        session_date=session_date,
        timezone=timezone,
        us_equities=_build_us_equities(_require_sub_mapping(data, "us_equities")),
        semiconductor=_build_semiconductor(
            _require_sub_mapping(data, "semiconductor")
        ),
        fx=_build_fx(_require_sub_mapping(data, "fx")),
        us_yields=_build_us_yields(_require_sub_mapping(data, "us_yields")),
        nikkei_night_session=_build_nikkei_night(
            _require_sub_mapping(data, "nikkei_night_session")
        ),
        previous_day=_build_previous_day(
            _require_sub_mapping(data, "previous_day")
        ),
        economic_event_risk=_build_economic_event_risk(
            _require_sub_mapping(data, "economic_event_risk")
        ),
        intraday_range=_build_intraday_range(
            _require_sub_mapping(data, "intraday_range")
        ),
        volatility_context=_build_volatility_context(
            _require_sub_mapping(data, "volatility_context")
        ),
    )
