"""Fit the official engine configuration (Dixon-Coles rho + Platt) strictly before a cutoff.

Shared by the 2026 simulation, the live re-simulation/publication flow and the tournament-level
backtest, so every consumer fits the SAME winning configuration (calibrated Dixon-Coles, Phase 8
go/no-go) the same leakage-safe way: both rho and the Platt layer see only matches strictly
before ``fit_before`` (addendum §1).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session
from tqdm import tqdm

from wc26.database.models import Match, MatchFeature, Team
from wc26.features.cutoff import get_rating_as_of
from wc26.models.baselines import BaselineConfig, elo_to_lambdas
from wc26.models.calibration import PlattCalibrator
from wc26.models.dixon_coles import DixonColesConfig, fit_rho, predict_dixon_coles


def fit_engine(
    session: Session, fit_before: dt.date, progress: bool = True
) -> tuple[DixonColesConfig, PlattCalibrator]:
    """Fit rho and the Platt calibrator on every played match strictly before ``fit_before``."""
    base = BaselineConfig()
    training = session.execute(
        select(
            MatchFeature.elo_home,
            MatchFeature.elo_away,
            MatchFeature.is_neutral,
            Match.home_score,
            Match.away_score,
        )
        .join(Match, Match.id == MatchFeature.match_id)
        .where(Match.match_date < fit_before)
    ).all()
    if not training:
        raise ValueError(f"no played matches before {fit_before}; is match_features seeded?")

    samples = []
    for elo_home, elo_away, neutral, home_score, away_score in training:
        lh, la = elo_to_lambdas(elo_home, elo_away, neutral, base)
        samples.append((lh, la, int(home_score), int(away_score)))
    config = DixonColesConfig(rho=fit_rho(samples))

    probs = []
    outcomes = []
    iterator = tqdm(training, desc=f"Platt fit < {fit_before}", unit="match", disable=not progress)
    for elo_home, elo_away, neutral, home_score, away_score in iterator:
        pred, _ = predict_dixon_coles(elo_home, elo_away, neutral, config)
        probs.append((pred.p_home_win, pred.p_draw, pred.p_away_win))
        outcomes.append(
            0
            if int(home_score) > int(away_score)
            else (1 if int(home_score) == int(away_score) else 2)
        )
    return config, PlattCalibrator.fit(probs, outcomes)


def load_team_elos(session: Session, teams: Iterable[str], as_of: dt.date) -> dict[str, float]:
    """As-of Elo per canonical team name. Unknown names raise (no silent default strength)."""
    requested = list(teams)
    team_ids = {
        name: team_id
        for name, team_id in session.execute(select(Team.canonical_name, Team.id)).all()
    }
    missing = [t for t in requested if t not in team_ids]
    if missing:
        raise ValueError(f"teams not found in the database: {missing}")
    return {t: get_rating_as_of(session, team_ids[t], as_of) for t in requested}
