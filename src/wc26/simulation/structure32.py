"""Historical 32-team World Cup structure (2010-2022) for tournament-level backtesting.

Eight groups of four; the top two of each group advance to a fixed Round-of-16 bracket. The
pairing template below (1A v 2B, 1C v 2D, ... and the QF/SF tree) is constant across the four
editions with available data (2010, 2014, 2018, 2022) and was verified against each edition's
actual bracket. Group compositions are well-established historical facts and are additionally
CROSS-VALIDATED against the ingested ``matches`` table before any backtest runs (no fabricated
data: a mismatch raises instead of silently simulating a wrong tournament).

The champion is stored per edition because ``results.csv`` records drawn knockout matches with
their 120' score (e.g. the 2022 final), so the shootout winner is not derivable from scores
alone; the stored champion is asserted to be one of the two actual finalists found in the data.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# Stages from shallowest to deepest in the 32-team format (16 teams reach the round of 16).
STAGES_32: list[str] = [
    "group",
    "round_of_16",
    "quarterfinal",
    "semifinal",
    "final",
    "champion",
]

# Round of 16: (match_no, (rank, group), (rank, group)) with rank "W" (winner) or "RU" (runner-up).
# FIFA numbering 49-56; the template is identical in 2010/2014/2018/2022.
R16_MATCHES_32: list[tuple[int, tuple[str, str], tuple[str, str]]] = [
    (49, ("W", "A"), ("RU", "B")),
    (50, ("W", "C"), ("RU", "D")),
    (51, ("W", "D"), ("RU", "C")),
    (52, ("W", "B"), ("RU", "A")),
    (53, ("W", "E"), ("RU", "F")),
    (54, ("W", "G"), ("RU", "H")),
    (55, ("W", "F"), ("RU", "E")),
    (56, ("W", "H"), ("RU", "G")),
]

# Knockout tree: each round is (match_no, source_home_match, source_away_match).
QUARTERFINALS_32: list[tuple[int, int, int]] = [
    (57, 49, 50),
    (58, 53, 54),
    (59, 51, 52),
    (60, 55, 56),
]
SEMIFINALS_32: list[tuple[int, int, int]] = [(61, 57, 58), (62, 59, 60)]
FINAL_32: list[tuple[int, int, int]] = [(64, 61, 62)]


@dataclass(frozen=True)
class WorldCupEdition:
    """One historical edition: cutoff, structure and the facts needed to score the backtest."""

    year: int
    start_date: dt.date  # first match day == strict cutoff for training/ratings
    end_date: dt.date  # last match day (window for collecting the edition's matches)
    hosts: frozenset[str]
    groups: dict[str, list[str]]
    champion: str  # asserted against the finalists found in the database


WC_EDITIONS: list[WorldCupEdition] = [
    WorldCupEdition(
        year=2010,
        start_date=dt.date(2010, 6, 11),
        end_date=dt.date(2010, 7, 11),
        hosts=frozenset({"South Africa"}),
        groups={
            "A": ["South Africa", "Mexico", "Uruguay", "France"],
            "B": ["Argentina", "Nigeria", "South Korea", "Greece"],
            "C": ["England", "United States", "Algeria", "Slovenia"],
            "D": ["Germany", "Australia", "Serbia", "Ghana"],
            "E": ["Netherlands", "Denmark", "Japan", "Cameroon"],
            "F": ["Italy", "Paraguay", "New Zealand", "Slovakia"],
            "G": ["Brazil", "North Korea", "Ivory Coast", "Portugal"],
            "H": ["Spain", "Switzerland", "Honduras", "Chile"],
        },
        champion="Spain",
    ),
    WorldCupEdition(
        year=2014,
        start_date=dt.date(2014, 6, 12),
        end_date=dt.date(2014, 7, 13),
        hosts=frozenset({"Brazil"}),
        groups={
            "A": ["Brazil", "Croatia", "Mexico", "Cameroon"],
            "B": ["Spain", "Netherlands", "Chile", "Australia"],
            "C": ["Colombia", "Greece", "Ivory Coast", "Japan"],
            "D": ["Uruguay", "Costa Rica", "England", "Italy"],
            "E": ["Switzerland", "Ecuador", "France", "Honduras"],
            "F": ["Argentina", "Bosnia and Herzegovina", "Iran", "Nigeria"],
            "G": ["Germany", "Portugal", "Ghana", "United States"],
            "H": ["Belgium", "Algeria", "Russia", "South Korea"],
        },
        champion="Germany",
    ),
    WorldCupEdition(
        year=2018,
        start_date=dt.date(2018, 6, 14),
        end_date=dt.date(2018, 7, 15),
        hosts=frozenset({"Russia"}),
        groups={
            "A": ["Russia", "Saudi Arabia", "Egypt", "Uruguay"],
            "B": ["Portugal", "Spain", "Morocco", "Iran"],
            "C": ["France", "Australia", "Peru", "Denmark"],
            "D": ["Argentina", "Iceland", "Croatia", "Nigeria"],
            "E": ["Brazil", "Switzerland", "Costa Rica", "Serbia"],
            "F": ["Germany", "Mexico", "Sweden", "South Korea"],
            "G": ["Belgium", "Panama", "Tunisia", "England"],
            "H": ["Poland", "Senegal", "Colombia", "Japan"],
        },
        champion="France",
    ),
    WorldCupEdition(
        year=2022,
        start_date=dt.date(2022, 11, 20),
        end_date=dt.date(2022, 12, 18),
        hosts=frozenset({"Qatar"}),
        groups={
            "A": ["Qatar", "Ecuador", "Senegal", "Netherlands"],
            "B": ["England", "Iran", "United States", "Wales"],
            "C": ["Argentina", "Saudi Arabia", "Mexico", "Poland"],
            "D": ["France", "Australia", "Denmark", "Tunisia"],
            "E": ["Spain", "Costa Rica", "Germany", "Japan"],
            "F": ["Belgium", "Canada", "Morocco", "Croatia"],
            "G": ["Brazil", "Serbia", "Switzerland", "Cameroon"],
            "H": ["Portugal", "Ghana", "Uruguay", "South Korea"],
        },
        champion="Argentina",
    ),
]
