"""Schema validation for raw ingested data (pandera).

Validation runs at the raw -> interim boundary and aborts the pipeline on invalid data,
so identity/leakage errors surface early instead of deep in the backtest (Phase 2 criteria).
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

# Schema for martj42 results.csv: exactly 9 columns, teams/tournament non-null,
# scores non-negative (nullable to tolerate future fixtures), neutral as boolean.
RESULTS_SCHEMA = pa.DataFrameSchema(
    {
        "date": pa.Column(pa.String, nullable=False),
        "home_team": pa.Column(pa.String, nullable=False),
        "away_team": pa.Column(pa.String, nullable=False),
        "home_score": pa.Column(pa.Float, nullable=True, checks=pa.Check.ge(0), coerce=True),
        "away_score": pa.Column(pa.Float, nullable=True, checks=pa.Check.ge(0), coerce=True),
        "tournament": pa.Column(pa.String, nullable=False),
        "city": pa.Column(pa.String, nullable=True),
        "country": pa.Column(pa.String, nullable=True),
        "neutral": pa.Column(pa.Bool, nullable=False),
    },
    strict=True,
    coerce=True,
)


def validate_results(df: pd.DataFrame) -> pd.DataFrame:
    """Validate the results DataFrame; raises ``pandera.errors.SchemaError(s)`` on failure."""
    return RESULTS_SCHEMA.validate(df, lazy=True)
