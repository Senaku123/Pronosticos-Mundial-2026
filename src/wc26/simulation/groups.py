"""Group-stage simulation with the verified FIFA 2026 tie-breaker cascade (addendum §7).

Cascade applied (Article 13): points -> head-to-head (points, GD, GF among the tied teams) ->
overall GD -> overall GF -> FIFA ranking. Two documented substitutions for V1: the conduct/
fair-play criterion is skipped (no card data), and the FIFA-ranking criterion is approximated by
internal Elo (we do not ingest the FIFA ranking). Both are noted as limitations.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from wc26.models.calibration import PlattCalibrator
from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.match_sampler import sample_match


@dataclass
class TeamStanding:
    """Accumulated group results for one team."""

    team: str
    elo: float
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


def _apply(standing: TeamStanding, scored: int, conceded: int) -> None:
    standing.goals_for += scored
    standing.goals_against += conceded
    standing.points += 3 if scored > conceded else (1 if scored == conceded else 0)


def _h2h_table(
    tied: list[str], head_to_head: dict[tuple[str, str], tuple[int, int]]
) -> dict[str, tuple[int, int, int]]:
    """Mini-table (points, GD, GF) restricted to the matches among the given teams."""
    mini: dict[str, list[int]] = {t: [0, 0, 0] for t in tied}  # points, gf, ga
    for a, b in itertools.combinations(tied, 2):
        a_goals, b_goals = (
            head_to_head[(a, b)] if (a, b) in head_to_head else head_to_head[(b, a)][::-1]
        )
        mini[a][0] += 3 if a_goals > b_goals else (1 if a_goals == b_goals else 0)
        mini[b][0] += 3 if b_goals > a_goals else (1 if b_goals == a_goals else 0)
        mini[a][1] += a_goals
        mini[a][2] += b_goals
        mini[b][1] += b_goals
        mini[b][2] += a_goals
    return {t: (mini[t][0], mini[t][1] - mini[t][2], mini[t][1]) for t in tied}


def _break_ties(
    tied: list[str],
    standings: dict[str, TeamStanding],
    head_to_head: dict[tuple[str, str], tuple[int, int]],
) -> list[str]:
    """Order teams equal on points per FIFA 2026 Article 13 (addendum §7).

    Step 1: head-to-head mini-table (points, GD, GF) among the tied teams. Step 2: any strict
    subset still tied on those criteria gets the head-to-head RE-APPLIED among themselves only
    (recursion). Only when the whole set stays tied do the overall criteria apply:
    overall GD -> overall GF -> Elo (our documented proxy for the FIFA-ranking criterion).
    """
    if len(tied) == 1:
        return tied
    h2h = _h2h_table(tied, head_to_head)
    ordered = sorted(tied, key=lambda t: h2h[t], reverse=True)

    result: list[str] = []
    for _, grp in itertools.groupby(ordered, key=lambda t: h2h[t]):
        subset = list(grp)
        if len(subset) == 1:
            result.extend(subset)
        elif len(subset) < len(tied):
            # Step 2: re-apply head-to-head restricted to the still-tied subset.
            result.extend(_break_ties(subset, standings, head_to_head))
        else:
            # Whole set tied on head-to-head -> overall criteria.
            result.extend(
                sorted(
                    subset,
                    key=lambda t: (
                        standings[t].goal_difference,
                        standings[t].goals_for,
                        standings[t].elo,
                    ),
                    reverse=True,
                )
            )
    return result


def rank_group(
    standings: dict[str, TeamStanding],
    head_to_head: dict[tuple[str, str], tuple[int, int]],
) -> list[str]:
    """Return team names ordered 1st..last applying the full cascade."""
    by_points = sorted(standings, key=lambda t: standings[t].points, reverse=True)
    ranked: list[str] = []
    for _, group in itertools.groupby(by_points, key=lambda t: standings[t].points):
        tied = list(group)
        ranked.extend(tied if len(tied) == 1 else _break_ties(tied, standings, head_to_head))
    return ranked


def orient_for_host(home: str, away: str, hosts: frozenset[str]) -> tuple[str, str, bool]:
    """Return (home, away, neutral): a host team plays at home, everything else is neutral."""
    if away in hosts and home not in hosts:
        home, away = away, home
    return home, away, home not in hosts


def simulate_group(
    team_elos: dict[str, float],
    config: DixonColesConfig,
    rng: np.random.Generator,
    hosts: frozenset[str] = frozenset(),
    known_scores: Mapping[frozenset[str], Mapping[str, int]] | None = None,
    calibrator: PlattCalibrator | None = None,
) -> list[TeamStanding]:
    """Simulate a round-robin group once; return standings ordered 1st..last.

    Group matches are neutral except for teams in ``hosts`` (Mexico/USA/Canada play their whole
    group stage in their own country), which receive the home advantage the model was fit with.
    Pairings present in ``known_scores`` (real results, Phase 12 re-simulation) are held fixed
    instead of sampled; goals are labeled by team so orientation cannot flip them.
    """
    standings = {team: TeamStanding(team, elo) for team, elo in team_elos.items()}
    head_to_head: dict[tuple[str, str], tuple[int, int]] = {}
    for first, second in itertools.combinations(team_elos, 2):
        home, away, neutral = orient_for_host(first, second, hosts)
        known = known_scores.get(frozenset((home, away))) if known_scores else None
        if known is not None:
            home_goals, away_goals = known[home], known[away]
        else:
            home_goals, away_goals = sample_match(
                team_elos[home], team_elos[away], neutral, config, rng, calibrator
            )
        _apply(standings[home], home_goals, away_goals)
        _apply(standings[away], away_goals, home_goals)
        head_to_head[(home, away)] = (home_goals, away_goals)
    return [standings[t] for t in rank_group(standings, head_to_head)]
