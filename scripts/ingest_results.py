"""Validate and ingest a martj42 results.csv snapshot into PostgreSQL (idempotent).

Usage:
    uv run python scripts/ingest_results.py path/to/results.csv

Requires a running database (docker compose up -d db) with migrations applied
(alembic upgrade head). Re-running is safe: duplicates are skipped on natural keys.
"""

from __future__ import annotations

import sys

from wc26.data.ingest import ingest_results, seed_data_sources
from wc26.database.base import get_session_factory
from wc26.utils.hashing import sha256_file


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: ingest_results.py <path-to-results.csv>")
        return 2
    csv_path = argv[0]
    file_hash = sha256_file(csv_path)

    session_factory = get_session_factory()
    with session_factory() as session:
        seed_data_sources(session)
        session.commit()
        run = ingest_results(session, csv_path, source_name="martj42_results", file_hash=file_hash)
        print(
            f"[ok] ingestion_run id={run.id} rows={run.row_count} "
            f"status={run.status} hash={file_hash[:12]}..."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
