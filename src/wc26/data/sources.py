"""Canonical registry of V1 data sources (mirrors the data_sources table).

Only verified, V1-eligible national-team sources live here. Club data, betting odds and
StatsBomb are intentionally excluded from V1 (see docs/DATA_SOURCES.md / addendum §14, §15).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    """Provenance + licensing descriptor for an external data source."""

    name: str
    url: str
    license: str
    upstream_source: str | None = None
    upstream_license: str | None = None
    tos_notes: str | None = None


# Match results, 1872-present. CC0; GitHub raw mirror avoids needing a Kaggle account.
MARTJ42_RESULTS = SourceSpec(
    name="martj42_results",
    url="https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
    license="CC0-1.0",
    upstream_source="martj42/international_results (GitHub)",
    upstream_license="CC0-1.0",
    tos_notes="Public domain (CC0). Verified 2026-06-11.",
)

# Structured World Cup data 1930-2026 (incl. 2026). CC0, no attribution required.
OPENFOOTBALL_WORLDCUP = SourceSpec(
    name="openfootball_worldcup",
    url="https://github.com/openfootball/worldcup.json",
    license="CC0-1.0",
    upstream_source="openfootball/worldcup.json (GitHub)",
    upstream_license="CC0-1.0",
    tos_notes="Public domain (CC0). Manual commit updates (~1/day), not live. Verified 2026-06-11.",
)

# Historical team name changes (e.g. West Germany -> Germany). CC0, same dataset as results.
MARTJ42_FORMER_NAMES = SourceSpec(
    name="martj42_former_names",
    url="https://raw.githubusercontent.com/martj42/international_results/master/former_names.csv",
    license="CC0-1.0",
    upstream_source="martj42/international_results (GitHub)",
    upstream_license="CC0-1.0",
    tos_notes="Public domain (CC0). Team name changes. Verified 2026-06-11.",
)

REGISTRY: dict[str, SourceSpec] = {
    spec.name: spec for spec in (MARTJ42_RESULTS, OPENFOOTBALL_WORLDCUP, MARTJ42_FORMER_NAMES)
}
