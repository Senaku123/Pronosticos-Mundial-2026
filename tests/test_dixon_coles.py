"""Tests for the Dixon-Coles scoreline model (Phase 7), incl. the single-source-of-truth rule."""

from __future__ import annotations

from wc26.models.baselines import wdl_from_matrix
from wc26.models.dixon_coles import (
    DixonColesConfig,
    dixon_coles_matrix,
    fit_rho,
    predict_dixon_coles,
)


def test_matrix_sums_to_one() -> None:
    matrix = dixon_coles_matrix(1.6, 1.1, -0.1, max_goals=10)
    assert abs(sum(sum(row) for row in matrix) - 1.0) < 1e-9


def test_wdl_single_source() -> None:
    """W/D/L must be exactly the zone-sum of the scoreline matrix (addendum §2)."""
    pred, matrix = predict_dixon_coles(1800.0, 1500.0, neutral=False)
    p_home, p_draw, p_away = wdl_from_matrix(matrix)
    assert abs(pred.p_home_win - p_home) < 1e-12
    assert abs(pred.p_draw - p_draw) < 1e-12
    assert abs(pred.p_away_win - p_away) < 1e-12
    assert abs(pred.p_home_win + pred.p_draw + pred.p_away_win - 1.0) < 1e-9


def test_negative_rho_lifts_draws() -> None:
    dc, _ = predict_dixon_coles(1500.0, 1500.0, neutral=True, config=DixonColesConfig(rho=-0.12))
    indep, _ = predict_dixon_coles(1500.0, 1500.0, neutral=True, config=DixonColesConfig(rho=0.0))
    assert dc.p_draw > indep.p_draw


def test_fit_rho_detects_excess_draws() -> None:
    # A sample dominated by 1-1 draws implies positive low-score dependence -> negative rho.
    samples = [(1.3, 1.1, 1, 1)] * 200 + [(1.3, 1.1, 0, 0)] * 50
    rho = fit_rho(samples)
    assert -0.3 <= rho < 0.0


def test_wdl_single_source_in_db(db_session) -> None:
    """DB-level: stored W/D/L equals the summed zones of the stored scoreline matrix.

    Skipped automatically when no database / no Dixon-Coles predictions are available.
    """
    import pytest
    from sqlalchemy import func, select

    from wc26.database.models import MatchPrediction, ModelRun, ScorelineProbability

    run = db_session.execute(
        select(ModelRun.id).where(ModelRun.run_id == "dixon_coles_wc2026")
    ).scalar_one_or_none()
    if run is None:
        pytest.skip("dixon_coles_wc2026 run not present")

    match_id = db_session.execute(
        select(ScorelineProbability.match_id)
        .where(ScorelineProbability.model_run_id == run)
        .limit(1)
    ).scalar_one()

    p_home = db_session.execute(
        select(func.sum(ScorelineProbability.probability)).where(
            ScorelineProbability.model_run_id == run,
            ScorelineProbability.match_id == match_id,
            ScorelineProbability.home_goals > ScorelineProbability.away_goals,
        )
    ).scalar_one()
    stored = db_session.execute(
        select(MatchPrediction.p_home_win).where(
            MatchPrediction.model_run_id == run, MatchPrediction.match_id == match_id
        )
    ).scalar_one()
    assert abs(float(p_home) - float(stored)) < 1e-9
