"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture
def db_session() -> Iterator[object]:
    """Yield a DB session, or skip the test if no database is reachable.

    Keeps the unit suite runnable without PostgreSQL (e.g. the lint/type/test CI job),
    while DB-dependent tests still run locally where a database is configured.
    """
    try:
        from sqlalchemy import text

        from wc26.database.base import get_engine, get_session_factory

        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"no database available: {exc}")

    factory = get_session_factory(engine)
    with factory() as session:
        yield session
