"""Team endpoints: list teams and fetch one (optionally with as-of Elo strength)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from wc26.database.models import Confederation, Team
from wc26.features.cutoff import get_rating_as_of
from wc26_api.deps import get_session
from wc26_api.schemas import TeamListResponse, TeamSummary

router = APIRouter(tags=["teams"])


@router.get("/teams", response_model=TeamListResponse)
def list_teams(
    session: Session = Depends(get_session),
    confederation: str | None = Query(
        default=None, description="filter by confederation code (e.g. UEFA, CONMEBOL)"
    ),
    with_elo: bool = Query(default=False, description="include each team's as-of Elo"),
    as_of: dt.date | None = Query(default=None, description="as-of date for Elo (default: today)"),
    limit: int = Query(default=500, ge=1, le=2000),
) -> TeamListResponse:
    """List teams (alphabetical). Elo is computed only when ``with_elo`` is set."""
    stmt = (
        select(Team.id, Team.canonical_name, Team.fifa_code, Confederation.code)
        .outerjoin(Confederation, Confederation.id == Team.confederation_id)
        .order_by(Team.canonical_name)
        .limit(limit)
    )
    if confederation is not None:
        stmt = stmt.where(Confederation.code == confederation)
    rows = session.execute(stmt).all()

    effective_as_of = as_of if as_of is not None else dt.date.today()
    teams = [
        TeamSummary(
            id=row.id,
            canonical_name=row.canonical_name,
            fifa_code=row.fifa_code,
            confederation=row.code,
            elo=get_rating_as_of(session, row.id, effective_as_of) if with_elo else None,
        )
        for row in rows
    ]
    return TeamListResponse(
        as_of=effective_as_of if with_elo else None, count=len(teams), teams=teams
    )


@router.get("/teams/{team_id}", response_model=TeamSummary)
def get_team(
    team_id: int,
    session: Session = Depends(get_session),
    as_of: dt.date | None = Query(default=None, description="as-of date for Elo (default: today)"),
) -> TeamSummary:
    """Fetch one team with its as-of Elo strength."""
    row = session.execute(
        select(Team.id, Team.canonical_name, Team.fifa_code, Confederation.code)
        .outerjoin(Confederation, Confederation.id == Team.confederation_id)
        .where(Team.id == team_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"team id {team_id} not found")
    effective_as_of = as_of if as_of is not None else dt.date.today()
    return TeamSummary(
        id=row.id,
        canonical_name=row.canonical_name,
        fifa_code=row.fifa_code,
        confederation=row.code,
        elo=get_rating_as_of(session, row.id, effective_as_of),
    )
