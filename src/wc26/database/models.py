"""Core ORM models (Phase 1): confederations, teams, tournaments, matches.

This is the *initial* schema only. Identity tables (team_aliases, team_identity_periods),
tournament_mapping, ratings/rankings, features, model runs, simulations and backtesting
are introduced incrementally in their own phases via Alembic migrations
(see docs/PHASES.md). The schema is treated as a revisable hypothesis, not a closed contract.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from wc26.database.base import Base


class Confederation(Base):
    """Football confederation (UEFA, CONMEBOL, CONCACAF, CAF, AFC, OFC)."""

    __tablename__ = "confederations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Team(Base):
    """A national team (stable federative identity).

    Historical name/identity changes (Yugoslavia/Serbia, USSR/Russia, ...) are modeled in
    Phase 3 via ``team_identity_periods`` and ``team_aliases`` (addendum §10).
    """

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(100), unique=True)
    fifa_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    confederation_id: Mapped[int | None] = mapped_column(
        ForeignKey("confederations.id", ondelete="SET NULL"), nullable=True
    )


class Tournament(Base):
    """A competition instance. The free-text label is normalized later via tournament_mapping."""

    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    raw_tournament: Mapped[str | None] = mapped_column(String(150), nullable=True)
    start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (UniqueConstraint("name", name="uq_tournaments_name"),)


class Match(Base):
    """A played international match. Natural key prevents duplicate ingestion (idempotency)."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_date: Mapped[dt.date] = mapped_column(Date)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="RESTRICT"))
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    neutral: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "home_team_id",
            "away_team_id",
            "match_date",
            "tournament_id",
            name="uq_matches_natural",
        ),
    )


class DataSource(Base):
    """Catalog of external data sources (provenance + licensing). See docs/DATA_SOURCES.md."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    url: Mapped[str] = mapped_column(String(300))
    license: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upstream_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upstream_license: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tos_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class IngestionRun(Base):
    """One ingestion of one source snapshot (idempotency + traceability anchor, addendum §8)."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"))
    snapshot_date: Mapped[dt.date] = mapped_column(Date)
    file_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="started")
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TournamentMapping(Base):
    """Maps a raw free-text tournament label to a clean category + weight (addendum §11).

    Weights are NOT final: they are a starting hypothesis to be validated by backtesting
    (see docs/METHODOLOGY_ADDENDUM.md §11 and docs/BACKTESTING_STRATEGY.md).
    """

    __tablename__ = "tournament_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_tournament: Mapped[str] = mapped_column(String(150), unique=True)
    tournament_category: Mapped[str] = mapped_column(String(20))
    match_importance_weight: Mapped[float] = mapped_column(Float)
    confederation_scope: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mapping_version: Mapped[str] = mapped_column(String(20))


class TeamIdentityPeriod(Base):
    """A named period of a national team's stable identity (addendum §10).

    Models historical name/identity changes (e.g. West Germany -> Germany) with validity
    dates. Succession policy is documented in docs/METHODOLOGY_ADDENDUM.md §10.
    """

    __tablename__ = "team_identity_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    fifa_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("team_id", "name", name="uq_team_identity_periods_team_name"),
    )


class TeamAlias(Base):
    """Maps a source-specific raw team name to a canonical team (addendum §10)."""

    __tablename__ = "team_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    source_name: Mapped[str] = mapped_column(String(50))
    raw_name: Mapped[str] = mapped_column(String(100))
    mapping_version: Mapped[str] = mapped_column(String(20))

    __table_args__ = (
        UniqueConstraint("source_name", "raw_name", name="uq_team_aliases_source_raw"),
    )


class EloRating(Base):
    """Internally-recomputed Elo rating, one row per (team, match) (addendum §1).

    Stores the team's rating BEFORE the match (``rating_pre``, the leakage-safe strength used
    for prediction) and AFTER (``rating_post``). The strength of a team as-of any date is the
    ``rating_post`` of its most recent match strictly before that date.
    """

    __tablename__ = "elo_ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    match_date: Mapped[dt.date] = mapped_column(Date)
    rating_pre: Mapped[float] = mapped_column(Float)
    rating_post: Mapped[float] = mapped_column(Float)
    is_home: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (UniqueConstraint("team_id", "match_id", name="uq_elo_ratings_team_match"),)


class MatchFeature(Base):
    """Point-in-time features for one match (Phase 5).

    Every column is computed using ONLY information strictly before the match (day-atomic),
    so a row is leakage-safe for predicting its match. Versioned for reproducibility (addendum §8):
    ``feature_pipeline_version`` + ``cutoff_date`` + ``code_git_sha``.
    """

    __tablename__ = "match_features"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    feature_pipeline_version: Mapped[str] = mapped_column(String(20))
    cutoff_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    code_git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Strength (from internal Elo, rating_pre).
    elo_home: Mapped[float] = mapped_column(Float)
    elo_away: Mapped[float] = mapped_column(Float)
    elo_diff: Mapped[float] = mapped_column(Float)

    # Recent form over the last N matches (NULL when the team has no prior matches).
    home_form_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_form_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_gf_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_ga_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_gf_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_ga_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_form_n: Mapped[int] = mapped_column(Integer)
    away_form_n: Mapped[int] = mapped_column(Integer)

    # Rest (days since each team's previous match; NULL for a team's first match).
    home_rest_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_rest_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Context.
    importance_weight: Mapped[float] = mapped_column(Float)
    is_neutral: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (UniqueConstraint("match_id", name="uq_match_features_match"),)


class ModelRun(Base):
    """One run of one model/baseline, with reproducibility metadata (addendum §8)."""

    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True)
    model_name: Mapped[str] = mapped_column(String(50))
    model_version: Mapped[str] = mapped_column(String(20))
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cutoff_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    python_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    package_lock: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_json: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MatchPrediction(Base):
    """Per-match W/D/L (and optional expected goals / most-likely score) for a model run.

    W/D/L is the single source of truth derived per model: a baseline writes it directly; the
    Dixon-Coles scoreline model (Phase 7) derives it by summing zones of its matrix (addendum §2).
    """

    __tablename__ = "match_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    p_home_win: Mapped[float] = mapped_column(Float)
    p_draw: Mapped[float] = mapped_column(Float)
    p_away_win: Mapped[float] = mapped_column(Float)
    expected_goals_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_goals_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("model_run_id", "match_id", name="uq_match_predictions_run_match"),
    )


class ScorelineProbability(Base):
    """One cell of a match's scoreline probability matrix (addendum: scoreline matrix).

    Stored only for 'official' predictions (e.g. the 2026 fixtures), not per Monte Carlo
    iteration. W/D/L is derived by summing zones of these cells (the single source of truth).
    """

    __tablename__ = "scoreline_probabilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    probability: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint(
            "model_run_id",
            "match_id",
            "home_goals",
            "away_goals",
            name="uq_scoreline_run_match_score",
        ),
    )


class CalibrationCurve(Base):
    """Reliability bins for a model run, by outcome class and raw/calibrated, on a test split.

    Lets the calibration be inspected and audited (predicted vs observed per bin) instead of
    recomputed at view time (addendum §2 / Phase 7b).
    """

    __tablename__ = "calibration_curves"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"))
    outcome_class: Mapped[str] = mapped_column(String(10))  # home | draw | away
    calibration: Mapped[str] = mapped_column(String(10))  # raw | calibrated
    split: Mapped[str] = mapped_column(String(10))  # train | test
    bin_index: Mapped[int] = mapped_column(Integer)
    mean_predicted: Mapped[float] = mapped_column(Float)
    observed_frequency: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)


class BacktestRun(Base):
    """One match-level (or tournament/live) backtest evaluation (addendum §3, §4)."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True)
    backtest_level: Mapped[str] = mapped_column(String(12))  # match | tournament | live
    test_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    n_matches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    python_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    config_json: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BacktestMetric(Base):
    """One metric value for one model within a backtest run (long format)."""

    __tablename__ = "backtest_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(40))
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint(
            "backtest_run_id", "model_name", "metric", name="uq_backtest_metrics_run_model_metric"
        ),
    )


class TournamentSimulation(Base):
    """One Monte Carlo simulation of a tournament (addendum §8, §9). Aggregates only."""

    __tablename__ = "tournament_simulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True)
    model_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True
    )
    n_simulations: Mapped[int] = mapped_column(Integer)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cutoff_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    python_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    config_json: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SimulationResult(Base):
    """Aggregated stage probability for one team in one tournament simulation (addendum §9)."""

    __tablename__ = "simulation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_simulation_id: Mapped[int] = mapped_column(
        ForeignKey("tournament_simulations.id", ondelete="CASCADE")
    )
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(16))
    probability: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint(
            "tournament_simulation_id",
            "team_id",
            "stage",
            name="uq_simulation_results_sim_team_stage",
        ),
    )
