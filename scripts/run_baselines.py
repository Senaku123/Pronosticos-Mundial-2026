"""Generate baseline predictions for every played match (for Phase 8 backtesting).

Usage:
    uv run python scripts/run_baselines.py

Predicts all rows in match_features with each baseline and stores them under one model_run per
baseline. Shows a tqdm progress bar per baseline. Idempotent (re-running overwrites each run).
"""

from __future__ import annotations

import platform
import sys

from sqlalchemy import select
from tqdm import tqdm

from wc26.database.base import get_session_factory
from wc26.database.models import MatchFeature
from wc26.models.baselines import BASELINES
from wc26.models.predict import reset_model_run, store_predictions
from wc26.utils.provenance import git_sha as _git_sha


def main(argv: list[str]) -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        features = session.execute(
            select(
                MatchFeature.match_id,
                MatchFeature.elo_home,
                MatchFeature.elo_away,
                MatchFeature.is_neutral,
            )
        ).all()

        for name, predict in BASELINES.items():
            run_id = reset_model_run(
                session,
                run_id=name,
                model_name=name,
                git_sha=_git_sha(),
                python_version=platform.python_version(),
            )
            rows: list[dict[str, object]] = []
            for match_id, elo_home, elo_away, neutral in tqdm(
                features, desc=f"{name:<15}", unit="match"
            ):
                p = predict(elo_home, elo_away, neutral)
                rows.append(
                    {
                        "model_run_id": run_id,
                        "match_id": match_id,
                        "p_home_win": p.p_home_win,
                        "p_draw": p.p_draw,
                        "p_away_win": p.p_away_win,
                        "expected_goals_home": p.expected_goals_home,
                        "expected_goals_away": p.expected_goals_away,
                        "predicted_home_score": p.predicted_home_score,
                        "predicted_away_score": p.predicted_away_score,
                    }
                )
            store_predictions(session, rows)
            session.commit()
            print(f"[ok] {name}: {len(rows)} predictions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
