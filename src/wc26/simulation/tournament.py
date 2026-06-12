"""Full 2026 World Cup Monte Carlo simulation -> per-team stage probabilities (addendum §6, §9).

One simulation: play the 12 groups, rank the 12 thirds and take the best 8, slot them into the
Round of 32 (constraint-respecting; see structure.py), then play the fixed knockout bracket
resolving every tie (90'/ET/penalties). Aggregating many simulations gives the stage-probability
matrix (P(Round of 16) ... P(champion)) per team. Only aggregates are returned (no raw match rows).
"""

from __future__ import annotations

import numpy as np

from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.groups import TeamStanding, simulate_group
from wc26.simulation.knockout import HOME, resolve_knockout
from wc26.simulation.structure import (
    FINAL,
    GROUPS_2026,
    QUARTERFINALS,
    R32_MATCHES,
    ROUND_OF_16,
    SEMIFINALS,
    STAGES,
    THIRD_SLOTS,
)

DEFAULT_ELO = 1500.0


def assign_thirds(qualifying_groups: set[str]) -> dict[int, str]:
    """Match the 8 qualifying third-place groups to the 8 third slots (bipartite matching).

    Each slot accepts only its 5-group set, which also guarantees no same-group rematch. Returns
    {slot_match_no: group}. If a perfect matching is not found (should not happen for valid
    combinations), remaining slots/groups are filled greedily so a simulation never crashes.
    """
    groups = sorted(qualifying_groups)
    group_to_slot_index: dict[str, int] = {}

    def augment(slot_index: int, seen: set[str]) -> bool:
        for g in groups:
            if g in THIRD_SLOTS[slot_index][1] and g not in seen:
                seen.add(g)
                if g not in group_to_slot_index or augment(group_to_slot_index[g], seen):
                    group_to_slot_index[g] = slot_index
                    return True
        return False

    for i in range(len(THIRD_SLOTS)):
        augment(i, set())

    assignment = {THIRD_SLOTS[idx][0]: g for g, idx in group_to_slot_index.items()}
    if len(assignment) < len(THIRD_SLOTS):  # greedy fallback for any unmatched slot/group
        used_groups = set(assignment.values())
        free_groups = [g for g in groups if g not in used_groups]
        for match_no, _allowed in THIRD_SLOTS:
            if match_no not in assignment and free_groups:
                assignment[match_no] = free_groups.pop()
    return assignment


def _slot_team(
    slot: tuple[str, object],
    match_no: int,
    winners: dict[str, str],
    runners_up: dict[str, str],
    third_by_group: dict[str, str],
    third_assignment: dict[int, str],
) -> str:
    kind = slot[0]
    if kind == "W":
        return winners[str(slot[1])]
    if kind == "RU":
        return runners_up[str(slot[1])]
    return third_by_group[third_assignment[match_no]]


def simulate_tournament(
    team_elos: dict[str, float], config: DixonColesConfig, rng: np.random.Generator
) -> dict[str, str]:
    """Simulate the whole tournament once; return each team's deepest stage reached."""
    reached: dict[str, str] = {team: "group" for group in GROUPS_2026.values() for team in group}

    winners: dict[str, str] = {}
    runners_up: dict[str, str] = {}
    thirds: list[tuple[str, TeamStanding]] = []
    for letter, teams in GROUPS_2026.items():
        elos = {t: team_elos.get(t, DEFAULT_ELO) for t in teams}
        standings = simulate_group(elos, config, rng)
        winners[letter] = standings[0].team
        runners_up[letter] = standings[1].team
        thirds.append((letter, standings[2]))

    thirds.sort(
        key=lambda x: (x[1].points, x[1].goal_difference, x[1].goals_for, x[1].elo), reverse=True
    )
    best_thirds = thirds[:8]
    third_by_group = {letter: standing.team for letter, standing in best_thirds}
    third_assignment = assign_thirds(set(third_by_group))

    for team in (*winners.values(), *runners_up.values(), *third_by_group.values()):
        reached[team] = "round_of_32"

    winner_of: dict[int, str] = {}
    for match_no, home_slot, away_slot in R32_MATCHES:
        home = _slot_team(
            home_slot, match_no, winners, runners_up, third_by_group, third_assignment
        )
        away = _slot_team(
            away_slot, match_no, winners, runners_up, third_by_group, third_assignment
        )
        result = resolve_knockout(
            team_elos.get(home, DEFAULT_ELO), team_elos.get(away, DEFAULT_ELO), True, config, rng
        )
        winner_of[match_no] = home if result == HOME else away

    for stage, matches in (
        ("round_of_16", ROUND_OF_16),
        ("quarterfinal", QUARTERFINALS),
        ("semifinal", SEMIFINALS),
        ("final", FINAL),
    ):
        for match_no, source_home, source_away in matches:
            home = winner_of[source_home]
            away = winner_of[source_away]
            reached[home] = stage
            reached[away] = stage
            result = resolve_knockout(
                team_elos.get(home, DEFAULT_ELO),
                team_elos.get(away, DEFAULT_ELO),
                True,
                config,
                rng,
            )
            winner_of[match_no] = home if result == HOME else away

    reached[winner_of[FINAL[0][0]]] = "champion"
    return reached


def run_monte_carlo(
    team_elos: dict[str, float],
    config: DixonColesConfig,
    n_simulations: int,
    seed: int,
) -> dict[str, dict[str, float]]:
    """Run ``n_simulations`` and return cumulative stage probabilities per team."""
    rng = np.random.default_rng(seed)
    counts = {team: dict.fromkeys(STAGES, 0) for team in team_elos}
    for _ in range(n_simulations):
        reached = simulate_tournament(team_elos, config, rng)
        for team, stage in reached.items():
            if team not in counts:
                continue
            for s in STAGES[: STAGES.index(stage) + 1]:
                counts[team][s] += 1
    return {team: {s: counts[team][s] / n_simulations for s in STAGES} for team in team_elos}
