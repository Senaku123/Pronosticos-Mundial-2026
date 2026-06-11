"""Seed team identity periods and aliases from martj42 former_names.csv (addendum §10).

former_names.csv columns: current, former, start_date, end_date.

This records the historical-name -> current-team mapping as aliases and identity periods.
NOTE: physically collapsing historical match attribution (e.g. merging "West Germany" matches
into "Germany") is a separate, documented and backtesteable decision (docs/METHODOLOGY_ADDENDUM.md
§10) and is intentionally NOT performed here.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from wc26.database.models import Team, TeamAlias, TeamIdentityPeriod

MAPPING_VERSION = "v1"
ALIAS_SOURCE = "martj42_former_names"


def _parse_date(value: object) -> dt.date | None:
    """Parse an ISO date cell, tolerating blanks/NaN."""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return dt.date.fromisoformat(text)


def seed_team_identities(session: Session, former_names_csv: str | Path) -> dict[str, int]:
    """Seed aliases + identity periods from former_names.csv. Idempotent. Returns stats.

    Both inserts use ON CONFLICT DO NOTHING on their unique keys, so re-running is safe and
    creates no duplicates (we do not rely on ``rowcount``, which is unreliable for DO NOTHING).
    """
    df = pd.read_csv(former_names_csv)
    team_ids = {
        name: team_id
        for name, team_id in session.execute(select(Team.canonical_name, Team.id)).all()
    }
    processed = 0
    skipped = 0
    for row in df.itertuples(index=False):
        current = str(row.current).strip()
        former = str(row.former).strip()
        team_id = team_ids.get(current)
        if team_id is None:
            skipped += 1
            continue
        session.execute(
            pg_insert(TeamAlias)
            .values(
                team_id=team_id,
                source_name=ALIAS_SOURCE,
                raw_name=former,
                mapping_version=MAPPING_VERSION,
            )
            .on_conflict_do_nothing(constraint="uq_team_aliases_source_raw")
        )
        session.execute(
            pg_insert(TeamIdentityPeriod)
            .values(
                team_id=team_id,
                name=former,
                valid_from=_parse_date(row.start_date),
                valid_to=_parse_date(row.end_date),
            )
            .on_conflict_do_nothing(constraint="uq_team_identity_periods_team_name")
        )
        processed += 1
    session.flush()
    return {"processed": processed, "skipped": skipped}
