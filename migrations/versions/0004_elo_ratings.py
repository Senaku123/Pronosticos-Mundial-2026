"""elo_ratings: internally-recomputed Elo, one row per (team, match)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11

Phase 4: anti-leakage strength signal. Elo is recomputed in-house from played matches with a
strict chronological order, so a rating never depends on future results (addendum §1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "elo_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("rating_pre", sa.Float(), nullable=False),
        sa.Column("rating_post", sa.Float(), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "match_id", name="uq_elo_ratings_team_match"),
    )
    # Index for as-of lookups: latest rating for a team strictly before a date.
    op.create_index("ix_elo_ratings_team_date", "elo_ratings", ["team_id", "match_date"])


def downgrade() -> None:
    op.drop_index("ix_elo_ratings_team_date", table_name="elo_ratings")
    op.drop_table("elo_ratings")
