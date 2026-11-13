// Typed client for docs/API_web.md (v1). Real API by default; mock with VITE_MOCK=1 or ?mock=1.
import * as mock from './mock'

export interface Meta { data_to: string; model: { score: string; chase: string }; trained_to: string; competitions: { key: string; label: string }[] }
export interface Choices { venues: string[]; teams: string[]; players: string[] }
export interface PredictReq {
  competition: string; venue: string; batting_team: string; bowling_team: string; innings: 1 | 2
  runs: number; wickets: number; overs: number; target?: number
  striker?: string; non_striker?: string; bowler?: string; n_sims?: number
}
export interface Q { q10: number; q50: number; q90: number }
export interface Prediction {
  score: Q; win: { bat: number; bowl: number }
  g1: Partial<Q> & { win_bat: number }; sim: Q & { win_bat: number }
  sims: number[]; level: number; caveats: string[]
}
export interface OverUnder { p_over: number; p_under: number; sim_over?: number }
export interface MatchRow { match_id: string; date: string; team1: string; team2: string; winner: string | null; venue: string }
export interface CurvePoint { innings: number; ball: number; over: number; runs: number; wickets: number; p_bat_first_win: number; q10?: number; q50?: number; q90?: number }
export interface MatchCurve { match: Partial<MatchRow> & Record<string, unknown>; in_sample: boolean; points: CurvePoint[]; caveats?: string[] }
export interface PaperSummary {
  start: number; final: number; roi: number; roi_lo: number; roi_hi: number
  hit_rate: number; max_drawdown: number; n_bets: number; path: { i: number; date: string; bankroll: number }[]
}
export interface LedgerRow { date: string; match: string; checkpoint: number; side: string; p_model: number; price: number; ev: number; stake: number; status: string; pnl: number }
// placed[] shape is not specified in the contract; assumed ledger-like, result fields optional.
export type PlacedBet = Omit<LedgerRow, 'status' | 'pnl' | 'date'> & Partial<Pick<LedgerRow, 'status' | 'pnl' | 'date'>>
export interface MakeBets { placed: PlacedBet[]; explanation: string; note: string }

export const useMock = import.meta.env.VITE_MOCK === '1' || /[?&]mock=1/.test(location.search)

async function http<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error((j as { error?: string }).error ?? `HTTP ${r.status}`)
  return j as T
}
const qs = (o: Record<string, string | number | undefined>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&')

export const api = {
  meta: () => (useMock ? mock.meta() : http<Meta>('/api/meta')),
  choices: (competition: string) => (useMock ? mock.choices() : http<Choices>(`/api/choices?${qs({ competition })}`)),
  predict: (r: PredictReq) => (useMock ? mock.predict(r) : http<Prediction>('/api/predict', r)),
  overUnder: (r: Q & { line: number; sims?: number[] }) => (useMock ? mock.overUnder(r) : http<OverUnder>('/api/over_under', r)),
  matches: (competition: string, season?: string | number) =>
    useMock ? mock.matches() : http<MatchRow[]>(`/api/matches?${qs({ competition, season })}`),
  matchCurve: (id: string) => (useMock ? mock.matchCurve() : http<MatchCurve>(`/api/match_curve/${encodeURIComponent(id)}`)),
  paperSummary: () => (useMock ? mock.paperSummary() : http<PaperSummary>('/api/paper/summary')),
  paperLedger: (limit = 50) => (useMock ? mock.paperLedger() : http<LedgerRow[]>(`/api/paper/ledger?limit=${limit}`)),
  makeBets: (n: number, date?: string) => (useMock ? mock.makeBets(n) : http<MakeBets>('/api/paper/make_bets', { n, date })),
}
