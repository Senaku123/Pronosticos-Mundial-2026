"""Smoke test: the package and its core modules import without a live database."""

from __future__ import annotations


def test_package_imports() -> None:
    import wc26

    assert wc26.__version__


def test_core_modules_import() -> None:
    from wc26.database import base, models
    from wc26.utils import config, hashing, seeds

    # Core ORM tables are registered on the shared metadata.
    assert {"confederations", "teams", "tournaments", "matches"} <= set(
        base.Base.metadata.tables
    )
    assert models.Match.__tablename__ == "matches"
    assert hasattr(config, "get_settings")
    assert hasattr(hashing, "sha256_file")
    assert hasattr(seeds, "set_global_seed")
