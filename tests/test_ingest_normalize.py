"""Tests for ingestion normalization helpers (no database required)."""

from __future__ import annotations

import math

from wc26.data.ingest import _to_int, _to_str, load_results


def test_load_results_normalizes_neutral(tmp_path) -> None:
    csv = tmp_path / "results.csv"
    csv.write_text(
        "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
        "2022-11-20,Qatar,Ecuador,0,2,FIFA World Cup,Al Khor,Qatar,FALSE\n"
        "2022-12-18,Argentina,France,3,3,FIFA World Cup,Lusail,Qatar,TRUE\n",
        encoding="utf-8",
    )
    df = load_results(csv)
    assert df["neutral"].dtype == bool
    assert df["neutral"].tolist() == [False, True]


def test_to_int_handles_missing() -> None:
    assert _to_int(2.0) == 2
    assert _to_int(3) == 3
    assert _to_int(None) is None
    assert _to_int(math.nan) is None


def test_to_str_strips_and_nulls() -> None:
    assert _to_str("  Glasgow ") == "Glasgow"
    assert _to_str("") is None
    assert _to_str(math.nan) is None
