"""match_features: point-in-time features per match

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11

Phase 5: leakage-safe feature set per match (Elo, recent form, rest, context).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("feature_pipeline_version", sa.String(length=20), nullable=False),
        sa.Column("cutoff_date", sa.Date(), nullable=True),
        sa.Column("code_git_sha", sa.String(length=40), nullable=True),
        sa.Column("elo_home", sa.Float(), nullable=False),
        sa.Column("elo_away", sa.Float(), nullable=False),
        sa.Column("elo_diff", sa.Float(), nullable=False),
        sa.Column("home_form_points", sa.Float(), nullable=True),
        sa.Column("away_form_points", sa.Float(), nullable=True),
        sa.Column("home_gf_avg", sa.Float(), nullable=True),
        sa.Column("home_ga_avg", sa.Float(), nullable=True),
        sa.Column("away_gf_avg", sa.Float(), nullable=True),
        sa.Column("away_ga_avg", sa.Float(), nullable=True),
        sa.Column("home_form_n", sa.Integer(), nullable=False),
        sa.Column("away_form_n", sa.Integer(), nullable=False),
        sa.Column("home_rest_days", sa.Integer(), nullable=True),
        sa.Column("away_rest_days", sa.Integer(), nullable=True),
        sa.Column("importance_weight", sa.Float(), nullable=False),
        sa.Column("is_neutral", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("match_id", name="uq_match_features_match"),
    )


def downgrade() -> None:
    op.drop_table("match_features")
