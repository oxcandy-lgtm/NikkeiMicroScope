"""NikkeiMicroScope (NMS) - market regime observation package.

This package is observation-only. It MUST NOT place orders, connect to
broker / exchange APIs, hold credentials, or make financial-advice
claims. See:

* ``AGENTS.md`` at the repository root for binding rules.
* ``docs/risk-policy.md`` for hard risk gates.
* ``docs/data-adapter-contract.md`` for the data adapter contract.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
