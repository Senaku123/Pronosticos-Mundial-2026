"""Tests for point-in-time match features (Phase 5)."""

from __future__ import annotations

import datetime as dt

from wc26.features.match_features import build_match_features
from wc26.models.elo import MatchInput


def _m(mid: int, day: int, home: int, away: int, hs: int, as_: int) -> MatchInput:
    return MatchInput(
        mid, dt.date(2020, 1, day), home, away, hs, as_, neutral=True, importance_weight=1.0
    )


def test_first_match_has_no_form() -> None:
    rows = build_match_features([_m(1, 1, 10, 20, 2, 0)], elo_pre={})
    row = rows[0]
    assert row.home_form_n == 0
    assert row.away_form_n == 0
    assert row.home_form_points is None
    assert row.home_rest_days is None
    assert row.elo_home == 1500.0 and row.elo_diff == 0.0  # no elo provided -> base


def test_form_uses_only_prior_matches() -> None:
    matches = [
        _m(1, 1, 10, 20, 2, 0),  # team 10 wins (3 pts, gf2 ga0)
        _m(2, 5, 10, 30, 0, 1),  # team 10 loses; its form here must reflect ONLY match 1
    ]
    rows = build_match_features(matches, elo_pre={})
    second = next(r for r in rows if r.match_id == 2)
    assert second.home_form_n == 1
    assert second.home_form_points == 3.0  # only the prior win counts, not this loss
    assert second.home_gf_avg == 2.0
    assert second.home_ga_avg == 0.0
    assert second.home_rest_days == 4  # 2020-01-05 minus 2020-01-01


def test_same_day_matches_share_pre_day_form() -> None:
    # team 10 plays twice on the same day; the second match must NOT see the first's result.
    matches = [
        _m(1, 1, 10, 20, 1, 0),  # establishes some prior form on an earlier day
        _m(2, 5, 10, 30, 2, 0),  # same day as match 3
        _m(3, 5, 10, 40, 0, 1),
    ]
    rows = build_match_features(matches, elo_pre={})
    second = next(r for r in rows if r.match_id == 2)
    third = next(r for r in rows if r.match_id == 3)
    # Both same-day matches see identical pre-day form (only matches 1 counted, not each other).
    assert second.home_form_n == third.home_form_n == 1
    assert second.home_form_points == third.home_form_points == 3.0


def test_elo_features_from_lookup() -> None:
    rows = build_match_features(
        [_m(1, 1, 10, 20, 1, 0)],
        elo_pre={(1, 10): 1800.0, (1, 20): 1600.0},
    )
    assert rows[0].elo_home == 1800.0
    assert rows[0].elo_away == 1600.0
    assert rows[0].elo_diff == 200.0
