"""Match-level backtest + go/no-go gate (Phase 8, addendum §3, §4).

Usage:
    uv run python scripts/backtest_match_level.py

Evaluates every stored model on the out-of-time test block (matches >= 2018), reports log loss,
Brier, RPS, ECE and accuracy, skill scores vs the Elo-only baseline, a paired bootstrap of the
champion vs the baseline, and the GO/NO-GO verdict. Stores backtest_runs + backtest_metrics.

NOTE: this evaluates already-stored predictions on a held-out block. BOTH Dixon-Coles parameters
(rho and the Platt calibration) were fit only on matches < 2018 (see calibrate_dc.py), so the
test block is genuinely out-of-time. This is a single out-of-time split, not a full per-cutoff
walk-forward (documented refinement for later).
"""

from __future__ import annotations

import datetime as dt
import platform
import subprocess
import sys

from sqlalchemy import delete, insert, select
from tqdm import tqdm

from wc26.backtesting.match_level import (
    PairedTest,
    _per_match_log_loss,
    evaluate_model,
    paired_bootstrap,
    skill_score,
)
from wc26.database.base import get_session_factory
from wc26.database.models import BacktestMetric, BacktestRun, Match, MatchPrediction, ModelRun

TEST_FROM = dt.date(2018, 1, 1)
MODELS = ["naive_favorite", "elo_only", "simple_poisson", "dixon_coles", "dixon_coles_calibrated"]
BASELINE = "elo_only"
CHAMPION = "dixon_coles_calibrated"
ECE_ACCEPTABLE = 0.05


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def _outcome(home_score: int, away_score: int) -> int:
    return 0 if home_score > away_score else (1 if home_score == away_score else 2)


def _load(session, run_id: str):
    rows = session.execute(
        select(
            MatchPrediction.match_id,
            MatchPrediction.p_home_win,
            MatchPrediction.p_draw,
            MatchPrediction.p_away_win,
            Match.home_score,
            Match.away_score,
        )
        .join(ModelRun, ModelRun.id == MatchPrediction.model_run_id)
        .join(Match, Match.id == MatchPrediction.match_id)
        .where(ModelRun.run_id == run_id, Match.match_date >= TEST_FROM)
        .order_by(MatchPrediction.match_id)
    ).all()
    probs = [(r.p_home_win, r.p_draw, r.p_away_win) for r in rows]
    outcomes = [_outcome(r.home_score, r.away_score) for r in rows]
    match_ids = [r.match_id for r in rows]
    return probs, outcomes, match_ids


def main(argv: list[str]) -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        loaded = {m: _load(session, m) for m in tqdm(MODELS, desc="loading models", unit="model")}
        # Paired metrics require every model to cover EXACTLY the same matches, in order.
        reference_ids = loaded[BASELINE][2]
        for name, (_, _, ids) in loaded.items():
            if ids != reference_ids:
                raise ValueError(f"model '{name}' covers different matches than '{BASELINE}'")
        data = {m: (probs, outcomes) for m, (probs, outcomes, _) in loaded.items()}
        evals = {m: evaluate_model(m, *data[m]) for m in MODELS}

        base = evals[BASELINE]
        champ = evals[CHAMPION]
        paired: PairedTest = paired_bootstrap(
            _per_match_log_loss(*data[CHAMPION]), _per_match_log_loss(*data[BASELINE])
        )

        beats_log_loss = champ.log_loss < base.log_loss
        beats_brier = champ.brier < base.brier
        calibration_ok = champ.ece <= ECE_ACCEPTABLE
        significant = paired.p_value < 0.05
        go = (beats_log_loss or beats_brier) and calibration_ok and significant

        # Persist the backtest run + metrics.
        session.execute(delete(BacktestRun).where(BacktestRun.run_id == "match_level_v1"))
        session.flush()
        config = f'{{"baseline": "{BASELINE}", "champion": "{CHAMPION}", "go": {str(go).lower()}}}'
        run = BacktestRun(
            run_id="match_level_v1",
            backtest_level="match",
            test_from=TEST_FROM,
            n_matches=base.n,
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=config,
        )
        session.add(run)
        session.flush()
        metric_rows = []
        for name, e in evals.items():
            values = {
                "log_loss": e.log_loss,
                "brier": e.brier,
                "rps": e.rps,
                "ece": e.ece,
                "accuracy": e.accuracy,
                "skill_log_loss_vs_elo": skill_score(e.log_loss, base.log_loss),
                "skill_brier_vs_elo": skill_score(e.brier, base.brier),
            }
            for metric, value in values.items():
                metric_rows.append(
                    {
                        "backtest_run_id": run.id,
                        "model_name": name,
                        "metric": metric,
                        "value": value,
                    }
                )
        session.execute(insert(BacktestMetric), metric_rows)
        session.commit()

    print(f"\nMatch-level backtest (out-of-time, test >= {TEST_FROM}, n={base.n}):\n")
    header = f"{'model':<24}{'logloss':>9}{'brier':>8}{'rps':>8}{'ece':>8}{'acc':>7}{'skill':>8}"
    print(header)
    print("-" * len(header))
    for name in MODELS:
        e = evals[name]
        print(
            f"{name:<24}{e.log_loss:>9.4f}{e.brier:>8.4f}{e.rps:>8.4f}"
            f"{e.ece:>8.4f}{e.accuracy:>7.3f}{skill_score(e.log_loss, base.log_loss):>8.3f}"
        )

    print(
        f"\nPaired bootstrap  {CHAMPION} vs {BASELINE} (per-match log loss):\n"
        f"  mean diff = {paired.mean_difference:+.5f}  "
        f"95% CI [{paired.ci_low:+.5f}, {paired.ci_high:+.5f}]  p={paired.p_value:.4f}"
    )
    print("\n" + "=" * 60)
    print(f"  GO/NO-GO VERDICT: {'>>> GO <<<' if go else '>>> NO-GO <<<'}")
    print(
        f"    beats Elo-only in log loss: {beats_log_loss} | brier: {beats_brier}\n"
        f"    calibration acceptable (ECE<= {ECE_ACCEPTABLE}): {calibration_ok} "
        f"(ECE={champ.ece:.4f})\n"
        f"    improvement significant (p<0.05): {significant} (p={paired.p_value:.4f})"
    )
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
