import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PredictMatchResponse } from '../api/types'
import { Card, ErrorBanner } from '../components/common'
import { pct } from '../format'

export function MatchPredictor() {
  const [teams, setTeams] = useState<string[]>([])
  const [home, setHome] = useState('Spain')
  const [away, setAway] = useState('Argentina')
  const [neutral, setNeutral] = useState(true)
  const [result, setResult] = useState<PredictMatchResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api
      .teams()
      .then((d) => setTeams(d.teams.map((t) => t.canonical_name)))
      .catch(() => setTeams([]))
  }, [])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    api
      .predictMatch({ home_team: home, away_team: away, neutral })
      .then(setResult)
      .catch((err) => {
        setError(err)
        setResult(null)
      })
      .finally(() => setLoading(false))
  }

  return (
    <Card title="Predicción de un partido">
      <form className="form" onSubmit={submit}>
        <datalist id="teams">
          {teams.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
        <label>
          Local
          <input list="teams" value={home} onChange={(e) => setHome(e.target.value)} />
        </label>
        <label>
          Visitante
          <input list="teams" value={away} onChange={(e) => setAway(e.target.value)} />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={neutral} onChange={(e) => setNeutral(e.target.checked)} />
          Sede neutral
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Calculando…' : 'Predecir'}
        </button>
      </form>

      {error != null && <ErrorBanner error={error} />}

      {result && (
        <div className="result">
          <div className="wdl-bar" role="img" aria-label="probabilidades W/D/L">
            <div className="wdl-home" style={{ width: pct(result.p_home_win, 1) }}>
              {pct(result.p_home_win, 0)}
            </div>
            <div className="wdl-draw" style={{ width: pct(result.p_draw, 1) }}>
              {pct(result.p_draw, 0)}
            </div>
            <div className="wdl-away" style={{ width: pct(result.p_away_win, 1) }}>
              {pct(result.p_away_win, 0)}
            </div>
          </div>
          <div className="wdl-legend muted small">
            <span>
              {result.home_team} gana · {pct(result.p_home_win)}
            </span>
            <span>Empate · {pct(result.p_draw)}</span>
            <span>
              {result.away_team} gana · {pct(result.p_away_win)}
            </span>
          </div>

          <div className="stat-row">
            <Stat label="Goles esp. local" value={result.expected_goals_home.toFixed(2)} />
            <Stat label="Goles esp. visitante" value={result.expected_goals_away.toFixed(2)} />
            <Stat
              label="Marcador más probable"
              value={`${result.most_likely_score.home_goals}-${result.most_likely_score.away_goals}`}
            />
            <Stat label="Elo local" value={result.elo_home.toFixed(0)} />
            <Stat label="Elo visitante" value={result.elo_away.toFixed(0)} />
          </div>

          <h3 className="sub">Marcadores más probables</h3>
          <ul className="scorelines">
            {result.top_scorelines.map((s) => (
              <li key={`${s.home_goals}-${s.away_goals}`}>
                <span className="score">
                  {s.home_goals}-{s.away_goals}
                </span>
                <span className="muted">{pct(s.probability)}</span>
              </li>
            ))}
          </ul>

          <p className="muted small">
            W/D/L derivado de la matriz Dixon-Coles <strong>calibrada</strong> (única fuente de
            verdad) · motor <code>{result.engine.run_id}</code>, ρ = {result.engine.rho.toFixed(4)},{' '}
            {result.engine.calibration} · fuerza as-of {result.as_of}.
          </p>
        </div>
      )}
    </Card>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label muted small">{label}</div>
    </div>
  )
}
