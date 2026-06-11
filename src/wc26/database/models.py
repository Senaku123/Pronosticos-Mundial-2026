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
