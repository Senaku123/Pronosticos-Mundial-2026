"""Persistence helpers for model runs and their match predictions (Phase 6)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from wc26.database.models import MatchPrediction, ModelRun


def reset_model_run(
    session: Session,
    run_id: str,
    model_name: str,
    model_version: str = "v1",
    git_sha: str | None = None,
    python_version: str | None = None,
    cutoff_date: dt.date | None = None,
    config_json: str | None = None,
) -> int:
    """Create (or clear) a model run by ``run_id`` and return its id (idempotent re-runs)."""
    existing = session.execute(
        select(ModelRun).where(ModelRun.run_id == run_id)
    ).scalar_one_or_none()
    if existing is not None:
        session.execute(delete(MatchPrediction).where(MatchPrediction.model_run_id == existing.id))
        session.flush()
        return existing.id
    run = ModelRun(
        run_id=run_id,
        model_name=model_name,
        model_version=model_version,
        git_sha=git_sha,
        python_version=python_version,
        cutoff_date=cutoff_date,
        config_json=config_json,
    )
    session.add(run)
    session.flush()
    return run.id


def store_predictions(session: Session, rows: list[dict[str, object]]) -> int:
    """Bulk-insert prediction rows. Returns the count."""
    if rows:
        session.execute(insert(MatchPrediction), rows)
    session.flush()
    return len(rows)
