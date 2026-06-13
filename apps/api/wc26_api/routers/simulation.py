"""Tournament-level endpoints — all READ-ONLY over precomputed Monte Carlo aggregates.

The API never runs a 50k simulation inside a request (blueprint §9: no heavy sync compute).
``/run-tournament-simulation`` reads a persisted run; the heavy work is done by
``scripts/run_2026_simulation.py`` and stored in ``tournament_simulations``/``simulation_results``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from wc26.database.models import SimulationResult, Team, TournamentSimulation
from wc26_api.deps import get_session
from wc26_api.schemas import (
    RunTournamentSimulationRequest,
    RunTournamentSimulationResponse,
    SimulationRunListResponse,
    SimulationRunMeta,
    StageProbability,
    TournamentProbabilitiesResponse,
)

router = APIRouter(tags=["simulation"])

_STAGE_FIELDS = (
    "round_of_32",
    "round_of_16",
    "quarterfinal",
    "semifinal",
    "final",
    "champion",
)


def _run_meta(sim: TournamentSimulation) -> SimulationRunMeta:
    return SimulationRunMeta(
        run_id=sim.run_id,
        n_simulations=sim.n_simulations,
        random_seed=sim.random_seed,
        cutoff_date=sim.cutoff_date,
        git_sha=sim.git_sha,
        python_version=sim.python_version,
        created_at=sim.created_at,
    )


def _load_run(session: Session, run_id: str) -> TournamentSimulation:
    sim = session.execute(
        select(TournamentSimulation).where(TournamentSimulation.run_id == run_id)
    ).scalar_one_or_none()
    if sim is None:
        available = (
            session.execute(
                select(TournamentSimulation.run_id).order_by(TournamentSimulation.created_at.desc())
            )
            .scalars()
            .all()
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"simulation run '{run_id}' not found. Available: {available}. "
                "Heavy simulations are precomputed by scripts/run_2026_simulation.py."
            ),
        )
    return sim


def _stage_rows(session: Session, sim_id: int) -> list[StageProbability]:
    rows = session.execute(
        select(Team.canonical_name, SimulationResult.stage, SimulationResult.probability)
        .join(Team, Team.id == SimulationResult.team_id)
        .where(SimulationResult.tournament_simulation_id == sim_id)
    ).all()
    by_team: dict[str, dict[str, float]] = {}
    for name, stage, prob in rows:
        by_team.setdefault(name, {})[stage] = prob
    return [
        StageProbability(team=name, **{f: stages.get(f) for f in _STAGE_FIELDS})
        for name, stages in by_team.items()
    ]


@router.get("/tournament-simulations", response_model=SimulationRunListResponse)
def list_simulations(session: Session = Depends(get_session)) -> SimulationRunListResponse:
    """List persisted simulation runs (most recent first)."""
    sims = (
        session.execute(
            select(TournamentSimulation).order_by(TournamentSimulation.created_at.desc())
        )
        .scalars()
        .all()
    )
    return SimulationRunListResponse(count=len(sims), runs=[_run_meta(s) for s in sims])


@router.get("/tournament-probabilities", response_model=TournamentProbabilitiesResponse)
def tournament_probabilities(
    session: Session = Depends(get_session),
    run_id: str = Query(default="wc2026", description="persisted simulation run"),
    stage: str = Query(default="champion", description="stage to rank by"),
    limit: int = Query(default=24, ge=1, le=48),
) -> TournamentProbabilitiesResponse:
    """Per-team stage probabilities for a run, ranked by ``stage`` (default: champion)."""
    if stage not in _STAGE_FIELDS:
        raise HTTPException(status_code=422, detail=f"stage must be one of {list(_STAGE_FIELDS)}")
    sim = _load_run(session, run_id)
    standings = _stage_rows(session, sim.id)
    standings.sort(key=lambda s: getattr(s, stage) or 0.0, reverse=True)
    return TournamentProbabilitiesResponse(
        run=_run_meta(sim), stage=stage, count=len(standings), standings=standings[:limit]
    )


@router.post("/run-tournament-simulation", response_model=RunTournamentSimulationResponse)
def run_tournament_simulation(
    body: RunTournamentSimulationRequest, session: Session = Depends(get_session)
) -> RunTournamentSimulationResponse:
    """Return a persisted simulation's full stage matrix (READ-ONLY; no synchronous compute)."""
    sim = _load_run(session, body.run_id)
    results = _stage_rows(session, sim.id)
    results.sort(key=lambda s: s.champion or 0.0, reverse=True)
    return RunTournamentSimulationResponse(
        run=_run_meta(sim),
        note=(
            "Read-only: heavy Monte Carlo is precomputed by scripts/run_2026_simulation.py and "
            "persisted; the API never simulates synchronously (blueprint §9)."
        ),
        count=len(results),
        results=results,
    )
