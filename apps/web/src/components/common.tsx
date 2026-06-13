import type { ReactNode } from 'react'
import { ApiError } from '../api/client'

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="card">
      {title && <h2 className="card-title">{title}</h2>}
      {children}
    </section>
  )
}

export function ErrorBanner({ error }: { error: unknown }) {
  const isApi = error instanceof ApiError
  const status = isApi ? (error as ApiError).status : undefined
  const message = error instanceof Error ? error.message : String(error)
  const hint =
    status === 503
      ? 'El motor congelado no está disponible: corré la simulación oficial (scripts/run_2026_simulation.py) y reintentá.'
      : status === 0
        ? '¿Está corriendo la API en http://127.0.0.1:8000? (uvicorn wc26_api.main:app)'
        : null
  return (
    <div className="error">
      <strong>Error{status ? ` ${status}` : ''}:</strong> {message}
      {hint && <div className="error-hint">{hint}</div>}
    </div>
  )
}

export function Loading({ what }: { what: string }) {
  return <div className="loading">Cargando {what}…</div>
}
