"""Request-scoped dependencies (DB session) for the API."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from wc26.database.base import get_session_factory


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    """One engine/session factory per process (created lazily on first request)."""
    return get_session_factory()


def get_session() -> Iterator[Session]:
    """Yield a DB session for one request, always closed afterwards."""
    with _session_factory()() as session:
        yield session
