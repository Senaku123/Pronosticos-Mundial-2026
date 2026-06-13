"""Backtest and model-run endpoints — read evaluation aggregates and run provenance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wc26.database.models import (
    BacktestMetric,
    BacktestRun,
    MatchPrediction,
    ModelRun,
)
from wc26_api.deps import get_session
from wc26_api.schemas import (
    BacktestMetricValue,
    BacktestResultsResponse,
    BacktestRunResult,
    ModelRunResponse,
)

router = APIRouter(tags=["evaluation"])


@router.get("/backtest-results", response_model=BacktestResultsResponse)
def backtest_results(
    session: Session = Depends(get_session),
    level: str | None = Query(
        default=None, description="filter by level: match | tournament | live"
    ),
    run_id: str | None = Query(default=None, description="filter by a specific backtest run_id"),
    limit: int = Query(default=50, ge=1, le=500),
) -> BacktestResultsResponse:
    """List backtest runs (most recent first) with their metrics in long format."""
    stmt = select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit)
    if level is not None:
        stmt = stmt.where(BacktestRun.backtest_level == level)
    if run_id is not None:
        stmt = stmt.where(BacktestRun.run_id == run_id)
    runs = session.execute(stmt).scalars().all()

    metric_rows = session.execute(
        select(
            BacktestMetric.backtest_run_id,
            BacktestMetric.model_name,
            BacktestMetric.metric,
            BacktestMetric.value,
        ).where(BacktestMetric.backtest_run_id.in_([r.id for r in runs]))
    ).all()
    metrics_by_run: dict[int, list[BacktestMetricValue]] = {}
    for backtest_run_id, model_name, metric, value in metric_rows:
        metrics_by_run.setdefault(backtest_run_id, []).append(
            BacktestMetricValue(model_name=model_name, metric=metric, value=value)
        )

    results = [
        BacktestRunResult(
            run_id=r.run_id,
            backtest_level=r.backtest_level,
            test_from=r.test_from,
            n_matches=r.n_matches,
            git_sha=r.git_sha,
            created_at=r.created_at,
            metrics=metrics_by_run.get(r.id, []),
        )
        for r in runs
    ]
    return BacktestResultsResponse(count=len(results), runs=results)


@router.get("/model-runs/{run_id}", response_model=ModelRunResponse)
def model_run(run_id: str, session: Session = Depends(get_session)) -> ModelRunResponse:
    """Reproducibility metadata for one model run, plus how many predictions it holds."""
    run = session.execute(select(ModelRun).where(ModelRun.run_id == run_id)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"model run '{run_id}' not found")
    n_predictions = session.execute(
        select(func.count())
        .select_from(MatchPrediction)
        .where(MatchPrediction.model_run_id == run.id)
    ).scalar_one()
    return ModelRunResponse(
        run_id=run.run_id,
        model_name=run.model_name,
        model_version=run.model_version,
        git_sha=run.git_sha,
        data_hash=run.data_hash,
        cutoff_date=run.cutoff_date,
        random_seed=run.random_seed,
        python_version=run.python_version,
        config_json=run.config_json,
        created_at=run.created_at,
        n_predictions=n_predictions,
    )
