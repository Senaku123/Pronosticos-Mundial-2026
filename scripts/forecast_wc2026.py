"""First glimpse: forecast the upcoming 2026 World Cup fixtures with the simple_poisson baseline.

Usage:
    uv run python scripts/forecast_wc2026.py

For each not-yet-played FIFA World Cup fixture, computes each team's Elo as-of the match date and
predicts W/D/L plus the most-likely scoreline. Stores the predictions and prints a table.

NOTE: these are BASELINE forecasts (Elo -> Poisson) with un-tuned hypothesis constants, shown only
to get an early look at the data. The calibrated engine and its evaluation come in Phases 7-8.
"""

from __future__ import annotations

import platform
import subprocess
import sys

from sqlalchemy import select
from sqlalchemy.orm import aliased
from tqdm import tqdm

from wc26.database.base import get_session_factory
from wc26.database.models import Match, Team, Tournament
from wc26.features.cutoff import get_rating_as_of
from wc26.models.baselines import simple_poisson
from wc26.models.predict import reset_model_run, store_predictions


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def main(argv: list[str]) -> int:
    home = aliased(Team)
    away = aliased(Team)
    session_factory = get_session_factory()
    with session_factory() as session:
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
            run_id="simple_poisson_wc2026",
            model_name="simple_poisson",
            git_sha=_git_sha(),
            python_version=platform.python_version(),
        )

        rows: list[dict[str, object]] = []
        table: list[tuple] = []
        for fx in tqdm(fixtures, desc="forecast WC2026", unit="match"):
            elo_home = get_rating_as_of(session, fx.home_team_id, fx.match_date)
            elo_away = get_rating_as_of(session, fx.away_team_id, fx.match_date)
            p = simple_poisson(elo_home, elo_away, fx.neutral)
            rows.append(
                {
                    "model_run_id": run_id,
                    "match_id": fx.id,
                    "p_home_win": p.p_home_win,
                    "p_draw": p.p_draw,
                    "p_away_win": p.p_away_win,
                    "expected_goals_home": p.expected_goals_home,
                    "expected_goals_away": p.expected_goals_away,
                    "predicted_home_score": p.predicted_home_score,
                    "predicted_away_score": p.predicted_away_score,
                }
            )
            table.append((fx.match_date, fx.home_name, fx.away_name, p))
        store_predictions(session, rows)
        session.commit()

    print(
        f"\n2026 World Cup — first-glimpse forecasts "
        f"(simple_poisson baseline): {len(table)} fixtures\n"
    )
    print(f"{'date':<11} {'home':<22} {'away':<22}   {'Hwin':>5} {'Draw':>5} {'Awin':>5}   score")
    print("-" * 88)
    for match_date, home_name, away_name, p in table:
        print(
            f"{match_date.isoformat():<11} {home_name[:22]:<22} {away_name[:22]:<22}   "
            f"{p.p_home_win * 100:>4.0f}% {p.p_draw * 100:>4.0f}% {p.p_away_win * 100:>4.0f}%   "
            f"{p.predicted_home_score}-{p.predicted_away_score}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
