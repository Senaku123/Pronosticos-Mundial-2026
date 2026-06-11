"""initial core schema: confederations, teams, tournaments, matches

Revision ID: 0001
Revises:
Create Date: 2026-06-11

Phase 1 initial schema only. Later tables are added in their own migrations (see docs/PHASES.md).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "confederations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_confederations_code"),
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_name", sa.String(length=100), nullable=False),
        sa.Column("fifa_code", sa.String(length=3), nullable=True),
        sa.Column("confederation_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name", name="uq_teams_canonical_name"),
        sa.ForeignKeyConstraint(
            ["confederation_id"], ["confederations.id"], ondelete="SET NULL"
        ),
    )

    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("raw_tournament", sa.String(length=150), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tournaments_name"),
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("tournament_id", sa.Integer(), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("neutral", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("source_name", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["home_team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["away_team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "home_team_id",
            "away_team_id",
            "match_date",
            "tournament_id",
            name="uq_matches_natural",
        ),
    )
    op.create_index("ix_matches_match_date", "matches", ["match_date"])


def downgrade() -> None:
    op.drop_index("ix_matches_match_date", table_name="matches")
    op.drop_table("matches")
    op.drop_table("tournaments")
    op.drop_table("teams")
    op.drop_table("confederations")
