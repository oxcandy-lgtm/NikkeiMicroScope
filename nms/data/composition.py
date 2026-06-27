"""Adapter composition for NikkeiMicroScope.

This module provides a small, deterministic composition layer for
already-approved :class:`MarketContextAdapter` instances. It does
**not** introduce a new market data source and does **not** perform
network I/O itself. It is a pure orchestration layer: it wires a
base adapter and a sequence of named overlay stages into one final
validated :class:`MarketContext`.

Hard constraints (enforced socially and via unit tests):

* No new market data source. Only already-approved adapters may be
  composed.
* No SOX adapter. Per
  ``docs/sox-source-selection.md`` and §8.5 of
  ``docs/data-adapter-contract.md``, no SOX / semiconductor adapter
  is approved yet, so a SOX stage must not be added here.
* No network I/O performed by this module. The composition layer
  only calls ``load()`` on already-constructed adapters. Any
  network access must be implemented inside the composed
  adapters themselves (and that is also constrained to no live
  network in tests and dry-runs).
* No subprocess, no environment-variable credential reading, no
  ``.env``, no auth / cookie / paid source.
* The final composed context is re-validated through
  :func:`nms.data.validate.validate_market_context`.

This module does not add a default live production pipeline. A
future PR may add an operator-run CLI with an explicit
``--live-network-ok`` flag, but not this one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Protocol, Sequence, Tuple

from nms.data.adapters import MarketContextAdapter
from nms.data.models import MarketContext
from nms.data.validate import validate_market_context


class AdapterCompositionError(RuntimeError):
    """Raised when an adapter composition stage fails to construct
    or to load.

    The original exception is preserved as ``__cause__`` for
    debugging. The error message includes the stage name (when
    known) and the session date (when known) so failures can be
    traced back to a specific stage of the composition.
    """


@dataclass(frozen=True)
class AdapterStage:
    """A named factory that takes a baseline adapter and returns a
    new adapter to be used as the next baseline.

    The factory itself must be pure: it must not perform network
    I/O, must not read environment credentials, and must not
    subprocess out. Network I/O happens lazily inside the
    constructed adapter's ``load()`` call. The factory is allowed
    to capture bound arguments such as an injected ``http_get``
    callable for tests and dry-runs.

    Attributes:
        name: Human-readable name for error reporting and
            debugging (e.g. ``"treasury"``, ``"sp500"``,
            ``"usdjpy"``, ``"nasdaq100"``).
        factory: A callable that accepts a
            :class:`MarketContextAdapter` and returns a new
            :class:`MarketContextAdapter` that uses the input as
            its baseline.
    """

    name: str
    factory: Callable[[MarketContextAdapter], MarketContextAdapter]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(
                "AdapterStage.name must be a non-empty string; "
                f"got {self.name!r}"
            )
        if not callable(self.factory):
            raise TypeError(
                "AdapterStage.factory must be callable; "
                f"got {type(self.factory).__name__}"
            )


class ComposedMarketContextAdapter:
    """A :class:`MarketContextAdapter` that runs a base adapter and
    then a sequence of named overlay stages, in order.

    Composition semantics:

    1. The base adapter is used to load the initial
       :class:`MarketContext`.
    2. For each stage, the stage's factory is called with the
       previous adapter as the new baseline, and the new adapter
       becomes the baseline for the next stage.
    3. The final adapter is called with ``load(session_date)`` to
       produce the final :class:`MarketContext`.
    4. The final context is re-validated through
       :func:`nms.data.validate.validate_market_context`.

    Construction-stage and load-stage failures are wrapped in
    :class:`AdapterCompositionError` with stage-name and
    session-date metadata, while preserving the original
    exception as ``__cause__``.

    The composition layer is intentionally minimal: it does not
    introspect overlay internals, does not call ``load()`` between
    stages (the existing overlay adapters take their base in the
    constructor and load it lazily on ``load()``), and does not
    introduce live network access.
    """

    def __init__(
        self,
        base_adapter: MarketContextAdapter,
        stages: Sequence[AdapterStage] = (),
    ) -> None:
        self._base_adapter = base_adapter
        # Normalize to a tuple so .stages returns an immutable
        # view, and so a single AdapterStage accidentally passed
        # in also works.
        self._stages: Tuple[AdapterStage, ...] = tuple(stages)

    @property
    def stages(self) -> Tuple[AdapterStage, ...]:
        """Return the composed stages as an immutable tuple."""
        return self._stages

    @property
    def base_adapter(self) -> MarketContextAdapter:
        """Return the base adapter passed at construction time."""
        return self._base_adapter

    def _build_chain(
        self,
    ) -> MarketContextAdapter:
        """Build the adapter chain by applying the stage factories
        in order on top of the base adapter.

        Construction failures are wrapped in
        :class:`AdapterCompositionError` with the failing
        stage's name.
        """
        current: MarketContextAdapter = self._base_adapter
        for stage in self._stages:
            try:
                current = stage.factory(current)
            except Exception as exc:
                raise AdapterCompositionError(
                    f"failed to construct adapter stage "
                    f"{stage.name!r}: {exc}"
                ) from exc
        return current

    def load(self, session_date: str) -> MarketContext:
        """Load a :class:`MarketContext` for ``session_date`` by
        applying the stage chain on top of the base adapter and
        re-validating the result.

        Args:
            session_date: An ISO-8601 calendar date string (e.g.
                ``"2026-06-24"``).

        Returns:
            A new frozen, fully validated
            :class:`MarketContext` produced by the chain.

        Raises:
            AdapterCompositionError: If any stage factory raises
                during construction, or if the final
                ``load(session_date)`` call raises. The original
                exception is preserved as ``__cause__``.
        """
        chain = self._build_chain()
        try:
            ctx = chain.load(session_date)
        except Exception as exc:
            raise AdapterCompositionError(
                f"failed to load composed market context for "
                f"session_date {session_date!r}: {exc}"
            ) from exc
        # Re-validate the final composed context to enforce
        # schema and nested strictness.
        return validate_market_context(asdict(ctx))


def compose_market_context_adapter(
    base_adapter: MarketContextAdapter,
    stages: Sequence[AdapterStage],
) -> ComposedMarketContextAdapter:
    """Convenience helper that returns a
    :class:`ComposedMarketContextAdapter` for the given base
    adapter and stages.

    The helper exists so callers can write::

        adapter = compose_market_context_adapter(
            base,
            [
                AdapterStage("treasury", lambda b: FredTreasuryOverlayAdapter(b, http_get=...)),
                AdapterStage("sp500", lambda b: FredSP500OverlayAdapter(b, http_get=...)),
                ...
            ],
        )

    and read the result as a single
    :class:`MarketContextAdapter`.
    """
    return ComposedMarketContextAdapter(base_adapter, stages)
