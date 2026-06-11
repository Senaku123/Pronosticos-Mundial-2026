"""Rule-based mapping of raw tournament labels to clean categories (addendum §11).

Categories: world_cup, continental_cup, qualifier, nations_league, friendly, other.
The importance weights are a STARTING HYPOTHESIS to be validated by backtesting, never final
(see docs/METHODOLOGY_ADDENDUM.md §11 and docs/BACKTESTING_STRATEGY.md).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from wc26.database.models import Tournament, TournamentMapping

MAPPING_VERSION = "v1"
MAPPING_SOURCE = "rule_based"

# (match_importance_weight, is_official) per category. Weights are hypotheses, not final.
CATEGORY_DEFAULTS: dict[str, tuple[float, bool]] = {
    "world_cup": (1.0, True),
    "continental_cup": (0.85, True),
    "nations_league": (0.75, True),
    "qualifier": (0.70, True),
    "other": (0.50, True),
    "friendly": (0.30, False),
}

# Main continental championships (lowercased substrings). Qualifiers are filtered out first.
_CONTINENTAL_KEYS = (
    "uefa euro",
    "copa américa",
    "copa america",
    "african cup of nations",
    "africa cup of nations",
    "afc asian cup",
    "gold cup",
    "concacaf championship",
    "oceania nations cup",
)


def classify_tournament(name: str) -> str:
    """Classify a raw tournament label into one of the six canonical categories."""
    n = name.strip().lower()
    if "friendly" in n:
        return "friendly"
    if "qualification" in n or "qualifier" in n or "qualifying" in n:
        return "qualifier"
    if "nations league" in n:
        return "nations_league"
    if "fifa world cup" in n:  # qualifiers were already routed above
        return "world_cup"
    if any(key in n for key in _CONTINENTAL_KEYS):
        return "continental_cup"
    return "other"


def seed_tournament_mapping(session: Session) -> int:
    """Upsert a mapping row for every tournament currently in the database. Returns count."""
    names = list(session.execute(select(Tournament.name)).scalars().all())
    for name in names:
        category = classify_tournament(name)
        weight, is_official = CATEGORY_DEFAULTS[category]
        scope = "global" if category == "world_cup" else None
        session.execute(
            pg_insert(TournamentMapping)
            .values(
                raw_tournament=name,
                tournament_category=category,
                match_importance_weight=weight,
                confederation_scope=scope,
                is_official=is_official,
                source=MAPPING_SOURCE,
                mapping_version=MAPPING_VERSION,
            )
            .on_conflict_do_nothing(constraint="uq_tournament_mapping_raw")
        )
    session.flush()
    return len(names)


def find_unmapped_tournaments(session: Session) -> list[str]:
    """Return tournament names present in `tournaments` but missing from `tournament_mapping`."""
    mapped = select(TournamentMapping.raw_tournament)
    rows = session.execute(select(Tournament.name).where(Tournament.name.not_in(mapped))).scalars()
    return list(rows.all())
