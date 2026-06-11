"""data governance: data_sources, ingestion_runs, matches.ingestion_run_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11

Phase 2: source catalog + ingestion provenance (addendum §8).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=300), nullable=False),
        sa.Column("license", sa.String(length=120), nullable=True),
        sa.Column("upstream_source", sa.String(length=120), nullable=True),
        sa.Column("upstream_license", sa.String(length=120), nullable=True),
        sa.Column("tos_notes", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_data_sources_name"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="started"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="RESTRICT"),
    )

    op.add_column(
        "matches",
        sa.Column("ingestion_run_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_matches_ingestion_run_id",
        "matches",
        "ingestion_runs",
        ["ingestion_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_matches_ingestion_run_id", "matches", type_="foreignkey")
    op.drop_column("matches", "ingestion_run_id")
    op.drop_table("ingestion_runs")
    op.drop_table("data_sources")
