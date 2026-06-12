"""Fit Dixon-Coles rho and forecast the 2026 World Cup with the official scoreline model.

Usage:
    uv run python scripts/forecast_dc.py

Fits rho by MLE on all played matches (lambdas from Elo), then forecasts each not-yet-played
World Cup fixture, storing W/D/L (single source of truth, summed from the matrix) and the full
scoreline matrix. Requires match_features + elo_ratings seeded.
"""

from __future__ import annotations

import platform
import sys

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import aliased
from tqdm import tqdm

from wc26.database.base import get_session_factory
from wc26.database.models import Match, MatchFeature, ScorelineProbability, Team, Tournament
from wc26.features.cutoff import get_rating_as_of
from wc26.models.baselines import BaselineConfig, elo_to_lambdas
from wc26.models.dixon_coles import DixonColesConfig, fit_rho, predict_dixon_coles
from wc26.models.predict import reset_model_run, store_predictions
from wc26.utils.provenance import git_sha as _git_sha


def main(argv: list[str]) -> int:
    base_cfg = BaselineConfig()
    session_factory = get_session_factory()
    with session_factory() as session:
        # 1) Fit rho by MLE on played matches (lambdas derived from Elo).
        training = session.execute(
            select(
                MatchFeature.elo_home,
                MatchFeature.elo_away,
                MatchFeature.is_neutral,
                Match.home_score,
                Match.away_score,
            ).join(Match, Match.id == MatchFeature.match_id)
        ).all()
        samples = []
        for elo_home, elo_away, neutral, home_score, away_score in training:
            lambda_home, lambda_away = elo_to_lambdas(elo_home, elo_away, neutral, base_cfg)
            samples.append((lambda_home, lambda_away, int(home_score), int(away_score)))
        rho = fit_rho(samples)
        cfg = DixonColesConfig(rho=rho)
        print(f"[ok] fitted Dixon-Coles rho={rho:.4f} on {len(samples)} played matches")

        # 2) Forecast the not-yet-played World Cup fixtures.
        home = aliased(Team)
        away = aliased(Team)
        fixtures = session.execute(
            select(
                Match.id,
                Match.match_date,
                Match.home_team_id,
                Match.away_team_id,
                Match.neutral,
                home.canonical_name.label("home_name"),
                away.canonical_name.label("away_name"),
            )
            .join(Tournament, Tournament.id == Match.tournament_id)
            .join(home, home.id == Match.home_team_id)
            .join(away, away.id == Match.away_team_id)
            .where(Tournament.name == "FIFA World Cup", Match.home_score.is_(None))
            .order_by(Match.match_date, Match.id)
        ).all()

        run_id = reset_model_run(
            session,
            run_id="dixon_coles_wc2026",
            model_name="dixon_coles",
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=f'{{"rho": {rho:.4f}}}',
        )
        session.execute(
            delete(ScorelineProbability).where(ScorelineProbability.model_run_id == run_id)
        )

        prediction_rows: list[dict[str, object]] = []
        cell_rows: list[dict[str, object]] = []
        table = []
        for fx in tqdm(fixtures, desc="Dixon-Coles WC2026", unit="match"):
            elo_home = get_rating_as_of(session, fx.home_team_id, fx.match_date)
            elo_away = get_rating_as_of(session, fx.away_team_id, fx.match_date)
            pred, matrix = predict_dixon_coles(elo_home, elo_away, fx.neutral, cfg)
            prediction_rows.append(
                {
                    "model_run_id": run_id,
                    "match_id": fx.id,
                    "p_home_win": pred.p_home_win,
                    "p_draw": pred.p_draw,
                    "p_away_win": pred.p_away_win,
                    "expected_goals_home": pred.expected_goals_home,
                    "expected_goals_away": pred.expected_goals_away,
                    "predicted_home_score": pred.predicted_home_score,
                    "predicted_away_score": pred.predicted_away_score,
                }
            )
            for i, row in enumerate(matrix):
                for j, probability in enumerate(row):
                    cell_rows.append(
                        {
                            "model_run_id": run_id,
                            "match_id": fx.id,
                            "home_goals": i,
                            "away_goals": j,
                            "probability": probability,
                        }
                    )
            table.append((fx.match_date, fx.home_name, fx.away_name, pred))
        store_predictions(session, prediction_rows)
        if cell_rows:
            session.execute(insert(ScorelineProbability), cell_rows)
        session.commit()

    print(f"\nDixon-Coles forecasts (rho={rho:.3f}) — sample fixtures:\n")
    print(f"{'home':<16} {'away':<16}   {'Hwin':>5} {'Draw':>5} {'Awin':>5}   top score")
    print("-" * 70)
    marquee = {
        "Spain",
        "Argentina",
        "France",
        "England",
        "Brazil",
        "Portugal",
        "Germany",
        "Netherlands",
    }
    for _date, home_name, away_name, pred in table:
        if home_name in marquee or away_name in marquee:
            print(
                f"{home_name[:16]:<16} {away_name[:16]:<16}   "
                f"{pred.p_home_win * 100:>4.0f}% {pred.p_draw * 100:>4.0f}% "
                f"{pred.p_away_win * 100:>4.0f}%   "
                f"{pred.predicted_home_score}-{pred.predicted_away_score}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
