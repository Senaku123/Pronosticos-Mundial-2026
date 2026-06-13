"""Per-match endpoints: W/D/L forecast and the full scoreline probability matrix.

These run LIGHT math (one calibrated Dixon-Coles matrix) — allowed inside a request. W/D/L is
always summed from the matrix zones (single source of truth, addendum §2).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from wc26.database.models import Team
from wc26.features.cutoff import get_rating_as_of
from wc26_api.deps import get_session
from wc26_api.engine import FrozenEngine, forecast_match, load_official_engine, top_scorelines
from wc26_api.schemas import (
    EngineInfo,
    PredictMatchRequest,
    PredictMatchResponse,
    Scoreline,
    ScorelineMatrixResponse,
)

router = APIRouter(tags=["predictions"])


def _team_id(session: Session, name: str) -> int:
    team_id = session.execute(
        select(Team.id).where(Team.canonical_name == name)
    ).scalar_one_or_none()
    if team_id is None:
        raise HTTPException(status_code=404, detail=f"team '{name}' not found (use canonical_name)")
    return team_id


def _engine_info(engine: FrozenEngine) -> EngineInfo:
    return EngineInfo(run_id=engine.run_id, rho=engine.config.rho, cutoff_date=engine.cutoff_date)


def _resolve_as_of(requested: dt.date | None, engine: FrozenEngine) -> dt.date:
    return requested or engine.cutoff_date or dt.date.today()


@router.post("/predict-match", response_model=PredictMatchResponse)
def predict_match(
    body: PredictMatchRequest, session: Session = Depends(get_session)
) -> PredictMatchResponse:
    """Calibrated W/D/L, expected goals and most-likely scorelines for a single match."""
    engine = load_official_engine(session)
    as_of = _resolve_as_of(body.as_of, engine)
    elo_home = get_rating_as_of(session, _team_id(session, body.home_team), as_of)
    elo_away = get_rating_as_of(session, _team_id(session, body.away_team), as_of)

    fc = forecast_match(elo_home, elo_away, body.neutral, engine)
    return PredictMatchResponse(
        home_team=body.home_team,
        away_team=body.away_team,
        neutral=body.neutral,
        as_of=as_of,
        elo_home=elo_home,
        elo_away=elo_away,
        p_home_win=fc.p_home_win,
        p_draw=fc.p_draw,
        p_away_win=fc.p_away_win,
        expected_goals_home=fc.expected_goals_home,
        expected_goals_away=fc.expected_goals_away,
        most_likely_score=Scoreline(
            home_goals=fc.most_likely_home,
            away_goals=fc.most_likely_away,
            probability=fc.matrix[fc.most_likely_home][fc.most_likely_away],
        ),
        top_scorelines=[
            Scoreline(home_goals=h, away_goals=a, probability=p)
            for h, a, p in top_scorelines(fc.matrix, limit=5)
        ],
        engine=_engine_info(engine),
    )


@router.get("/scoreline-matrix", response_model=ScorelineMatrixResponse)
def scoreline_matrix(
    session: Session = Depends(get_session),
    home_team: str = Query(..., description="canonical team name"),
    away_team: str = Query(..., description="canonical team name"),
    neutral: bool = Query(default=True),
    as_of: dt.date | None = Query(default=None),
    max_goals: int = Query(default=6, ge=1, le=10, description="display truncation"),
) -> ScorelineMatrixResponse:
    """Full calibrated scoreline matrix, truncated to ``max_goals`` for display.

    W/D/L marginals are summed from the FULL matrix; ``truncated_mass`` reports the probability
    that falls outside the displayed grid so the truncation is explicit, never hidden.
    """
    engine = load_official_engine(session)
    effective_as_of = _resolve_as_of(as_of, engine)
    elo_home = get_rating_as_of(session, _team_id(session, home_team), effective_as_of)
    elo_away = get_rating_as_of(session, _team_id(session, away_team), effective_as_of)

    fc = forecast_match(elo_home, elo_away, neutral, engine)
    shown = [row[: max_goals + 1] for row in fc.matrix[: max_goals + 1]]
    shown_mass = sum(sum(row) for row in shown)
    return ScorelineMatrixResponse(
        home_team=home_team,
        away_team=away_team,
        neutral=neutral,
        as_of=effective_as_of,
        max_goals=max_goals,
        p_home_win=fc.p_home_win,
        p_draw=fc.p_draw,
        p_away_win=fc.p_away_win,
        matrix=shown,
        truncated_mass=max(0.0, 1.0 - shown_mass),
        engine=_engine_info(engine),
    )
