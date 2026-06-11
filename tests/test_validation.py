"""Tests for the pandera validation schema of results.csv."""

from __future__ import annotations

import pandas as pd
import pytest
from pandera.errors import SchemaErrors

from wc26.data.validation import validate_results


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2022-11-20", "1872-11-30"],
            "home_team": ["Qatar", "Scotland"],
            "away_team": ["Ecuador", "England"],
            "home_score": [0, 0],
            "away_score": [2, 0],
            "tournament": ["FIFA World Cup", "Friendly"],
            "city": ["Al Khor", "Glasgow"],
            "country": ["Qatar", "Scotland"],
            "neutral": [False, False],
        }
    )


def test_valid_frame_passes() -> None:
    out = validate_results(_valid_frame())
    assert len(out) == 2


def test_missing_column_fails() -> None:
    df = _valid_frame().drop(columns=["neutral"])
    with pytest.raises(SchemaErrors):
        validate_results(df)


def test_null_home_team_fails() -> None:
    df = _valid_frame()
    df.loc[0, "home_team"] = None
    with pytest.raises(SchemaErrors):
        validate_results(df)


def test_negative_score_fails() -> None:
    df = _valid_frame()
    df.loc[0, "home_score"] = -1
    with pytest.raises(SchemaErrors):
        validate_results(df)
