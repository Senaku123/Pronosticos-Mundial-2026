"""Full 2026 World Cup Monte Carlo simulation -> per-team stage probabilities (addendum §6, §9).

One simulation: play the 12 groups (co-hosts get home advantage; everything else neutral), rank
the 12 thirds and take the best 8, slot them into the Round of 32 (constraint-respecting; see
structure.py), then play the fixed knockout bracket resolving every tie (90'/ET/penalties; all
knockout matches simulated as neutral — documented V1 simplification). Scorelines come from the
Platt-calibrated Dixon-Coles matrix (the configuration that won the Phase 8 go/no-go).
Aggregating many simulations gives the stage-probability matrix per team. Only aggregates are
returned (no raw match rows).
"""

from __future__ import annotations

import numpy as np
from tqdm import tqdm

from wc26.models.calibration import PlattCalibrator
from wc26.models.dixon_coles import DixonColesConfig
from wc26.simulation.conditioning import KnownResults
from wc26.simulation.groups import TeamStanding, simulate_group
from wc26.simulation.knockout import HOME, resolve_knockout
from wc26.simulation.structure import (
    FINAL,
    GROUPS_2026,
    HOSTS_2026,
    QUARTERFINALS,
    R32_MATCHES,
    ROUND_OF_16,
    SEMIFINALS,
    STAGES,
    THIRD_SLOTS,
)


def assign_thirds(
    qualifying_groups: set[str], fixed: dict[int, str] | None = None
) -> dict[int, str]:
    """Match the 8 qualifying third-place groups to the 8 third slots (bipartite matching).

    Each slot accepts only its 5-group set, which also guarantees no same-group rematch. Returns
    {slot_match_no: group}. A perfect matching exists for every valid 8-of-12 combination
    (Hall's condition holds for the official slot sets); if it ever fails, a ValueError is
    raised rather than silently violating the bracket. ``fixed`` pins slots already locked by
    the REAL bracket (from the ingested R32 fixtures); the matching only completes the rest.
    NOTE: without ``fixed`` this is a deterministic, constraint-respecting assignment, NOT
    FIFA's exact Annex C table (documented pending item).
    """
    fixed = fixed or {}
    slot_of_match = {match_no: i for i, (match_no, _) in enumerate(THIRD_SLOTS)}
    for match_no, group in fixed.items():
        if group not in qualifying_groups or group not in THIRD_SLOTS[slot_of_match[match_no]][1]:
            raise ValueError(f"fixed third slot {match_no} <- group {group} is invalid")
    locked_groups = set(fixed.values())
    groups = sorted(qualifying_groups)
    group_to_slot_index: dict[str, int] = {g: slot_of_match[m] for m, g in fixed.items()}
    fixed_slots = set(group_to_slot_index.values())

    def augment(slot_index: int, seen: set[str]) -> bool:
        for g in groups:
            if g in locked_groups or g in seen or g not in THIRD_SLOTS[slot_index][1]:
                continue
            seen.add(g)
            if g not in group_to_slot_index or augment(group_to_slot_index[g], seen):
                group_to_slot_index[g] = slot_index
                return True
        return False

    for i in range(len(THIRD_SLOTS)):
        if i not in fixed_slots:
            augment(i, set())

    if len(group_to_slot_index) < len(THIRD_SLOTS):
        raise ValueError(
            f"no perfect third-place matching for groups {sorted(qualifying_groups)} "
            f"with fixed slots {fixed}; THIRD_SLOTS may have been edited inconsistently"
        )
    return {THIRD_SLOTS[idx][0]: g for g, idx in group_to_slot_index.items()}


# Each third slot's opponent is a fixed group winner; that anchor locates the slot's real pairing.
_THIRD_SLOT_ANCHOR: dict[int, str] = {
    match_no: str(home_slot[1])
    for match_no, home_slot, away_slot in R32_MATCHES
    if away_slot[0] == "3RD"
}


def thirds_from_real_pairings(
    r32_pairings: frozenset[frozenset[str]],
    winners: dict[str, str],
    third_by_group: dict[str, str],
) -> dict[int, str]:
    """Third slots locked by the REAL Round-of-32 pairings (FIFA's Annex C outcome as data).

    Our algorithmic slotting is not the official Annex C table, so once the real bracket is
    locked the real pairings take precedence: for each third slot, its group-winner anchor finds
    the real pairing and the partner is that slot's third. Slots whose anchor has no ingested
    pairing yet are left to the matching; an INCONSISTENT pairing (partner is not a simulated
    third, or from a disallowed group) raises - that means the simulated group outcomes diverge
    from reality and conditioning must not proceed silently.
    """
    group_of_third = {team: group for group, team in third_by_group.items()}
    fixed: dict[int, str] = {}
    for match_no, allowed in THIRD_SLOTS:
        anchor = winners[_THIRD_SLOT_ANCHOR[match_no]]
        partners = [pair - {anchor} for pair in r32_pairings if anchor in pair]
        if not partners:
            continue  # this slot's real fixture is not ingested yet
        if len(partners) > 1:
            raise ValueError(f"team '{anchor}' appears in {len(partners)} real R32 pairings")
        (third,) = partners[0]
        group = group_of_third.get(third)
        if group is None or group not in allowed:
            raise ValueError(
                f"real R32 pairing {anchor} vs {third} (match {match_no}) is inconsistent with "
                "the simulated third-place qualifiers; simulated group outcomes diverge from "
                "reality (tie-break proxy?)"
            )
        fixed[match_no] = group
    return fixed


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
    team_elos: dict[str, float],
    config: DixonColesConfig,
    rng: np.random.Generator,
    calibrator: PlattCalibrator | None = None,
    known: KnownResults | None = None,
    consumed: set[frozenset[str]] | None = None,
) -> dict[str, str]:
    """Simulate the whole tournament once; return each team's deepest stage reached.

    ``known`` (Phase 12 live re-simulation) holds real results fixed: group scorelines are
    replayed exactly, the real R32 pairings lock the third-place slotting, and decided knockout
    pairs advance their real winner; only the remaining matches are sampled. Every fixed
    knockout pair actually applied is recorded into ``consumed`` so the caller can detect real
    results that never matched a simulated pairing (silent bracket divergence is forbidden).
    """
    reached: dict[str, str] = {team: "group" for group in GROUPS_2026.values() for team in group}

    winners: dict[str, str] = {}
    runners_up: dict[str, str] = {}
    thirds: list[tuple[str, TeamStanding]] = []
    for letter, teams in GROUPS_2026.items():
        elos = {t: team_elos[t] for t in teams}
        standings = simulate_group(
            elos,
            config,
            rng,
            hosts=HOSTS_2026,
            known_scores=known.group_scores if known else None,
            calibrator=calibrator,
        )
        winners[letter] = standings[0].team
        runners_up[letter] = standings[1].team
        thirds.append((letter, standings[2]))

    thirds.sort(
        key=lambda x: (x[1].points, x[1].goal_difference, x[1].goals_for, x[1].elo), reverse=True
    )
    best_thirds = thirds[:8]
    third_by_group = {letter: standing.team for letter, standing in best_thirds}
    fixed_thirds = (
        thirds_from_real_pairings(known.r32_pairings, winners, third_by_group)
        if known and known.r32_pairings
        else None
    )
    third_assignment = assign_thirds(set(third_by_group), fixed_thirds)

    for team in (*winners.values(), *runners_up.values(), *third_by_group.values()):
        reached[team] = "round_of_32"

    def knockout_winner(home: str, away: str) -> str:
        if known:
            pair = frozenset((home, away))
            fixed = known.knockout_winners.get(pair)
            if fixed is not None:
                if consumed is not None:
                    consumed.add(pair)
                return fixed
        result = resolve_knockout(team_elos[home], team_elos[away], True, config, rng, calibrator)
        return home if result == HOME else away

    winner_of: dict[int, str] = {}
    for match_no, home_slot, away_slot in R32_MATCHES:
        home = _slot_team(
            home_slot, match_no, winners, runners_up, third_by_group, third_assignment
        )
        away = _slot_team(
            away_slot, match_no, winners, runners_up, third_by_group, third_assignment
        )
        winner_of[match_no] = knockout_winner(home, away)

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
            winner_of[match_no] = knockout_winner(home, away)

    reached[winner_of[FINAL[0][0]]] = "champion"
    return reached


def run_monte_carlo(
    team_elos: dict[str, float],
    config: DixonColesConfig,
    n_simulations: int,
    seed: int,
    calibrator: PlattCalibrator | None = None,
    known: KnownResults | None = None,
    progress: bool = False,
) -> dict[str, dict[str, float]]:
    """Run ``n_simulations`` and return cumulative stage probabilities per team.

    ``team_elos`` must cover all 48 teams in GROUPS_2026 (missing teams raise, instead of
    silently simulating with a default strength and disappearing from the output). If any real
    knockout result in ``known`` never matched a simulated pairing across ALL simulations, a
    ValueError is raised: the conditioned bracket diverged from reality and the aggregates
    would silently ignore a known result.
    """
    expected = {team for group in GROUPS_2026.values() for team in group}
    missing = expected - set(team_elos)
    if missing:
        raise ValueError(f"team_elos is missing tournament teams: {sorted(missing)}")

    rng = np.random.default_rng(seed)
    counts = {team: dict.fromkeys(STAGES, 0) for team in expected}
    consumed: set[frozenset[str]] = set()
    for _ in tqdm(range(n_simulations), desc="Monte Carlo", unit="sim", disable=not progress):
        reached = simulate_tournament(team_elos, config, rng, calibrator, known, consumed)
        for team, stage in reached.items():
            for s in STAGES[: STAGES.index(stage) + 1]:
                counts[team][s] += 1

    if known:
        unconsumed = set(known.knockout_winners) - consumed
        if unconsumed:
            raise ValueError(
                "real knockout results never matched a simulated pairing (bracket divergence; "
                f"are the R32 fixtures fully ingested?): "
                f"{sorted(tuple(sorted(pair)) for pair in unconsumed)}"
            )
    return {team: {s: counts[team][s] / n_simulations for s in STAGES} for team in expected}
