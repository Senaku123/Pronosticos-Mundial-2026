"""Load the frozen engine and run LIGHT per-match math (single calibrated matrix).

The official pre-tournament run ``wc2026`` persists the engine configuration (Dixon-Coles rho +
Platt calibrator) that won the Phase 8 go/no-go. The API reads and reuses it verbatim — it never
refits (a refit is heavy and would silently diverge from the published forecast). A single
calibrated scoreline matrix per request is cheap and is the single source of truth for W/D/L.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from wc26.database.models import TournamentSimulation
from wc26.models.baselines import elo_to_lambdas, most_likely_score, wdl_from_matrix
from wc26.models.calibration import PlattCalibrator, calibrate_matrix
from wc26.models.dixon_coles import DixonColesConfig, dixon_coles_matrix
from wc26.models.engine_config import engine_from_config_json

OFFICIAL_RUN_ID = "wc2026"


@dataclass(frozen=True)
class FrozenEngine:
    """The frozen, calibrated engine plus the provenance of the run it came from."""

    config: DixonColesConfig
    calibrator: PlattCalibrator
    run_id: str
    cutoff_date: dt.date | None


@lru_cache(maxsize=8)
def _parse(config_json: str) -> tuple[DixonColesConfig, PlattCalibrator]:
    """Parse (and memoize) a run's engine configuration from its JSON."""
    return engine_from_config_json(config_json)


def load_official_engine(session: Session, run_id: str = OFFICIAL_RUN_ID) -> FrozenEngine:
    """Read the frozen engine from a persisted tournament simulation run.

    Raises 503 if the run is absent: the API must not refit the engine synchronously (heavy);
    the configuration is produced and persisted by the simulation scripts.
    """
    row = session.execute(
        select(TournamentSimulation.config_json, TournamentSimulation.cutoff_date).where(
            TournamentSimulation.run_id == run_id
        )
    ).one_or_none()
    if row is None or row.config_json is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"engine configuration unavailable: simulation run '{run_id}' is not persisted. "
                "Run scripts/run_2026_simulation.py (or the Phase 10 simulator) first."
            ),
        )
    config, calibrator = _parse(row.config_json)
    return FrozenEngine(config, calibrator, run_id, row.cutoff_date)


@dataclass(frozen=True)
class MatchForecast:
    """A single match's calibrated forecast (the single source of truth is ``matrix``)."""

    p_home_win: float
    p_draw: float
    p_away_win: float
    expected_goals_home: float
    expected_goals_away: float
    most_likely_home: int
    most_likely_away: int
    matrix: list[list[float]]


def forecast_match(
    elo_home: float, elo_away: float, neutral: bool, engine: FrozenEngine
) -> MatchForecast:
    """Calibrated Dixon-Coles forecast for one match. W/D/L is summed from the matrix zones."""
    lh, la = elo_to_lambdas(elo_home, elo_away, neutral, engine.config.base)
    raw = dixon_coles_matrix(lh, la, engine.config.rho, engine.config.base.max_goals)
    matrix = calibrate_matrix(raw, engine.calibrator)
    p_home, p_draw, p_away = wdl_from_matrix(matrix)
    home_goals, away_goals = most_likely_score(matrix)
    exp_home = sum(i * sum(row) for i, row in enumerate(matrix))
    exp_away = sum(j * matrix[i][j] for i in range(len(matrix)) for j in range(len(matrix[i])))
    return MatchForecast(
        p_home_win=p_home,
        p_draw=p_draw,
        p_away_win=p_away,
        expected_goals_home=exp_home,
        expected_goals_away=exp_away,
        most_likely_home=home_goals,
        most_likely_away=away_goals,
        matrix=matrix,
    )


def top_scorelines(matrix: list[list[float]], limit: int = 5) -> list[tuple[int, int, float]]:
    """The ``limit`` most probable (home_goals, away_goals, probability) cells, descending."""
    cells = [(i, j, value) for i, row in enumerate(matrix) for j, value in enumerate(row)]
    cells.sort(key=lambda c: c[2], reverse=True)
    return cells[:limit]
