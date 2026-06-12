"""Live forecasting and scoring during the 2026 World Cup (Phase 12, addendum §1, §4).

The anti-hype loop (BACKTESTING_STRATEGY.md §7): PUBLISH frozen probabilities before matches
(engine + Elo-only baseline, same cutoff), SCORE them after results against the baseline, and
RE-SIMULATE the remaining rounds holding real results fixed. Strict cutoff: a publication dated
``as_of`` uses only information strictly before that date (as-of Elo lookups guarantee it), so
even a match-day publication never sees its own matches. Everything is registered in
``model_runs`` / ``backtest_runs`` (level 'live') for traceability.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, delete, insert, or_, select
from sqlalchemy.orm import Session, aliased

from wc26.backtesting.match_level import (
    ModelEvaluation,
    PairedTest,
    evaluate_model,
    evaluation_metric_rows,
    paired_bootstrap,
    per_match_log_loss,
)
from wc26.database.models import (
    BacktestMetric,
    BacktestRun,
    Match,
    MatchPrediction,
    ModelRun,
    Team,
    Tournament,
    TournamentMapping,
)
from wc26.features.cutoff import get_rating_as_of
from wc26.models.baselines import elo_only, most_likely_score, wdl_from_matrix
from wc26.models.calibration import (
    PlattCalibrator,
    ProbTriplet,
    calibrate_matrix,
    outcome_index,
)
from wc26.models.dixon_coles import DixonColesConfig, predict_dixon_coles
from wc26.models.engine_config import engine_config_json
from wc26.models.predict import reset_model_run, store_predictions
from wc26.simulation.conditioning import KnownResults
from wc26.simulation.structure import (
    GROUPS_2026,
    R32_FIRST_DAY,
    R32_LAST_DAY,
    THIRD_PLACE_DATE,
    TOURNAMENT_START,
)

ENGINE_MODEL = "dixon_coles_calibrated"
BASELINE_MODEL = "elo_only"
ENGINE_RUN_PREFIX = "live_dc_calibrated_"
BASELINE_RUN_PREFIX = "live_elo_only_"


def monte_carlo_half_width(probability: float, n_simulations: int) -> float:
    """95% Monte Carlo half-width of an aggregated probability (binomial standard error)."""
    if n_simulations <= 0:
        return 0.0
    return 1.96 * math.sqrt(probability * (1.0 - probability) / n_simulations)


def world_cup_matches(
    start: dt.date = TOURNAMENT_START,
    end: dt.date | None = None,
    as_of: dt.date | None = None,
    played: bool | None = None,
) -> Select[Any]:
    """Base select for World Cup matches with team names resolved (one query definition).

    ``end`` is inclusive (an edition's final day belongs to it); ``as_of`` is the strict
    publication cutoff (matches strictly before it). The tournament-level backtest reuses this
    with each historical edition's window so Phase 11 and Phase 12 agree on the match universe.
    """
    home = aliased(Team)
    away = aliased(Team)
    stmt = (
        select(
            Match.id.label("match_id"),
            Match.match_date,
            Match.neutral,
            home.canonical_name.label("home"),
            away.canonical_name.label("away"),
            Match.home_score,
            Match.away_score,
            Match.home_team_id,
            Match.away_team_id,
        )
        .join(Tournament, Tournament.id == Match.tournament_id)
        .join(TournamentMapping, TournamentMapping.raw_tournament == Tournament.name)
        .join(home, home.id == Match.home_team_id)
        .join(away, away.id == Match.away_team_id)
        .where(
            TournamentMapping.tournament_category == "world_cup",
            Match.match_date >= start,
        )
        .order_by(Match.match_date, Match.id)
    )
    if end is not None:
        stmt = stmt.where(Match.match_date <= end)
    if as_of is not None:
        stmt = stmt.where(Match.match_date < as_of)
    if played is True:
        stmt = stmt.where(Match.home_score.is_not(None), Match.away_score.is_not(None))
    if played is False:
        stmt = stmt.where(or_(Match.home_score.is_(None), Match.away_score.is_(None)))
    return stmt


@dataclass(frozen=True)
class PlayedResult:
    """One real tournament result, decoupled from the DB so classification stays pure."""

    match_date: dt.date
    home: str
    away: str
    home_score: int
    away_score: int


def _drawn_knockout_winner(
    row: PlayedResult, index: int, rows: Sequence[PlayedResult]
) -> str | None:
    """Winner of a 120'-drawn knockout tie, only when derivable from later appearances.

    The third-place match must NEVER identify a winner: semifinal LOSERS reappear there, so
    counting it would condition the loser into the final. With it excluded, a later appearance
    is sound for every round; for a drawn semifinal in the bronze-played/final-pending window,
    the team NOT in the bronze is the advancer. Anything else stays underivable (None).
    """
    later = [r for r in rows[index + 1 :] if r.match_date > row.match_date]
    non_bronze = {t for r in later if r.match_date != THIRD_PLACE_DATE for t in (r.home, r.away)}
    advanced = [t for t in (row.home, row.away) if t in non_bronze]
    if len(advanced) == 1:
        return advanced[0]
    if not advanced:
        bronze = {t for r in later if r.match_date == THIRD_PLACE_DATE for t in (r.home, r.away)}
        eliminated = [t for t in (row.home, row.away) if t in bronze]
        if len(eliminated) == 1:
            return row.away if eliminated[0] == row.home else row.home
    return None


def classify_results(rows: Sequence[PlayedResult]) -> tuple[KnownResults, list[str]]:
    """Pure classification of real results into conditioning facts (rows in date order).

    A pair's first meeting inside its own group is a group scoreline; the third-place match is
    skipped entirely (it decides nothing about advancement); anything else is a knockout tie,
    whose winner is the higher score or - for a 120' draw recorded by the source - derived per
    ``_drawn_knockout_winner``. An underivable draw is left to be simulated and reported as a
    warning, never guessed. Played Round-of-32 fixtures also contribute the real pairings that
    lock the third-place slotting (our algorithmic slotting is not FIFA's Annex C).
    """
    group_of = {team: letter for letter, teams in GROUPS_2026.items() for team in teams}
    group_scores: dict[frozenset[str], dict[str, int]] = {}
    knockout_winners: dict[frozenset[str], str] = {}
    r32_pairings: set[frozenset[str]] = set()
    warnings: list[str] = []
    for i, row in enumerate(rows):
        pair = frozenset((row.home, row.away))
        if R32_FIRST_DAY <= row.match_date <= R32_LAST_DAY:
            r32_pairings.add(pair)
        if row.match_date == THIRD_PLACE_DATE:
            continue
        same_group = group_of.get(row.home) is not None and group_of[row.home] == group_of.get(
            row.away
        )
        if same_group and pair not in group_scores:
            group_scores[pair] = {row.home: row.home_score, row.away: row.away_score}
            continue
        if row.home_score != row.away_score:
            winner = row.home if row.home_score > row.away_score else row.away
        else:
            derived = _drawn_knockout_winner(row, i, rows)
            if derived is None:
                warnings.append(
                    f"knockout draw {row.home} {row.home_score}-{row.away_score} {row.away} "
                    f"({row.match_date}): winner unknown from results alone; left simulated"
                )
                continue
            winner = derived
        knockout_winners[pair] = winner
    return KnownResults(group_scores, knockout_winners, frozenset(r32_pairings)), warnings


def load_known_results(session: Session, as_of: dt.date) -> tuple[KnownResults, list[str]]:
    """Real 2026 conditioning facts strictly before ``as_of`` (results) plus locked pairings.

    Scheduled-but-unplayed R32 fixtures already pin the real bracket (the pairing is public the
    moment groups close, so using it is not leakage), and they matter precisely before those
    matches are played.
    """
    played = [
        PlayedResult(r.match_date, r.home, r.away, int(r.home_score), int(r.away_score))
        for r in session.execute(world_cup_matches(as_of=as_of, played=True)).all()
    ]
    known, warnings = classify_results(played)

    scheduled = session.execute(world_cup_matches(start=R32_FIRST_DAY, end=R32_LAST_DAY)).all()
    pairings = set(known.r32_pairings) | {frozenset((r.home, r.away)) for r in scheduled}
    if pairings != set(known.r32_pairings):
        known = KnownResults(known.group_scores, known.knockout_winners, frozenset(pairings))
    return known, warnings


@dataclass(frozen=True)
class PublishedFixture:
    """One frozen pre-match forecast row (for reporting)."""

    match_date: dt.date
    home: str
    away: str
    probs: ProbTriplet
    predicted_score: tuple[int, int]


def publish_match_forecasts(
    session: Session,
    as_of: dt.date,
    config: DixonColesConfig,
    calibrator: PlattCalibrator,
    git_sha: str | None = None,
    python_version: str | None = None,
) -> tuple[list[PublishedFixture], list[str]]:
    """Freeze engine + baseline W/D/L for every upcoming fixture, as two dated model runs.

    Both models use the SAME as-of-``as_of`` Elo (strictly-before lookup), so the published
    engine forecast is always comparable against its baseline. Re-publishing the same day
    overwrites that day's runs (idempotent); each day gets its own frozen run. A fixture
    already in the past with no ingested result is excluded (publishing the past is cheating)
    but reported as a warning - it usually means results are lagging ingestion.
    """
    all_fixtures = session.execute(world_cup_matches(played=False)).all()
    fixtures = [f for f in all_fixtures if f.match_date >= as_of]
    warnings = [
        f"unplayed past fixture {f.match_date} {f.home} vs {f.away}: no result ingested, "
        "excluded from publication (results lagging ingestion?)"
        for f in all_fixtures
        if f.match_date < as_of
    ]

    engine_run = reset_model_run(
        session,
        run_id=f"{ENGINE_RUN_PREFIX}{as_of.isoformat()}",
        model_name=ENGINE_MODEL,
        git_sha=git_sha,
        python_version=python_version,
        cutoff_date=as_of,
        config_json=engine_config_json(config, calibrator, fixtures=len(fixtures)),
    )
    baseline_run = reset_model_run(
        session,
        run_id=f"{BASELINE_RUN_PREFIX}{as_of.isoformat()}",
        model_name=BASELINE_MODEL,
        git_sha=git_sha,
        python_version=python_version,
        cutoff_date=as_of,
        config_json=json.dumps({"fixtures": len(fixtures)}),
    )

    published: list[PublishedFixture] = []
    engine_rows: list[dict[str, object]] = []
    baseline_rows: list[dict[str, object]] = []
    for fx in fixtures:
        elo_home = get_rating_as_of(session, fx.home_team_id, as_of)
        elo_away = get_rating_as_of(session, fx.away_team_id, as_of)

        pred, matrix = predict_dixon_coles(elo_home, elo_away, fx.neutral, config)
        calibrated = calibrate_matrix(matrix, calibrator)
        p_home, p_draw, p_away = wdl_from_matrix(calibrated)
        score = most_likely_score(calibrated)
        engine_rows.append(
            {
                "model_run_id": engine_run,
                "match_id": fx.match_id,
                "p_home_win": p_home,
                "p_draw": p_draw,
                "p_away_win": p_away,
                "expected_goals_home": pred.expected_goals_home,
                "expected_goals_away": pred.expected_goals_away,
                "predicted_home_score": score[0],
                "predicted_away_score": score[1],
            }
        )

        base = elo_only(elo_home, elo_away, fx.neutral)
        baseline_rows.append(
            {
                "model_run_id": baseline_run,
                "match_id": fx.match_id,
                "p_home_win": base.p_home_win,
                "p_draw": base.p_draw,
                "p_away_win": base.p_away_win,
                "expected_goals_home": None,
                "expected_goals_away": None,
                "predicted_home_score": None,
                "predicted_away_score": None,
            }
        )
        published.append(
            PublishedFixture(fx.match_date, fx.home, fx.away, (p_home, p_draw, p_away), score)
        )
    store_predictions(session, engine_rows)
    store_predictions(session, baseline_rows)
    return published, warnings


@dataclass(frozen=True)
class PublishedPrediction:
    """One stored live prediction of one match, from one dated publication."""

    match_id: int
    match_date: dt.date
    publication_date: dt.date
    probs: ProbTriplet
    outcome: int


def operative_forecasts(rows: Iterable[PublishedPrediction]) -> dict[int, PublishedPrediction]:
    """The forecast that counts per match: its latest publication on or before match day.

    A same-day publication is leakage-safe (as-of lookups are strictly-before), but later
    publications would already know the result, so they never score.
    """
    chosen: dict[int, PublishedPrediction] = {}
    for row in rows:
        if row.publication_date > row.match_date:
            continue
        current = chosen.get(row.match_id)
        if current is None or row.publication_date > current.publication_date:
            chosen[row.match_id] = row
    return chosen


@dataclass(frozen=True)
class LiveScoreReport:
    """Scored live forecasts: engine vs baseline on the matches played so far."""

    n_scored: int
    evaluations: dict[str, ModelEvaluation]
    paired: PairedTest


def _load_published(session: Session, run_prefix: str) -> list[PublishedPrediction]:
    rows = session.execute(
        select(
            MatchPrediction.match_id,
            Match.match_date,
            ModelRun.cutoff_date,
            MatchPrediction.p_home_win,
            MatchPrediction.p_draw,
            MatchPrediction.p_away_win,
            Match.home_score,
            Match.away_score,
        )
        .join(ModelRun, ModelRun.id == MatchPrediction.model_run_id)
        .join(Match, Match.id == MatchPrediction.match_id)
        .where(
            ModelRun.run_id.like(f"{run_prefix}%"),
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
        )
    ).all()
    return [
        PublishedPrediction(
            match_id=r.match_id,
            match_date=r.match_date,
            publication_date=r.cutoff_date,
            probs=(r.p_home_win, r.p_draw, r.p_away_win),
            outcome=outcome_index(r.home_score, r.away_score),
        )
        for r in rows
    ]


def score_published_forecasts(
    session: Session,
    as_of: dt.date,
    git_sha: str | None = None,
    python_version: str | None = None,
) -> LiveScoreReport:
    """Score every published forecast whose match has a result; persist a 'live' backtest run.

    With nothing to score yet, nothing is persisted: an empty evaluation would store log_loss
    0.0 rows that read as perfect scores.
    """
    operative = {
        model: operative_forecasts(_load_published(session, prefix))
        for model, prefix in (
            (ENGINE_MODEL, ENGINE_RUN_PREFIX),
            (BASELINE_MODEL, BASELINE_RUN_PREFIX),
        )
    }
    engine_ids = sorted(operative[ENGINE_MODEL])
    baseline_ids = sorted(operative[BASELINE_MODEL])
    if engine_ids != baseline_ids:
        raise ValueError(
            "live publications cover different matches for engine and baseline; "
            "publish always writes both - was a run deleted?"
        )

    data: dict[str, tuple[list[ProbTriplet], list[int]]] = {}
    for model, forecasts in operative.items():
        ordered = [forecasts[match_id] for match_id in engine_ids]
        data[model] = ([f.probs for f in ordered], [f.outcome for f in ordered])

    evaluations = {model: evaluate_model(model, *data[model]) for model in data}
    if not engine_ids:
        return LiveScoreReport(0, evaluations, PairedTest(0.0, 0.0, 0.0, 1.0))
    paired = paired_bootstrap(
        per_match_log_loss(*data[ENGINE_MODEL]), per_match_log_loss(*data[BASELINE_MODEL])
    )

    run_id = f"live_scoring_{as_of.isoformat()}"
    session.execute(delete(BacktestRun).where(BacktestRun.run_id == run_id))
    session.flush()
    run = BacktestRun(
        run_id=run_id,
        backtest_level="live",
        test_from=TOURNAMENT_START,
        n_matches=len(engine_ids),
        git_sha=git_sha,
        python_version=python_version,
        config_json=json.dumps(
            {"engine": ENGINE_MODEL, "baseline": BASELINE_MODEL, "scored_until": as_of.isoformat()}
        ),
    )
    session.add(run)
    session.flush()

    metric_rows = evaluation_metric_rows(run.id, evaluations, BASELINE_MODEL)
    metric_rows.extend(
        {"backtest_run_id": run.id, "model_name": ENGINE_MODEL, "metric": metric, "value": value}
        for metric, value in (
            ("paired_mean_diff_log_loss", paired.mean_difference),
            ("paired_p_value", paired.p_value),
        )
    )
    session.execute(insert(BacktestMetric), metric_rows)
    session.flush()
    return LiveScoreReport(len(engine_ids), evaluations, paired)


def summarize_known(known: KnownResults, warnings: Sequence[str]) -> str:
    """One line for run configs / logs describing what a re-simulation held fixed."""
    return (
        f"{len(known.group_scores)} group results + {len(known.knockout_winners)} knockout "
        f"winners + {len(known.r32_pairings)} R32 pairings fixed; {len(warnings)} undecided"
    )
