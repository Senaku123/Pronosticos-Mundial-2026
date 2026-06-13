import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Stage, StageProbability, TournamentProbabilitiesResponse } from '../api/types'
import { Card, ErrorBanner, Loading } from '../components/common'
import { pct, pctWithBand } from '../format'

const STAGES: { key: Stage; label: string }[] = [
  { key: 'round_of_32', label: 'R32' },
  { key: 'round_of_16', label: 'Octavos' },
  { key: 'quarterfinal', label: 'Cuartos' },
  { key: 'semifinal', label: 'Semis' },
  { key: 'final', label: 'Final' },
  { key: 'champion', label: 'Campeón' },
]

export function Probabilities() {
  const [stage, setStage] = useState<Stage>('champion')
  const [data, setData] = useState<TournamentProbabilitiesResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    api
      .tournamentProbabilities(stage, 24)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [stage])

  return (
    <Card title="Probabilidades por selección (Monte Carlo)">
      <div className="toolbar">
        <span className="muted">Ordenar por:</span>
        {STAGES.map((s) => (
          <button
            key={s.key}
            className={s.key === stage ? 'chip chip-on' : 'chip'}
            onClick={() => setStage(s.key)}
          >
            {s.label}
          </button>
        ))}
      </div>

      {loading && <Loading what="probabilidades" />}
      {error != null && <ErrorBanner error={error} />}

      {data && !loading && (
        <>
          <p className="muted small">
            Corrida <code>{data.run.run_id}</code> · {data.run.n_simulations.toLocaleString()}{' '}
            simulaciones · corte {data.run.cutoff_date ?? '—'}. Banda = error Monte Carlo 95% sobre
            N simulaciones (no es la incertidumbre real del evento). Probabilidades calibradas
            (Platt, ECE ≈ 0.021).
          </p>
          <table className="grid">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Selección</th>
                {STAGES.map((s) => (
                  <th key={s.key} className="num">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.standings.map((row: StageProbability, i: number) => (
                <tr key={row.team}>
                  <td className="num muted">{i + 1}</td>
                  <td>{row.team}</td>
                  {STAGES.map((s) => {
                    const value = row[s.key]
                    const highlight = s.key === stage
                    return (
                      <td key={s.key} className={highlight ? 'num strong' : 'num'}>
                        {highlight && value != null
                          ? pctWithBand(value, data.run.n_simulations)
                          : pct(value)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Card>
  )
}
