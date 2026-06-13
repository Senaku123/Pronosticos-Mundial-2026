// Types mirroring the FastAPI response contracts (apps/api/wc26_api/schemas.py).
// Hand-written for V1; run `npm run gen:types` against a live API to regenerate from OpenAPI.

export interface EngineInfo {
  run_id: string
  model: string
  rho: number
  calibration: string
  cutoff_date: string | null
}

export interface Scoreline {
  home_goals: number
  away_goals: number
  probability: number
}

export interface TeamSummary {
  id: number
  canonical_name: string
  fifa_code: string | null
  confederation: string | null
  elo: number | null
}

export interface TeamListResponse {
  as_of: string | null
  count: number
  teams: TeamSummary[]
}

export interface PredictMatchRequest {
  home_team: string
  away_team: string
  neutral: boolean
  as_of?: string | null
}

export interface PredictMatchResponse {
  home_team: string
  away_team: string
  neutral: boolean
  as_of: string
  elo_home: number
  elo_away: number
  p_home_win: number
  p_draw: number
  p_away_win: number
  expected_goals_home: number
  expected_goals_away: number
  most_likely_score: Scoreline
  top_scorelines: Scoreline[]
  engine: EngineInfo
}

export interface ScorelineMatrixResponse {
  home_team: string
  away_team: string
  neutral: boolean
  as_of: string
  max_goals: number
  p_home_win: number
  p_draw: number
  p_away_win: number
  matrix: number[][]
  truncated_mass: number
  engine: EngineInfo
}

export interface SimulationRunMeta {
  run_id: string
  n_simulations: number
  random_seed: number | null
  cutoff_date: string | null
  git_sha: string | null
  python_version: string | null
  created_at: string | null
}

export type Stage =
  | 'round_of_32'
  | 'round_of_16'
  | 'quarterfinal'
  | 'semifinal'
  | 'final'
  | 'champion'

export interface StageProbability {
  team: string
  round_of_32: number | null
  round_of_16: number | null
  quarterfinal: number | null
  semifinal: number | null
  final: number | null
  champion: number | null
}

export interface TournamentProbabilitiesResponse {
  run: SimulationRunMeta
  stage: Stage
  count: number
  standings: StageProbability[]
}

export interface HealthResponse {
  status: string
  database: string
  git_sha: string | null
  official_run: string | null
}
