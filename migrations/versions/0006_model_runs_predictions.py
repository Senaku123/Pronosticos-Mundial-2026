"""model_runs and match_predictions

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-11

Phase 6: baseline models. model_runs carries reproducibility metadata; match_predictions holds
per-match W/D/L (+ optional expected goals / most-likely score) per run.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=50), nullable=False),
        sa.Column("model_version", sa.String(length=20), nullable=False),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("data_hash", sa.String(length=64), nullable=True),
        sa.Column("cutoff_date", sa.Date(), nullable=True),
        sa.Column("random_seed", sa.Integer(), nullable=True),
        sa.Column("python_version", sa.String(length=20), nullable=True),
        sa.Column("package_lock", sa.String(length=64), nullable=True),
        sa.Column("config_json", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_model_runs_run_id"),
    )

    op.create_table(
        "match_predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("p_home_win", sa.Float(), nullable=False),
        sa.Column("p_draw", sa.Float(), nullable=False),
        sa.Column("p_away_win", sa.Float(), nullable=False),
        sa.Column("expected_goals_home", sa.Float(), nullable=True),
        sa.Column("expected_goals_away", sa.Float(), nullable=True),
        sa.Column("predicted_home_score", sa.Integer(), nullable=True),
        sa.Column("predicted_away_score", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("model_run_id", "match_id", name="uq_match_predictions_run_match"),
    )


def downgrade() -> None:
    op.drop_table("match_predictions")
    op.drop_table("model_runs")
