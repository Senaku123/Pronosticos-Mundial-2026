"""Fit and evaluate a calibration layer on the Dixon-Coles W/D/L (Phase 7b).

Usage:
    uv run python scripts/calibrate_dc.py

Predicts Dixon-Coles W/D/L for every played match, splits TEMPORALLY (train < 2018, test >= 2018),
fits Platt scaling on the train block and measures reliability (log loss, Brier, ECE) on the test
block (out-of-time). Stores raw + calibrated predictions and the reliability curves.

NOTE: rho is fit on all played matches here (a single global parameter); the strict walk-forward
discipline is Phase 8. This step demonstrates and measures the calibration layer out-of-time.
"""

from __future__ import annotations

import datetime as dt
import platform
import subprocess
import sys

from sqlalchemy import delete, insert, select
from tqdm import tqdm

from wc26.database.base import get_session_factory
from wc26.database.models import CalibrationCurve, Match, MatchFeature
from wc26.models.baselines import BaselineConfig, elo_to_lambdas
from wc26.models.calibration import (
    PlattCalibrator,
    brier_score,
    expected_calibration_error,
    log_loss,
    reliability_bins,
)
from wc26.models.dixon_coles import DixonColesConfig, fit_rho, predict_dixon_coles
from wc26.models.predict import reset_model_run, store_predictions

SPLIT_DATE = dt.date(2018, 1, 1)
CLASSES = (("home", 0), ("draw", 1), ("away", 2))


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


def _avg_ece(probs: list[tuple[float, float, float]], outcomes: list[int]) -> float:
    total = 0.0
    for _, c in CLASSES:
        class_probs = [p[c] for p in probs]
        labels = [1 if o == c else 0 for o in outcomes]
        total += expected_calibration_error(class_probs, labels)
    return total / len(CLASSES)


def _prediction_rows(run_id: int, items: list[tuple[int, tuple[float, float, float]]]) -> list:
    return [
        {
            "model_run_id": run_id,
            "match_id": match_id,
            "p_home_win": probs[0],
            "p_draw": probs[1],
            "p_away_win": probs[2],
            "expected_goals_home": None,
            "expected_goals_away": None,
            "predicted_home_score": None,
            "predicted_away_score": None,
        }
        for match_id, probs in items
    ]


def main(argv: list[str]) -> int:
    base = BaselineConfig()
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.execute(
            select(
                MatchFeature.match_id,
                MatchFeature.elo_home,
                MatchFeature.elo_away,
                MatchFeature.is_neutral,
                Match.match_date,
                Match.home_score,
                Match.away_score,
            ).join(Match, Match.id == MatchFeature.match_id)
        ).all()

        samples = []
        for r in rows:
            lh, la = elo_to_lambdas(r.elo_home, r.elo_away, r.is_neutral, base)
            samples.append((lh, la, int(r.home_score), int(r.away_score)))
        rho = fit_rho(samples)
        cfg = DixonColesConfig(rho=rho)
        print(f"[ok] Dixon-Coles rho={rho:.4f}")

        records = []  # (match_id, probs, outcome, date)
        for r in tqdm(rows, desc="Dixon-Coles predict", unit="match"):
            pred, _ = predict_dixon_coles(r.elo_home, r.elo_away, r.is_neutral, cfg)
            records.append(
                (
                    r.match_id,
                    (pred.p_home_win, pred.p_draw, pred.p_away_win),
                    _outcome(int(r.home_score), int(r.away_score)),
                    r.match_date,
                )
            )

        train = [(p, o) for _, p, o, d in records if d < SPLIT_DATE]
        test = [(mid, p, o) for mid, p, o, d in records if d >= SPLIT_DATE]
        calibrator = PlattCalibrator.fit([p for p, _ in train], [o for _, o in train])

        test_probs = [p for _, p, _ in test]
        test_out = [o for _, _, o in test]
        cal_probs = [calibrator.calibrate(*p) for p in test_probs]

        metrics = {
            "log_loss": (log_loss(test_probs, test_out), log_loss(cal_probs, test_out)),
            "brier": (brier_score(test_probs, test_out), brier_score(cal_probs, test_out)),
            "ece": (_avg_ece(test_probs, test_out), _avg_ece(cal_probs, test_out)),
        }

        # Persist raw + calibrated predictions for all matches (Phase 8 input).
        raw_run = reset_model_run(
            session,
            run_id="dixon_coles",
            model_name="dixon_coles",
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=f'{{"rho": {rho:.4f}}}',
        )
        store_predictions(session, _prediction_rows(raw_run, [(m, p) for m, p, _, _ in records]))
        cal_config = f'{{"rho": {rho:.4f}, "calibration": "platt", "split_date": "{SPLIT_DATE}"}}'
        cal_run = reset_model_run(
            session,
            run_id="dixon_coles_calibrated",
            model_name="dixon_coles_calibrated",
            git_sha=_git_sha(),
            python_version=platform.python_version(),
            config_json=cal_config,
        )
        store_predictions(
            session,
            _prediction_rows(cal_run, [(m, calibrator.calibrate(*p)) for m, p, _, _ in records]),
        )

        # Persist reliability curves (test split, raw vs calibrated, per class).
        session.execute(delete(CalibrationCurve).where(CalibrationCurve.model_run_id == cal_run))
        curve_rows = []
        for label, c in CLASSES:
            labels = [1 if o == c else 0 for o in test_out]
            for tag, probs in (("raw", test_probs), ("calibrated", cal_probs)):
                for bin_index, mean_pred, observed, count in reliability_bins(
                    [p[c] for p in probs], labels
                ):
                    curve_rows.append(
                        {
                            "model_run_id": cal_run,
                            "outcome_class": label,
                            "calibration": tag,
                            "split": "test",
                            "bin_index": bin_index,
                            "mean_predicted": mean_pred,
                            "observed_frequency": observed,
                            "sample_count": count,
                        }
                    )
        if curve_rows:
            session.execute(insert(CalibrationCurve), curve_rows)
        session.commit()

    print(f"\nOut-of-time calibration (test >= {SPLIT_DATE}, n={len(test)}):\n")
    print(f"{'metric':<10} {'raw':>10} {'calibrated':>12}")
    print("-" * 34)
    for name, (raw, cal) in metrics.items():
        print(f"{name:<10} {raw:>10.4f} {cal:>12.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
