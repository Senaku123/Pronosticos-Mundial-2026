import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { HealthResponse } from './api/types'
import { MatchPredictor } from './views/MatchPredictor'
import { Probabilities } from './views/Probabilities'
import { ScorelineMatrix } from './views/ScorelineMatrix'

type Tab = 'probabilities' | 'match' | 'matrix'

const TABS: { key: Tab; label: string }[] = [
  { key: 'probabilities', label: 'Probabilidades' },
  { key: 'match', label: 'Predicción de partido' },
  { key: 'matrix', label: 'Matriz de marcador' },
]

export function App() {
  const [tab, setTab] = useState<Tab>('probabilities')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [down, setDown] = useState(false)

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h)
        setDown(false)
      })
      .catch(() => setDown(true))
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">⚽</span>
          <div>
            <h1>Mundial 2026 — Motor de Pronóstico</h1>
            <p className="muted small">
              Dixon-Coles calibrado · simulación Monte Carlo · sin data leakage
            </p>
          </div>
        </div>
        <HealthPill health={health} down={down} />
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={t.key === tab ? 'tab tab-on' : 'tab'}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {tab === 'probabilities' && <Probabilities />}
        {tab === 'match' && <MatchPredictor />}
        {tab === 'matrix' && <ScorelineMatrix />}
      </main>

      <footer className="footer muted small">
        Comunicación honesta de incertidumbre: toda probabilidad es <strong>calibrada</strong>{' '}
        (Platt, validada out-of-time) y, cuando proviene del simulador, lleva su banda de error
        Monte Carlo. El formato de 48 equipos no tiene análogo histórico: el backtest valida el motor
        de propagación, no este cuadro concreto. No es asesoramiento de apuestas.
      </footer>
    </div>
  )
}

function HealthPill({ health, down }: { health: HealthResponse | null; down: boolean }) {
  if (down) return <span className="pill pill-bad">API sin conexión</span>
  if (!health) return <span className="pill">conectando…</span>
  const ok = health.status === 'ok' && health.official_run != null
  return (
    <span className={ok ? 'pill pill-ok' : 'pill pill-warn'} title={`db: ${health.database}`}>
      {ok ? `motor ${health.official_run}` : `estado: ${health.status}`}
    </span>
  )
}
