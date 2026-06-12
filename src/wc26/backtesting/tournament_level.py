"""Tournament-level backtesting: sanity check of the propagation engine (Phase 11, addendum §3).

NEVER a model-selection criterion: with four usable World Cups the sample size is ~4, so these
numbers can only flag gross propagation bugs, not rank models (BACKTESTING_STRATEGY.md §1, §4).
The primary metric is the RPS of each team's ordinal stage distribution (how far the team got),
averaged per tournament; uncertainty uses a block bootstrap that resamples whole tournaments,
because matches within a tournament are not independent. The engine is also compared against a
``format_uniform`` reference (every team advances with the format's base rates) and judged on
whether real champions were among the reasonable candidates - not on "calling" them.

Everything here is pure (no DB): the script feeds it played matches and simulated probabilities.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from wc26.simulation.structure32 import STAGES_32, WorldCupEdition

# Teams reaching each stage of the 32-team format (group, R16, QF, SF, final, champion).
TEAMS_PER_STAGE_32: list[int] = [32, 16, 8, 4, 2, 1]


@dataclass(frozen=True)
class PlayedMatch:
    """One played match inside an edition's window, by canonical team name."""

    match_date: date
    home: str
    away: str
    home_score: int
    away_score: int


def validate_groups_against_matches(
    edition: WorldCupEdition, matches: Sequence[PlayedMatch]
) -> None:
    """Cross-check the hardcoded groups against the ingested data (no fabricated structure).

    Each team's first three matches of the edition must be exactly against its three group
    mates. A mismatch means the hardcoded edition data and the database disagree, and the
    backtest must not run on a wrong tournament structure.
    """
    group_mates: dict[str, set[str]] = {}
    for teams in edition.groups.values():
        for team in teams:
            group_mates[team] = set(teams) - {team}

    seen = {t for m in matches for t in (m.home, m.away)}
    expected = set(group_mates)
    if seen != expected:
        raise ValueError(
            f"WC {edition.year}: teams in data do not match the edition's 32 teams; "
            f"missing={sorted(expected - seen)} unexpected={sorted(seen - expected)}"
        )

    opponents: dict[str, list[str]] = defaultdict(list)
    for m in sorted(matches, key=lambda m: m.match_date):
        opponents[m.home].append(m.away)
        opponents[m.away].append(m.home)
    for team, mates in group_mates.items():
        first_three = set(opponents[team][:3])
        if first_three != mates:
            raise ValueError(
                f"WC {edition.year}: group of '{team}' disagrees with the data "
                f"(expected opponents {sorted(mates)}, found {sorted(first_three)})"
            )


def infer_deepest_stages(
    edition: WorldCupEdition, matches: Sequence[PlayedMatch]
) -> dict[str, str]:
    """Derive each team's actual deepest stage from its match count (32-team format).

    3 matches = out in groups, 4 = round of 16, 5 = quarterfinal; all four semifinalists play
    7 (semifinal + final or third-place match), so the finalists are identified as the two
    teams of the edition's last match. Drawn knockout matches are recorded with their 120'
    score in the source data, so the champion comes from the edition record and is asserted
    to be one of the finalists.
    """
    counts = Counter(t for m in matches for t in (m.home, m.away))
    distribution = Counter(counts.values())
    if distribution.get(3, 0) != 16 or distribution.get(4, 0) != 8 or distribution.get(5, 0) != 4:
        raise ValueError(
            f"WC {edition.year}: unexpected match-count distribution {dict(distribution)}; "
            "expected 16 teams with 3, 8 with 4, 4 with 5 and 4 semifinalists"
        )

    last_date = max(m.match_date for m in matches)
    finals = [m for m in matches if m.match_date == last_date]
    if len(finals) != 1:
        raise ValueError(
            f"WC {edition.year}: expected exactly one match on the last day, found {len(finals)}"
        )
    final = finals[0]
    finalists = {final.home, final.away}
    if edition.champion not in finalists:
        raise ValueError(
            f"WC {edition.year}: recorded champion '{edition.champion}' is not one of the "
            f"finalists found in the data {sorted(finalists)}"
        )

    stages: dict[str, str] = {}
    for team, n in counts.items():
        if n == 3:
            stages[team] = "group"
        elif n == 4:
            stages[team] = "round_of_16"
        elif n == 5:
            stages[team] = "quarterfinal"
        elif team in finalists:
            stages[team] = "champion" if team == edition.champion else "final"
        else:
            stages[team] = "semifinal"
    return stages


def stage_rps(
    cumulative: Mapping[str, float], actual_stage: str, stages: Sequence[str] = STAGES_32
) -> float:
    """RPS of one team's ordinal stage distribution against its actual deepest stage.

    ``cumulative`` holds P(reach >= stage); the implied CDF of "deepest stage reached" at
    stage i is 1 - P(reach stage i+1). Lower is better; a perfect point forecast scores 0.
    """
    k = len(stages)
    actual_index = stages.index(actual_stage)
    total = 0.0
    for i in range(k - 1):
        cdf_pred = 1.0 - cumulative[stages[i + 1]]
        cdf_obs = 1.0 if actual_index <= i else 0.0
        total += (cdf_pred - cdf_obs) ** 2
    return total / (k - 1)


def format_uniform_cumulative(
    teams_per_stage: Sequence[int] = TEAMS_PER_STAGE_32, stages: Sequence[str] = STAGES_32
) -> dict[str, float]:
    """No-skill reference: every team reaches each stage with the format's base rate."""
    n_teams = teams_per_stage[0]
    return {stage: teams_per_stage[i] / n_teams for i, stage in enumerate(stages)}


def mean_stage_rps(
    probabilities: Mapping[str, Mapping[str, float]],
    actual_stages: Mapping[str, str],
    stages: Sequence[str] = STAGES_32,
) -> float:
    """Mean stage RPS over all teams of one edition."""
    if set(probabilities) != set(actual_stages):
        raise ValueError("probabilities and actual stages cover different teams")
    return sum(
        stage_rps(probabilities[team], actual_stages[team], stages) for team in probabilities
    ) / len(probabilities)


@dataclass(frozen=True)
class BootstrapSummary:
    """Mean of per-tournament values with a block-bootstrap CI (tournaments are the blocks)."""

    mean: float
    ci_low: float
    ci_high: float
    n_blocks: int


def block_bootstrap_mean(
    per_tournament_values: Sequence[float], n_boot: int = 2000, seed: int = 20260611
) -> BootstrapSummary:
    """Resample whole tournaments with replacement (matches within one are correlated)."""
    values = np.asarray(per_tournament_values, dtype=float)
    n = len(values)
    if n == 0:
        return BootstrapSummary(0.0, 0.0, 0.0, 0)
    rng = np.random.default_rng(seed)
    means = np.array([values[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    return BootstrapSummary(
        mean=float(values.mean()),
        ci_low=float(np.percentile(means, 2.5)),
        ci_high=float(np.percentile(means, 97.5)),
        n_blocks=n,
    )


@dataclass(frozen=True)
class ChampionAssessment:
    """Where the real champion sat in the engine's pre-tournament title odds."""

    champion: str
    probability: float
    rank: int  # 1 = the engine's top candidate
    n_teams: int


def assess_champion(
    probabilities: Mapping[str, Mapping[str, float]], champion: str
) -> ChampionAssessment:
    """Rank the real champion by predicted P(champion) (ties broken by name, deterministic)."""
    ordered = sorted(probabilities.items(), key=lambda kv: (-kv[1]["champion"], kv[0]))
    rank = next(i for i, (team, _) in enumerate(ordered, start=1) if team == champion)
    return ChampionAssessment(
        champion=champion,
        probability=probabilities[champion]["champion"],
        rank=rank,
        n_teams=len(ordered),
    )
