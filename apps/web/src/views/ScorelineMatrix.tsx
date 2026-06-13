import { useState } from 'react'
import { api } from '../api/client'
import type { ScorelineMatrixResponse } from '../api/types'
import { Card, ErrorBanner } from '../components/common'
import { heat, pct } from '../format'

export function ScorelineMatrix() {
  const [home, setHome] = useState('Spain')
  const [away, setAway] = useState('Argentina')
  const [neutral, setNeutral] = useState(true)
  const [maxGoals, setMaxGoals] = useState(5)
  const [data, setData] = useState<ScorelineMatrixResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    api
      .scorelineMatrix(home, away, neutral, maxGoals)
      .then(setData)
      .catch((err) => {
        setError(err)
        setData(null)
      })
      .finally(() => setLoading(false))
  }

  const peak = data ? Math.max(...data.matrix.flat()) : 0

  return (
    <Card title="Matriz de marcador">
      <form className="form" onSubmit={submit}>
        <label>
          Local
          <input value={home} onChange={(e) => setHome(e.target.value)} />
        </label>
        <label>
          Visitante
          <input value={away} onChange={(e) => setAway(e.target.value)} />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={neutral} onChange={(e) => setNeutral(e.target.checked)} />
          Sede neutral
        </label>
        <label>
          Máx. goles
          <input
            type="number"
            min={1}
            max={10}
            value={maxGoals}
            onChange={(e) => setMaxGoals(Number(e.target.value))}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Calculando…' : 'Calcular'}
        </button>
      </form>

      {error != null && <ErrorBanner error={error} />}

      {data && (
        <div className="result">
          <div className="muted small">
            Filas = goles {data.home_team} · columnas = goles {data.away_team}. Color ∝ probabilidad.
          </div>
          <table className="matrix">
            <thead>
              <tr>
                <th />
                {data.matrix[0].map((_, j) => (
                  <th key={j} className="num">
                    {j}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.matrix.map((row, i) => (
                <tr key={i}>
                  <th className="num">{i}</th>
                  {row.map((p, j) => (
                    <td
                      key={j}
                      className="num cell"
                      style={{ background: heat(p, peak) }}
                      title={`${i}-${j}: ${pct(p, 2)}`}
                    >
                      {(p * 100).toFixed(1)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <div className="stat-row">
            <Marginal label={`${data.home_team} gana`} value={pct(data.p_home_win)} />
            <Marginal label="Empate" value={pct(data.p_draw)} />
            <Marginal label={`${data.away_team} gana`} value={pct(data.p_away_win)} />
          </div>
          <p className="muted small">
            W/D/L sumado de la matriz <strong>completa</strong> (0–10), no de la vista recortada.
            Masa fuera del recorte mostrado: {pct(data.truncated_mass, 2)} · motor{' '}
            <code>{data.engine.run_id}</code>, fuerza as-of {data.as_of}.
          </p>
        </div>
      )}
    </Card>
  )
}

function Marginal({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label muted small">{label}</div>
    </div>
  )
}
