"""Official 2026 World Cup structure: groups and the knockout bracket (verified).

Groups A-L from the December 2025 draw (+ March 2026 play-offs). Bracket from the FIFA
"Regulations for the FIFA World Cup 26" / Wikipedia "2026 FIFA World Cup knockout stage":
the 16 Round-of-32 matches (73-88) and the R16/QF/SF/Final tree are fixed and encoded here.

The exact slotting of the 8 best thirds is FIFA's Annex C (a 495-row lookup table, not a formula).
We do NOT have that table transcribed, so ``assign_thirds`` (in tournament.py) uses a
constraint-respecting assignment: each third goes to a slot whose 5-group set contains its group
(which also guarantees no same-group rematch). The exact Annex C ordering is a documented pending
item (addendum §6). Team names must match ``teams.canonical_name`` in the database.
"""

from __future__ import annotations

import datetime as dt

# Official 2026 calendar facts (FIFA match schedule). TOURNAMENT_START doubles as the strict
# training cutoff (mirrors WorldCupEdition.start_date in structure32.py). The Round-of-32 window
# identifies real R32 fixtures in the data (no stage column exists), and the third-place date
# matters because semifinal LOSERS reappear there - it must never decide a drawn tie's winner.
TOURNAMENT_START: dt.date = dt.date(2026, 6, 11)
R32_FIRST_DAY: dt.date = dt.date(2026, 6, 28)
R32_LAST_DAY: dt.date = dt.date(2026, 7, 3)
THIRD_PLACE_DATE: dt.date = dt.date(2026, 7, 18)

# Co-hosts: they play their entire group stage in their own country (home advantage applies).
# Knockout venues are simulated as neutral for everyone (documented V1 simplification).
HOSTS_2026: frozenset[str] = frozenset({"Mexico", "United States", "Canada"})

# Group letter -> the four teams (canonical names).
GROUPS_2026: dict[str, list[str]] = {
    "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# A bracket slot is one of:
#   ("W", group)   -> group winner
#   ("RU", group)  -> group runner-up
#   ("3RD", frozenset(groups))  -> best third from one of those groups
Slot = tuple[str, object]

# Round of 32: (match_no, home_slot, away_slot).
R32_MATCHES: list[tuple[int, Slot, Slot]] = [
    (73, ("RU", "A"), ("RU", "B")),
    (74, ("W", "E"), ("3RD", frozenset("ABCDF"))),
    (75, ("W", "F"), ("RU", "C")),
    (76, ("W", "C"), ("RU", "F")),
    (77, ("W", "I"), ("3RD", frozenset("CDFGH"))),
    (78, ("RU", "E"), ("RU", "I")),
    (79, ("W", "A"), ("3RD", frozenset("CEFHI"))),
    (80, ("W", "L"), ("3RD", frozenset("EHIJK"))),
    (81, ("W", "D"), ("3RD", frozenset("BEFIJ"))),
    (82, ("W", "G"), ("3RD", frozenset("AEHIJ"))),
    (83, ("RU", "K"), ("RU", "L")),
    (84, ("W", "H"), ("RU", "J")),
    (85, ("W", "B"), ("3RD", frozenset("EFGIJ"))),
    (86, ("W", "J"), ("RU", "H")),
    (87, ("W", "K"), ("3RD", frozenset("DEIJL"))),
    (88, ("RU", "D"), ("RU", "G")),
]

# The 8 third-place slots: (match_no, allowed groups). Used by assign_thirds (mirrors R32_MATCHES).
THIRD_SLOTS: list[tuple[int, frozenset[str]]] = [
    (74, frozenset("ABCDF")),
    (77, frozenset("CDFGH")),
    (79, frozenset("CEFHI")),
    (80, frozenset("EHIJK")),
    (81, frozenset("BEFIJ")),
    (82, frozenset("AEHIJ")),
    (85, frozenset("EFGIJ")),
    (87, frozenset("DEIJL")),
]

# Knockout tree: each round is (match_no, source_home_match, source_away_match).
ROUND_OF_16: list[tuple[int, int, int]] = [
    (89, 74, 77),
    (90, 73, 75),
    (91, 76, 78),
    (92, 79, 80),
    (93, 83, 84),
    (94, 81, 82),
    (95, 86, 88),
    (96, 85, 87),
]
QUARTERFINALS: list[tuple[int, int, int]] = [
    (97, 89, 90),
    (98, 93, 94),
    (99, 91, 92),
    (100, 95, 96),
]
SEMIFINALS: list[tuple[int, int, int]] = [(101, 97, 98), (102, 99, 100)]
FINAL: list[tuple[int, int, int]] = [(104, 101, 102)]

# Stages from shallowest to deepest, used for the cumulative stage-probability matrix.
STAGES: list[str] = [
    "group",
    "round_of_32",
    "round_of_16",
    "quarterfinal",
    "semifinal",
    "final",
    "champion",
]
