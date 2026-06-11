"""scoreline_probabilities

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-11

Phase 7: Dixon-Coles scoreline matrix cells for official predictions (single source of truth).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scoreline_probabilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("home_goals", sa.Integer(), nullable=False),
        sa.Column("away_goals", sa.Integer(), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "model_run_id",
            "match_id",
            "home_goals",
            "away_goals",
            name="uq_scoreline_run_match_score",
        ),
    )


def downgrade() -> None:
    op.drop_table("scoreline_probabilities")
