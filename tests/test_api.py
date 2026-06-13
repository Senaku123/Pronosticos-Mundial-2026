"""Phase 13 API tests — hermetic (in-memory SQLite), no PostgreSQL required.

A seeded SQLite database is injected via FastAPI's dependency override, so every endpoint is
exercised end-to-end in CI without a live database. Includes the W/D/L single-source-of-truth
check (addendum §2) and a guard that ``src/`` never imports the API package (blueprint §9).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from wc26.database.base import Base
from wc26.database.models import (
    BacktestMetric,
    BacktestRun,
    Confederation,
    EloRating,
    MatchPrediction,
    ModelRun,
    SimulationResult,
    Team,
    TournamentSimulation,
)
from wc26.models.calibration import PlattCalibrator
from wc26.models.dixon_coles import DixonColesConfig
from wc26.models.engine_config import engine_config_json
from wc26_api.deps import get_session
from wc26_api.main import create_app

CUTOFF = dt.date(2026, 6, 11)
_STAGES = ["round_of_32", "round_of_16", "quarterfinal", "semifinal", "final", "champion"]


def _seed(session: Session) -> None:
    session.add(Confederation(id=1, code="UEFA", name="UEFA"))
    session.add(Team(id=1, canonical_name="Spain", fifa_code="ESP", confederation_id=1))
    session.add(Team(id=2, canonical_name="France", fifa_code="FRA", confederation_id=1))
    # Distinct as-of strengths (rating_post of the latest match strictly before the cutoff).
    session.add(
        EloRating(
            team_id=1,
            match_id=1,
            match_date=dt.date(2026, 1, 1),
            rating_pre=2110.0,
            rating_post=2130.0,
            is_home=True,
        )
    )
    session.add(
        EloRating(
            team_id=2,
            match_id=1,
            match_date=dt.date(2026, 1, 1),
            rating_pre=2050.0,
            rating_post=2060.0,
            is_home=False,
        )
    )

    config = DixonColesConfig(rho=-0.037)
    calibrator = PlattCalibrator(1.0, 0.0, 1.0, 0.0, 1.0, 0.0)
    sim = TournamentSimulation(
        id=1,
        run_id="wc2026",
        n_simulations=100,
        random_seed=20260611,
        cutoff_date=CUTOFF,
        git_sha="deadbeef",
        python_version="3.11.0",
        config_json=engine_config_json(config, calibrator),
        created_at=dt.datetime(2026, 6, 12, 15, 0, 0),
    )
    session.add(sim)
    champ = {"Spain": 0.20, "France": 0.12}
    for team_id, name in ((1, "Spain"), (2, "France")):
        for stage in _STAGES:
            prob = champ[name] if stage == "champion" else 0.9 - 0.1 * _STAGES.index(stage)
            session.add(
                SimulationResult(
                    tournament_simulation_id=1, team_id=team_id, stage=stage, probability=prob
                )
            )

    run = ModelRun(
        id=1,
        run_id="dixon_coles_calibrated",
        model_name="dixon_coles",
        model_version="v1",
        git_sha="deadbeef",
        cutoff_date=CUTOFF,
        created_at=dt.datetime(2026, 6, 11, 0, 0, 0),
    )
    session.add(run)
    session.add(
        MatchPrediction(model_run_id=1, match_id=1, p_home_win=0.5, p_draw=0.27, p_away_win=0.23)
    )

    bt = BacktestRun(
        id=1,
        run_id="match_level_v1",
        backtest_level="match",
        test_from=dt.date(2018, 1, 1),
        n_matches=8107,
        git_sha="deadbeef",
        created_at=dt.datetime(2026, 6, 11, 0, 0, 0),
    )
    session.add(bt)
    session.add(
        BacktestMetric(
            backtest_run_id=1, model_name="dixon_coles_calibrated", metric="log_loss", value=0.873
        )
    )
    session.add(
        BacktestMetric(backtest_run_id=1, model_name="elo_only", metric="log_loss", value=0.895)
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        _seed(session)
        session.commit()

    app = create_app()

    def _override() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["official_run"] == "wc2026"


def test_list_teams(client: TestClient) -> None:
    r = client.get("/teams")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    names = [t["canonical_name"] for t in body["teams"]]
    assert names == ["France", "Spain"]  # alphabetical
    assert all(t["elo"] is None for t in body["teams"])  # no elo unless requested


def test_list_teams_with_elo(client: TestClient) -> None:
    r = client.get("/teams", params={"with_elo": True, "as_of": "2026-06-11"})
    assert r.status_code == 200
    spain = next(t for t in r.json()["teams"] if t["canonical_name"] == "Spain")
    assert spain["elo"] == pytest.approx(2130.0)


def test_get_team_and_404(client: TestClient) -> None:
    r = client.get("/teams/1", params={"as_of": "2026-06-11"})
    assert r.status_code == 200
    assert r.json()["canonical_name"] == "Spain"
    assert client.get("/teams/999").status_code == 404


def test_predict_match_wdl_sums_to_one(client: TestClient) -> None:
    r = client.post(
        "/predict-match",
        json={"home_team": "Spain", "away_team": "France", "neutral": True},
    )
    assert r.status_code == 200
    body = r.json()
    total = body["p_home_win"] + body["p_draw"] + body["p_away_win"]
    assert total == pytest.approx(1.0, abs=1e-9)  # single source of truth (addendum §2)
    assert body["p_home_win"] > body["p_away_win"]  # Spain stronger
    assert body["as_of"] == "2026-06-11"  # defaults to the official run's cutoff
    assert body["engine"]["run_id"] == "wc2026"
    assert len(body["top_scorelines"]) == 5


def test_predict_match_unknown_team(client: TestClient) -> None:
    r = client.post("/predict-match", json={"home_team": "Atlantis", "away_team": "France"})
    assert r.status_code == 404


def test_scoreline_matrix(client: TestClient) -> None:
    r = client.get(
        "/scoreline-matrix",
        params={"home_team": "Spain", "away_team": "France", "max_goals": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["matrix"]) == 6  # 0..5
    assert all(len(row) == 6 for row in body["matrix"])
    assert body["p_home_win"] + body["p_draw"] + body["p_away_win"] == pytest.approx(1.0, abs=1e-9)
    assert body["truncated_mass"] >= 0.0


def test_tournament_probabilities(client: TestClient) -> None:
    r = client.get("/tournament-probabilities", params={"stage": "champion"})
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "champion"
    assert body["run"]["n_simulations"] == 100
    assert body["standings"][0]["team"] == "Spain"  # ranked by champion desc
    assert body["standings"][0]["champion"] == pytest.approx(0.20)


def test_tournament_probabilities_bad_stage(client: TestClient) -> None:
    assert client.get("/tournament-probabilities", params={"stage": "nonsense"}).status_code == 422


def test_run_tournament_simulation_readonly(client: TestClient) -> None:
    r = client.post("/run-tournament-simulation", json={"run_id": "wc2026"})
    assert r.status_code == 200
    body = r.json()
    assert "precomputed" in body["note"].lower() or "read-only" in body["note"].lower()
    assert body["count"] == 2
    assert client.post("/run-tournament-simulation", json={"run_id": "ghost"}).status_code == 404


def test_list_simulations(client: TestClient) -> None:
    r = client.get("/tournament-simulations")
    assert r.status_code == 200
    assert r.json()["runs"][0]["run_id"] == "wc2026"


def test_backtest_results(client: TestClient) -> None:
    r = client.get("/backtest-results", params={"level": "match"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    metrics = {m["model_name"]: m["value"] for m in body["runs"][0]["metrics"]}
    assert metrics["dixon_coles_calibrated"] < metrics["elo_only"]  # engine beats baseline


def test_model_run_detail_and_404(client: TestClient) -> None:
    r = client.get("/model-runs/dixon_coles_calibrated")
    assert r.status_code == 200
    assert r.json()["n_predictions"] == 1
    assert client.get("/model-runs/ghost").status_code == 404


def test_engine_unavailable_returns_503() -> None:
    """With no persisted 'wc2026' run, engine endpoints must 503, never refit synchronously."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.add(Team(id=1, canonical_name="Spain"))
        session.add(Team(id=2, canonical_name="France"))
        session.commit()
    app = create_app()

    def _override() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        r = test_client.post("/predict-match", json={"home_team": "Spain", "away_team": "France"})
    assert r.status_code == 503
    Base.metadata.drop_all(engine)


def test_src_does_not_import_api() -> None:
    """Dependency direction (blueprint §9): apps/api depends on src, never the reverse."""
    src = Path(__file__).resolve().parents[1] / "src" / "wc26"
    offenders = [p for p in src.rglob("*.py") if "wc26_api" in p.read_text(encoding="utf-8")]
    assert not offenders, f"src/ must not import the API package: {offenders}"


def test_openapi_schema_builds(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/predict-match" in r.json()["paths"]
