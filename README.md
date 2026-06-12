# World Cup 2026 Forecast Engine

A probabilistic forecasting engine for the 2026 FIFA World Cup. It predicts individual matches and
simulates the full tournament (Monte Carlo) to estimate stage-by-stage qualification and title
probabilities.

This is **not** an "AI predicts the World Cup" gimmick. It is a modular, reproducible, and
explainable system grounded in statistics, careful backtesting, and honest uncertainty reporting.
Every quality claim is measured against baselines; nothing is asserted without evaluation.

> **Status:** Phases 0-12 implemented — data pipeline, anti-leakage Elo, calibrated Dixon-Coles
> (GO gate passed), Monte Carlo simulator (2026 + historical 32-team backtest) and the live
> publish/score flow for the ongoing tournament. Next: FastAPI backend (Phase 13).
> Planning documents live in [`docs/`](docs/) and are written in Spanish (project guidance
> language). All technical identifiers are in English.

## What it produces

- Match-level: `p_team_a_win`, `p_draw`, `p_team_b_win`; expected goals per team; a full scoreline
  probability matrix; most likely scorelines.
- Tournament-level (via Monte Carlo): per-team probabilities for Round of 32, Round of 16,
  Quarterfinal, Semifinal, Final, and Champion.

## Methodological commitments

This project follows a binding methodological addendum
([`docs/METHODOLOGY_ADDENDUM.md`](docs/METHODOLOGY_ADDENDUM.md)). Highlights:

- **No temporal data leakage.** Elo is recomputed internally from raw results with a strict
  `cutoff_date`; external rankings are modeled as bitemporal series; automated tests fail on any
  feature dated after the cutoff.
- **A single source of truth for W/D/L.** Match outcome probabilities are derived by summing zones
  of the Poisson/Dixon-Coles scoreline matrix. Any ML model is a *challenger* only, never a second
  official source.
- **Model selection at the match level**, not by who won a past World Cup (a 4-tournament sample
  cannot select models). Tournament-level backtesting is a sanity check.
- **A quantitative go/no-go gate:** the engine must beat an Elo-only baseline in out-of-time Brier
  Score or Log Loss, with acceptable calibration, before any full frontend or player-aware V2.
- **Realistic 2026 simulation:** official Round of 32 third-place bracket mapping, knockout
  resolution (90' → extra time → penalties), and official group tie-breakers.
- **Mechanized reproducibility:** every run records `git_sha`, `data_hash`, `cutoff_date`,
  `random_seed`, Python version, and lockfile; data sources are pinned to immutable snapshots.

## Versions

- **V1 — National team forecasting engine (current focus).** National teams only. No club data,
  no betting odds, no deep learning.
- **V2 — Player-aware model (future).** Squad/player signals.
- **V3 — Advanced analytics / DL (future, conditional).** Only with sufficient event-level data.

## Tech stack

Python (data, features, modeling, backtesting, simulation) · PostgreSQL (local; DataGrip as client)
· SQLAlchemy + Alembic · pytest · FastAPI (backend, gated) · React + Vite (frontend, optional and
non-blocking) · Jupyter (exploration only).

## Repository layout

```text
apps/      # api (FastAPI), web (React+Vite, optional)
data/      # raw, interim, processed (gitignored; pinned by manifest + hash)
docs/      # planning documents (Spanish)
notebooks/ # exploration only
src/       # data, database, identity, features, models, backtesting, simulation, evaluation, utils
tests/     # unit + sport-logic golden tests
scripts/
```

## Documentation

- [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) — reproducible setup, from zero to loaded data.
- [`docs/PROJECT_BLUEPRINT.md`](docs/PROJECT_BLUEPRINT.md) — core project document (Spanish).
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — modeling methodology and anti-leakage rules.
- [`docs/BACKTESTING_STRATEGY.md`](docs/BACKTESTING_STRATEGY.md) — two-level backtesting + live scoring.
- [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) — candidate data sources and licensing notes.
- [`docs/PHASES.md`](docs/PHASES.md) — phase-by-phase plan.
- [`docs/METHODOLOGY_ADDENDUM.md`](docs/METHODOLOGY_ADDENDUM.md) — binding methodological rules.

## Honest limitations

- The 2026 format (48 teams) has no historical analog, so historical tournament backtests validate
  the propagation engine, not the specific 2026 bracket. Live scoring during the tournament is the
  definitive validation.
- Official 2026 group tie-breakers and the third-place bracket mapping must be verified against the
  official FIFA regulations; unconfirmed details are explicit placeholders. No data is fabricated.

## License

To be defined.
