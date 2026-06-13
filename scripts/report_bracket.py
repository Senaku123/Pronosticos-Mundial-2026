"""Ad-hoc report: full 2026 bracket (modal path) + 50k stage probabilities + drivers.

Reads the official frozen engine ('wc2026' run: rho + Platt + as-of Elos at the 2026-06-11
cutoff) and:
  1. Pulls the 50,000-simulation stage-probability matrix for all 48 teams (the real product).
  2. Builds ONE concrete "most-likely path" bracket analytically from the calibrated engine:
     group standings by expected points, best-8 thirds, knockout advance probabilities
     (90' + extra time + 50/50 penalties), advancing the favourite each tie.

This bracket is illustrative (its joint probability is tiny); the probability tables are the
forecast. Pure read of the DB + deterministic engine math; no RNG, no writes.
"""

from __future__ import annotations

import datetime as dt
import itertools

from sqlalchemy import select

from wc26.database.base import get_session_factory
from wc26.database.models import SimulationResult, Team, TournamentSimulation
from wc26.models.baselines import elo_to_lambdas, most_likely_score, wdl_from_matrix
from wc26.models.calibration import calibrate_matrix
from wc26.models.dixon_coles import dixon_coles_matrix
from wc26.models.engine_config import engine_from_config_json, load_team_elos
from wc26.simulation.groups import orient_for_host
from wc26.simulation.structure import (
    FINAL,
    GROUPS_2026,
    HOSTS_2026,
    QUARTERFINALS,
    R32_MATCHES,
    ROUND_OF_16,
    SEMIFINALS,
)
from wc26.simulation.tournament import _slot_team, assign_thirds

AS_OF = dt.date(2026, 6, 11)
EXTRA_TIME_FRACTION = 1.0 / 3.0


def cal_matrix(elo_home, elo_away, neutral, config, calibrator):
    lh, la = elo_to_lambdas(elo_home, elo_away, neutral, config.base)
    m = dixon_coles_matrix(lh, la, config.rho, config.base.max_goals)
    return calibrate_matrix(m, calibrator)


def match_wdl_score(elo_home, elo_away, neutral, config, calibrator):
    m = cal_matrix(elo_home, elo_away, neutral, config, calibrator)
    ph, pd, pa = wdl_from_matrix(m)
    hs, as_ = most_likely_score(m)
    return ph, pd, pa, hs, as_


def knockout_advance_prob(elo_home, elo_away, config, calibrator):
    """Analytic P(home advances) at a neutral knockout: 90' + ET + 50/50 penalties."""
    m = cal_matrix(elo_home, elo_away, True, config, calibrator)
    ph90, pd90, pa90 = wdl_from_matrix(m)
    hs, as_ = most_likely_score(m)
    # Extra time: reduced-rate Dixon-Coles, NO calibration (matches knockout.py).
    lh, la = elo_to_lambdas(elo_home, elo_away, True, config.base)
    et = dixon_coles_matrix(
        lh * EXTRA_TIME_FRACTION, la * EXTRA_TIME_FRACTION, config.rho, config.base.max_goals
    )
    eth, etd, eta = wdl_from_matrix(et)
    p_home = ph90 + pd90 * (eth + 0.5 * etd)
    return p_home, (ph90, pd90, pa90), (hs, as_)


def main() -> int:
    sf = get_session_factory()
    with sf() as session:
        cfg_json = session.execute(
            select(TournamentSimulation.config_json).where(TournamentSimulation.run_id == "wc2026")
        ).scalar_one()
        config, calibrator = engine_from_config_json(cfg_json)

        # 50k stage probabilities per team.
        sim_id, n_sims = session.execute(
            select(TournamentSimulation.id, TournamentSimulation.n_simulations).where(
                TournamentSimulation.run_id == "wc2026"
            )
        ).one()
        rows = session.execute(
            select(Team.canonical_name, SimulationResult.stage, SimulationResult.probability)
            .join(Team, Team.id == SimulationResult.team_id)
            .where(SimulationResult.tournament_simulation_id == sim_id)
        ).all()
        probs: dict[str, dict[str, float]] = {}
        for name, stage, p in rows:
            probs.setdefault(name, {})[stage] = p

        teams = [t for g in GROUPS_2026.values() for t in g]
        elos = load_team_elos(session, teams, AS_OF)

    print(f"### ENGINE  rho={config.rho:.4f}  n_sims={n_sims}  as_of={AS_OF}")
    print(f"### PLATT  {calibrator.to_dict()}")

    # ---- ELO table ----
    print("\n### ELO (as-of 2026-06-11)")
    for t, e in sorted(elos.items(), key=lambda kv: kv[1], reverse=True):
        print(f"{t:<24}{e:7.1f}")

    # ---- GROUP STAGE: concrete standings + scorelines ----
    print("\n### GROUP STAGE")
    winners: dict[str, str] = {}
    runners_up: dict[str, str] = {}
    thirds: list[tuple[str, str, float, float, float]] = []  # group, team, points, gd, elo
    for letter, group in GROUPS_2026.items():
        exp_pts = {t: 0.0 for t in group}
        exp_gd = {t: 0.0 for t in group}
        matches = []
        for a, b in itertools.combinations(group, 2):
            home, away, neutral = orient_for_host(a, b, HOSTS_2026)
            ph, pd, pa, hs, as_ = match_wdl_score(
                elos[home], elos[away], neutral, config, calibrator
            )
            exp_pts[home] += 3 * ph + pd
            exp_pts[away] += 3 * pa + pd
            # expected goal diff from the calibrated matrix means
            m = cal_matrix(elos[home], elos[away], neutral, config, calibrator)
            egh = sum(i * sum(row) for i, row in enumerate(m))
            ega = sum(j * m[i][j] for i in range(len(m)) for j in range(len(m)))
            exp_gd[home] += egh - ega
            exp_gd[away] += ega - egh
            matches.append((home, away, ph, pd, pa, hs, as_))
        order = sorted(group, key=lambda t: (exp_pts[t], exp_gd[t], elos[t]), reverse=True)
        winners[letter] = order[0]
        runners_up[letter] = order[1]
        thirds.append((letter, order[2], exp_pts[order[2]], exp_gd[order[2]], elos[order[2]]))
        host = next((t for t in group if t in HOSTS_2026), None)
        print(f"\nGroup {letter}{'  (host: ' + host + ')' if host else ''}")
        for pos, t in enumerate(order, 1):
            adv = probs.get(t, {}).get("round_of_32", 0.0)
            print(
                f"  {pos}. {t:<22} xPts={exp_pts[t]:4.2f}  xGD={exp_gd[t]:+5.2f}  "
                f"Elo={elos[t]:6.1f}  P(advance,50k)={adv * 100:4.1f}%"
            )
        for home, away, ph, pd, pa, hs, as_ in matches:
            print(
                f"     {home:<20} {hs}-{as_} {away:<20}  "
                f"[{ph * 100:2.0f}/{pd * 100:2.0f}/{pa * 100:2.0f}]"
            )

    # ---- BEST 8 THIRDS ----
    thirds.sort(key=lambda x: (x[2], x[3], x[4]), reverse=True)
    best8 = thirds[:8]
    third_by_group = {letter: team for letter, team, *_ in best8}
    print("\n### BEST THIRDS (top 8 advance)")
    for i, (letter, team, pts, _gd, elo) in enumerate(thirds, 1):
        mark = "QUALIFIES" if i <= 8 else "OUT"
        print(f"  {i:2}. {team:<22} (Grp {letter})  xPts={pts:4.2f}  Elo={elo:6.1f}  {mark}")

    third_assignment = assign_thirds(set(third_by_group))

    # ---- KNOCKOUTS: greedy favourite path ----
    print("\n### KNOCKOUT BRACKET (most-likely path: favourite advances each tie)")
    winner_of: dict[int, str] = {}

    def play(home: str, away: str, match_no: int, label: str):
        p_home, (ph, pd, pa), (hs, as_) = knockout_advance_prob(
            elos[home], elos[away], config, calibrator
        )
        adv = home if p_home >= 0.5 else away
        padv = max(p_home, 1 - p_home)
        winner_of[match_no] = adv
        print(
            f"  [{label} M{match_no}] {home:<20} vs {away:<20}  "
            f"90'[{ph * 100:2.0f}/{pd * 100:2.0f}/{pa * 100:2.0f}] ML {hs}-{as_}  "
            f"-> {adv:<20} (advance {padv * 100:4.1f}%)"
        )

    print("\n-- Round of 32 --")
    for match_no, home_slot, away_slot in R32_MATCHES:
        args = (match_no, winners, runners_up, third_by_group, third_assignment)
        home = _slot_team(home_slot, *args)
        away = _slot_team(away_slot, *args)
        play(home, away, match_no, "R32")

    for _stage, matches, lbl in (
        ("round_of_16", ROUND_OF_16, "R16"),
        ("quarterfinal", QUARTERFINALS, "QF"),
        ("semifinal", SEMIFINALS, "SF"),
        ("final", FINAL, "FINAL"),
    ):
        print(f"\n-- {lbl} --")
        for match_no, sh, sa in matches:
            play(winner_of[sh], winner_of[sa], match_no, lbl)

    champion = winner_of[FINAL[0][0]]
    print(f"\n### MODAL-PATH CHAMPION: {champion}")

    # ---- 50k PROBABILITY TABLE (the real forecast) ----
    print("\n### 50k STAGE PROBABILITIES (top 24 by champion)")
    header_stages = ["round_of_32", "round_of_16", "quarterfinal", "semifinal", "final", "champion"]
    print(f"{'team':<22}{'R32':>7}{'R16':>7}{'QF':>7}{'SF':>7}{'Final':>7}{'Champ':>8}")
    for t, sp in sorted(probs.items(), key=lambda kv: kv[1].get("champion", 0), reverse=True)[:24]:
        print(
            f"{t:<22}"
            + "".join(f"{sp.get(s, 0) * 100:6.1f}%" for s in header_stages[:-1])
            + f"{sp.get('champion', 0) * 100:7.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
