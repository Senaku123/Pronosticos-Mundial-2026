"""SQLAlchemy declarative base and engine/session factories.

Engines/sessions are created lazily through factory functions so that importing this
module never requires a live ``DATABASE_URL`` (keeps unit tests and CI imports cheap).
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from wc26.utils.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def get_engine(echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine from the configured ``DATABASE_URL``."""
    return create_engine(get_settings().database_url, echo=echo, future=True)


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Return a configured session factory bound to ``engine`` (or a fresh engine)."""
    return sessionmaker(
        bind=engine or get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )
