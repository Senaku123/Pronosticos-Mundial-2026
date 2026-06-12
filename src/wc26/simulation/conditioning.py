"""Known real results to condition a mid-tournament re-simulation on (Phase 12).

Once the tournament is underway, re-simulating "the remaining rounds" means fixing what already
happened and sampling only the rest (strict publication cutoff: only results known at publish
time may be fixed, BACKTESTING_STRATEGY.md §7). Pairs are keyed as unordered ``frozenset`` and
goals are labeled BY TEAM, so home/away orientation can never flip a real result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KnownResults:
    """Real results to hold fixed: group scorelines, knockout advancers, real R32 pairings."""

    # Group stage: pair -> {team_name: goals}. Each group pairing plays exactly once.
    group_scores: Mapping[frozenset[str], Mapping[str, int]] = field(default_factory=dict)
    # Knockout: pair -> the team that advanced (however the tie was decided).
    knockout_winners: Mapping[frozenset[str], str] = field(default_factory=dict)
    # The real Round-of-32 pairings once FIFA's bracket is locked. Our third-place slotting is
    # NOT the official Annex C table (documented pending item), so conditioned re-simulations
    # must take the real pairings as given or real R32 results could silently never match.
    r32_pairings: frozenset[frozenset[str]] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.group_scores) or bool(self.knockout_winners) or bool(self.r32_pairings)
