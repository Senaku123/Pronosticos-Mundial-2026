"""backtest_runs and backtest_metrics

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-11

Phase 8: match-level backtesting. Stores one run and its per-model metrics (long format).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("backtest_level", sa.String(length=12), nullable=False),
        sa.Column("test_from", sa.Date(), nullable=True),
        sa.Column("n_matches", sa.Integer(), nullable=True),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("python_version", sa.String(length=20), nullable=True),
        sa.Column("config_json", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_backtest_runs_run_id"),
    )

    op.create_table(
        "backtest_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("backtest_run_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=40), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["backtest_run_id"], ["backtest_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "backtest_run_id",
            "model_name",
            "metric",
            name="uq_backtest_metrics_run_model_metric",
        ),
    )


def downgrade() -> None:
    op.drop_table("backtest_metrics")
    op.drop_table("backtest_runs")
