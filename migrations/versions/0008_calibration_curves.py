"""calibration_curves

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-11

Phase 7b: stored reliability bins (predicted vs observed) per model run / class / raw|calibrated.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calibration_curves",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("outcome_class", sa.String(length=10), nullable=False),
        sa.Column("calibration", sa.String(length=10), nullable=False),
        sa.Column("split", sa.String(length=10), nullable=False),
        sa.Column("bin_index", sa.Integer(), nullable=False),
        sa.Column("mean_predicted", sa.Float(), nullable=False),
        sa.Column("observed_frequency", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("calibration_curves")
