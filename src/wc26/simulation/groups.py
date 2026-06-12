"""Group-stage simulation with the verified FIFA 2026 tie-breaker cascade (addendum §7).

Cascade applied (Article 13): points -> head-to-head (points, GD, GF among the tied teams) ->
overall GD -> overall GF -> FIFA ranking. Two documented substitutions for V1: the conduct/
fair-play criterion is skipped (no card data), and the FIFA-ranking criterion is approximated by
internal Elo (we do not ingest the FIFA ranking). Both are noted as limitations.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

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


def _break_ties(
    tied: list[str],
    standings: dict[str, TeamStanding],
    head_to_head: dict[tuple[str, str], tuple[int, int]],
) -> list[str]:
    """Order teams equal on points: head-to-head mini-table, then overall GD/GF, then Elo."""
    mini: dict[str, list[int]] = {t: [0, 0, 0] for t in tied}  # points, gf, ga among tied teams
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

    def key(team: str) -> tuple[int, int, int, int, int, float]:
        h2h_points, h2h_gf, h2h_ga = mini[team]
        s = standings[team]
        return (h2h_points, h2h_gf - h2h_ga, h2h_gf, s.goal_difference, s.goals_for, s.elo)

    return sorted(tied, key=key, reverse=True)


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


def simulate_group(
    team_elos: dict[str, float],
    config: DixonColesConfig,
    rng: np.random.Generator,
    neutral: bool = True,
) -> list[TeamStanding]:
    """Simulate a round-robin group once; return standings ordered 1st..last."""
    standings = {team: TeamStanding(team, elo) for team, elo in team_elos.items()}
    head_to_head: dict[tuple[str, str], tuple[int, int]] = {}
    for home, away in itertools.combinations(team_elos, 2):
        home_goals, away_goals = sample_match(
            team_elos[home], team_elos[away], neutral, config, rng
        )
        _apply(standings[home], home_goals, away_goals)
        _apply(standings[away], away_goals, home_goals)
        head_to_head[(home, away)] = (home_goals, away_goals)
    return [standings[t] for t in rank_group(standings, head_to_head)]
