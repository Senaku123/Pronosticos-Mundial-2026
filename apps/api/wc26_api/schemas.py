"""Pydantic request/response contracts for the API (the transport boundary types).

Every probability field is a plain float in [0, 1]; W/D/L triplets always come from summing the
Dixon-Coles scoreline matrix (addendum §2), never produced independently here.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    database: str
    git_sha: str | None = None
    official_run: str | None = Field(
        default=None, description="run_id of the frozen engine, if persisted"
    )


class TeamSummary(BaseModel):
    id: int
    canonical_name: str
    fifa_code: str | None = None
    confederation: str | None = None
    elo: float | None = Field(default=None, description="as-of Elo when requested")


class TeamListResponse(BaseModel):
    as_of: dt.date | None = None
    count: int
    teams: list[TeamSummary]


class EngineInfo(BaseModel):
    run_id: str
    model: str = "dixon_coles_calibrated"
    rho: float
    calibration: str = "platt_pre_tournament"
    cutoff_date: dt.date | None = None


class Scoreline(BaseModel):
    home_goals: int
    away_goals: int
    probability: float


class PredictMatchRequest(BaseModel):
    home_team: str = Field(..., description="canonical team name")
    away_team: str = Field(..., description="canonical team name")
    neutral: bool = Field(default=True, description="neutral venue (true for most WC matches)")
    as_of: dt.date | None = Field(
        default=None, description="strength as-of date; defaults to the official run's cutoff"
    )


class PredictMatchResponse(BaseModel):
    home_team: str
    away_team: str
    neutral: bool
    as_of: dt.date
    elo_home: float
    elo_away: float
    p_home_win: float
    p_draw: float
    p_away_win: float
    expected_goals_home: float
    expected_goals_away: float
    most_likely_score: Scoreline
    top_scorelines: list[Scoreline]
    engine: EngineInfo


class ScorelineMatrixResponse(BaseModel):
    home_team: str
    away_team: str
    neutral: bool
    as_of: dt.date
    max_goals: int = Field(..., description="matrix is truncated to 0..max_goals for display")
    p_home_win: float
    p_draw: float
    p_away_win: float
    matrix: list[list[float]] = Field(..., description="matrix[home_goals][away_goals]")
    truncated_mass: float = Field(
        ..., description="probability mass beyond the displayed max_goals (full matrix sums to 1)"
    )
    engine: EngineInfo


class StageProbability(BaseModel):
    team: str
    round_of_32: float | None = None
    round_of_16: float | None = None
    quarterfinal: float | None = None
    semifinal: float | None = None
    final: float | None = None
    champion: float | None = None


class SimulationRunMeta(BaseModel):
    run_id: str
    n_simulations: int
    random_seed: int | None = None
    cutoff_date: dt.date | None = None
    git_sha: str | None = None
    python_version: str | None = None
    created_at: dt.datetime | None = None


class TournamentProbabilitiesResponse(BaseModel):
    run: SimulationRunMeta
    stage: str
    count: int
    standings: list[StageProbability]


class RunTournamentSimulationRequest(BaseModel):
    run_id: str = Field(default="wc2026", description="persisted simulation run to read")


class RunTournamentSimulationResponse(BaseModel):
    run: SimulationRunMeta
    note: str
    count: int
    results: list[StageProbability]


class SimulationRunListResponse(BaseModel):
    count: int
    runs: list[SimulationRunMeta]


class BacktestMetricValue(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    metric: str
    value: float


class BacktestRunResult(BaseModel):
    run_id: str
    backtest_level: str
    test_from: dt.date | None = None
    n_matches: int | None = None
    git_sha: str | None = None
    created_at: dt.datetime | None = None
    metrics: list[BacktestMetricValue]


class BacktestResultsResponse(BaseModel):
    count: int
    runs: list[BacktestRunResult]


class ModelRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    model_name: str
    model_version: str
    git_sha: str | None = None
    data_hash: str | None = None
    cutoff_date: dt.date | None = None
    random_seed: int | None = None
    python_version: str | None = None
    config_json: str | None = None
    created_at: dt.datetime | None = None
    n_predictions: int
