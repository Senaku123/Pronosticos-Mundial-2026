"""Phase 13 — thin FastAPI transport layer over the forecast engine.

This package depends on ``wc26`` (``src/``) and NEVER the other way around (blueprint §9). It
exposes precomputed aggregates (teams, tournament probabilities, backtests, model runs) and runs
only LIGHT per-match math (a single calibrated Dixon-Coles matrix) inside a request. Heavy Monte
Carlo simulations are precomputed by scripts and persisted; the API just reads them.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
