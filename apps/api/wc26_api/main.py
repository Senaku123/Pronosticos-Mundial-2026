"""FastAPI application factory for the World Cup 2026 forecast engine (Phase 13).

A thin transport layer: it reads precomputed aggregates and runs only light per-match math.
Run locally with: ``uv run --group api uvicorn wc26_api.main:app --reload`` (needs a live DB).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from wc26.database.models import TournamentSimulation
from wc26.utils.provenance import git_sha
from wc26_api import __version__
from wc26_api.deps import get_session
from wc26_api.engine import OFFICIAL_RUN_ID
from wc26_api.routers import backtest, predict, simulation, teams
from wc26_api.schemas import HealthResponse


def create_app() -> FastAPI:
    """Build the FastAPI app with all routers registered."""
    app = FastAPI(
        title="World Cup 2026 Forecast Engine API",
        version=__version__,
        description=(
            "Thin read layer over the calibrated Dixon-Coles engine and its precomputed Monte "
            "Carlo aggregates. Every probability is calibrated (Platt, Phase 8 go/no-go)."
        ),
    )

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    def health(session: Session = Depends(get_session)) -> HealthResponse:
        """Liveness + DB connectivity + whether the frozen engine run is available."""
        try:
            session.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as exc:  # pragma: no cover - exercised only when the DB is down
            return HealthResponse(status="degraded", database=f"error: {exc}", git_sha=git_sha())
        official = session.execute(
            select(TournamentSimulation.run_id).where(
                TournamentSimulation.run_id == OFFICIAL_RUN_ID
            )
        ).scalar_one_or_none()
        return HealthResponse(
            status="ok", database=db_status, git_sha=git_sha(), official_run=official
        )

    app.include_router(teams.router)
    app.include_router(predict.router)
    app.include_router(simulation.router)
    app.include_router(backtest.router)
    return app


app = create_app()
