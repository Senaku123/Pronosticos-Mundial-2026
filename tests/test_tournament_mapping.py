"""Tests for tournament category mapping (addendum §11)."""

from __future__ import annotations

from wc26.identity.tournament_mapping import classify_tournament, find_unmapped_tournaments


def test_classify_categories() -> None:
    cases = {
        "Friendly": "friendly",
        "FIFA World Cup": "world_cup",
        "FIFA World Cup qualification": "qualifier",
        "UEFA Euro": "continental_cup",
        "UEFA Euro qualification": "qualifier",
        "UEFA Nations League": "nations_league",
        "CONCACAF Nations League qualification": "qualifier",
        "Copa América": "continental_cup",
        "African Cup of Nations": "continental_cup",
        "Gold Cup": "continental_cup",
        "CECAFA Cup": "other",
        "British Home Championship": "other",
    }
    for name, expected in cases.items():
        assert classify_tournament(name) == expected, name


def test_no_unmapped_tournaments(db_session) -> None:
    # Requires a seeded database; skipped automatically when no DB is available.
    assert find_unmapped_tournaments(db_session) == []
