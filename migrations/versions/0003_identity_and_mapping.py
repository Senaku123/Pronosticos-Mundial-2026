"""identity and mapping: tournament_mapping, team_identity_periods, team_aliases

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

Phase 3: team identity resolution + tournament category mapping (addendum §10, §11).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tournament_mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw_tournament", sa.String(length=150), nullable=False),
        sa.Column("tournament_category", sa.String(length=20), nullable=False),
        sa.Column("match_importance_weight", sa.Float(), nullable=False),
        sa.Column("confederation_scope", sa.String(length=20), nullable=True),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("mapping_version", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_tournament", name="uq_tournament_mapping_raw"),
    )

    op.create_table(
        "team_identity_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("fifa_code", sa.String(length=3), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "name", name="uq_team_identity_periods_team_name"),
    )

    op.create_table(
        "team_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=50), nullable=False),
        sa.Column("raw_name", sa.String(length=100), nullable=False),
        sa.Column("mapping_version", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_name", "raw_name", name="uq_team_aliases_source_raw"),
    )


def downgrade() -> None:
    op.drop_table("team_aliases")
    op.drop_table("team_identity_periods")
    op.drop_table("tournament_mapping")
