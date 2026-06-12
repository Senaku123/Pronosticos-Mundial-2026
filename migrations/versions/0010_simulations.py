"""tournament_simulations and simulation_results

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-11

Phase 10: Monte Carlo tournament simulation. Stores the run metadata and aggregated stage
probabilities only (no raw per-iteration matches), per addendum §9.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tournament_simulations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=True),
        sa.Column("n_simulations", sa.Integer(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=True),
        sa.Column("cutoff_date", sa.Date(), nullable=True),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("python_version", sa.String(length=20), nullable=True),
        sa.Column("config_json", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("run_id", name="uq_tournament_simulations_run_id"),
    )

    op.create_table(
        "simulation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tournament_simulation_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tournament_simulation_id"], ["tournament_simulations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tournament_simulation_id",
            "team_id",
            "stage",
            name="uq_simulation_results_sim_team_stage",
        ),
    )


def downgrade() -> None:
    op.drop_table("simulation_results")
    op.drop_table("tournament_simulations")
