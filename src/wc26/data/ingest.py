"""Idempotent ingestion of match results into PostgreSQL.

Re-running an ingestion does not create duplicates: teams, tournaments and matches are
UPSERTed on their natural keys (ON CONFLICT DO NOTHING). Every ingestion is recorded in
``ingestion_runs`` for traceability (addendum §8). Team-identity resolution and tournament
category mapping are deliberately left to Phase 3; here teams are keyed by their raw
canonical name and tournaments by their raw label.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from wc26.data.sources import REGISTRY
from wc26.data.validation import validate_results
from wc26.database.models import DataSource, IngestionRun, Match, Team, Tournament

_TRUTHY = {"TRUE", "T", "1", "YES"}

# Max match rows per INSERT (~11 columns each) to stay under PostgreSQL's 65535-param limit.
_MATCH_INSERT_CHUNK = 5000


def load_results(path: str | Path) -> pd.DataFrame:
    """Read results.csv and normalize the ``neutral`` flag to a real boolean."""
    df = pd.read_csv(path)
    df["neutral"] = df["neutral"].astype(str).str.strip().str.upper().isin(_TRUTHY)
    return df


def _to_int(value: float | int | str | None) -> int | None:
    """Convert a possibly-missing numeric cell to int or None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return int(value)


def _to_str(value: object) -> str | None:
    """Convert a possibly-missing/empty cell to a stripped string or None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def seed_data_sources(session: Session) -> None:
    """Insert the canonical source registry (idempotent)."""
    for spec in REGISTRY.values():
        stmt = (
            pg_insert(DataSource)
            .values(
                name=spec.name,
                url=spec.url,
                license=spec.license,
                upstream_source=spec.upstream_source,
                upstream_license=spec.upstream_license,
                tos_notes=spec.tos_notes,
            )
            .on_conflict_do_nothing(constraint="uq_data_sources_name")
        )
        session.execute(stmt)
    session.flush()


def upsert_teams(session: Session, names: list[str]) -> dict[str, int]:
    """Insert any new teams (by canonical name) and return a name -> id map."""
    if names:
        session.execute(
            pg_insert(Team)
            .values([{"canonical_name": name} for name in names])
            .on_conflict_do_nothing(constraint="uq_teams_canonical_name")
        )
        session.flush()
    rows = session.execute(select(Team.canonical_name, Team.id)).all()
    return {name: team_id for name, team_id in rows}


def upsert_tournaments(session: Session, names: list[str]) -> dict[str, int]:
    """Insert any new tournaments (by raw label) and return a name -> id map."""
    if names:
        session.execute(
            pg_insert(Tournament)
            .values([{"name": name, "raw_tournament": name} for name in names])
            .on_conflict_do_nothing(constraint="uq_tournaments_name")
        )
        session.flush()
    rows = session.execute(select(Tournament.name, Tournament.id)).all()
    return {name: tournament_id for name, tournament_id in rows}


def upsert_matches(
    session: Session,
    df: pd.DataFrame,
    team_ids: dict[str, int],
    tournament_ids: dict[str, int],
    ingestion_run_id: int,
    source_name: str,
) -> int:
    """Insert matches on their natural key (idempotent). Returns rows inserted."""
    records = [
        {
            "match_date": dt.date.fromisoformat(str(row.date)),
            "home_team_id": team_ids[row.home_team],
            "away_team_id": team_ids[row.away_team],
            "tournament_id": tournament_ids[row.tournament],
            "home_score": _to_int(row.home_score),
            "away_score": _to_int(row.away_score),
            "neutral": bool(row.neutral),
            "city": _to_str(row.city),
            "country": _to_str(row.country),
            "source_name": source_name,
            "ingestion_run_id": ingestion_run_id,
        }
        for row in df.itertuples(index=False)
    ]
    if not records:
        return 0
    # Chunk inserts to stay under PostgreSQL's 65535 bound parameters per statement
    # (each match row binds ~11 columns).
    inserted = 0
    for start in range(0, len(records), _MATCH_INSERT_CHUNK):
        chunk = records[start : start + _MATCH_INSERT_CHUNK]
        result = session.execute(
            pg_insert(Match).values(chunk).on_conflict_do_nothing(constraint="uq_matches_natural")
        )
        inserted += result.rowcount or 0  # type: ignore[attr-defined]  # CursorResult at runtime
    return inserted


def ingest_results(
    session: Session,
    csv_path: str | Path,
    source_name: str = "martj42_results",
    snapshot_date: dt.date | None = None,
    file_hash: str = "",
) -> IngestionRun:
    """Validate and idempotently ingest a results snapshot, recording the ingestion run."""
    source = session.execute(select(DataSource).where(DataSource.name == source_name)).scalar_one()

    df = validate_results(load_results(csv_path))

    run = IngestionRun(
        source_id=source.id,
        snapshot_date=snapshot_date or dt.date.today(),
        file_hash=file_hash,
        status="started",
    )
    session.add(run)
    session.flush()

    team_ids = upsert_teams(session, sorted(set(df["home_team"]) | set(df["away_team"])))
    tournament_ids = upsert_tournaments(session, sorted(set(df["tournament"])))
    upsert_matches(session, df, team_ids, tournament_ids, run.id, source_name)

    run.row_count = int(len(df))
    run.status = "completed"
    run.finished_at = dt.datetime.now(dt.UTC)
    session.commit()
    return run
