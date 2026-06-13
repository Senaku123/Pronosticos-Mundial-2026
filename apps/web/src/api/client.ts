// Tiny typed fetch wrapper. In dev, BASE = '/api' is proxied to the FastAPI backend by Vite;
// in production set VITE_API_BASE to the API origin.
import type {
  HealthResponse,
  PredictMatchRequest,
  PredictMatchResponse,
  ScorelineMatrixResponse,
  TeamListResponse,
  TournamentProbabilitiesResponse,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch (err) {
    throw new ApiError(0, `network error: ${(err as Error).message}`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const usp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') usp.set(key, String(value))
  }
  const qs = usp.toString()
  return qs ? `?${qs}` : ''
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  teams: () => request<TeamListResponse>('/teams'),

  tournamentProbabilities: (stage: string, limit = 24) =>
    request<TournamentProbabilitiesResponse>(
      `/tournament-probabilities${query({ stage, limit })}`,
    ),

  predictMatch: (body: PredictMatchRequest) =>
    request<PredictMatchResponse>('/predict-match', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  scorelineMatrix: (home: string, away: string, neutral: boolean, maxGoals: number) =>
    request<ScorelineMatrixResponse>(
      `/scoreline-matrix${query({
        home_team: home,
        away_team: away,
        neutral,
        max_goals: maxGoals,
      })}`,
    ),
}
