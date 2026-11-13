// Offline stand-in for the backend (flag: VITE_MOCK=1 or ?mock=1). Numbers are illustrative, shapes follow docs/API_web.md.
import type { Choices, LedgerRow, MakeBets, MatchCurve, MatchRow, Meta, OverUnder, PaperSummary, PredictReq, Prediction, Q } from './api'

const wait = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 150))
const rng = (() => { let s = 7; return () => ((s = (s * 16807) % 2147483647) / 2147483647) })()
const normal = () => Math.sqrt(-2 * Math.log(rng() || 1e-9)) * Math.cos(2 * Math.PI * rng())

export const meta = () => wait<Meta>({
  data_to: '2026-11-01', model: { score: 'G1', chase: 'ens-G1' }, trained_to: '2026-10-14',
  competitions: [{ key: 'ipl', label: 'IPL' }, { key: 'bbl', label: 'BBL' }, { key: 't20i_men', label: 'T20I men' }],
})
export const choices = () => wait<Choices>({
  venues: ['MA Chidambaram Stadium, Chepauk', 'Wankhede Stadium, Mumbai'],
  teams: ['Chennai Super Kings', 'Sunrisers Hyderabad', 'Mumbai Indians'], players: [],
})
export const predict = (r: PredictReq) => {
  const base = r.innings === 1 ? r.runs + (20 - r.overs) * 9.4 : r.target ?? 180
  const q50 = Math.round(base), q10 = q50 - 25, q90 = q50 + 25
  const sims = Array.from({ length: r.n_sims ?? 1000 }, () => Math.round(q50 + 6 + normal() * 19))
  return wait<Prediction>({
    score: { q10, q50, q90 }, win: { bat: 0.44, bowl: 0.56 }, g1: { q10, q50, q90, win_bat: 0.49 },
    sim: { q10: q10 + 4, q50: q50 + 5, q90: q90 + 6, win_bat: 0.39 }, sims, level: q50 + 5,
    caveats: ['MOCK DATA. Simulator runs about 8 runs high in 2026.', 'Only the 10-90% range is checked against real matches.', 'The market beat this model on 303 BBL matches.'],
  })
}
export const overUnder = (r: Q & { line: number; sims?: number[] }) => {
  const p = r.sims?.length ? r.sims.filter((x) => x > r.line).length / r.sims.length : 1 / (1 + Math.exp((r.line - r.q50) / 12))
  return wait<OverUnder>({ p_over: p, p_under: 1 - p, sim_over: p })
}
export const matches = () => wait<MatchRow[]>([
  { match_id: '1535465', date: '2026-05-31', team1: 'Gujarat Titans', team2: 'Royal Challengers Bengaluru', winner: 'Royal Challengers Bengaluru', venue: 'Narendra Modi Stadium' },
])
export const matchCurve = () => {
  const points: MatchCurve['points'] = []
  let p = 0.5, w = 0, runs = 0
  for (let b = 1; b <= 120; b++) {
    p = Math.min(0.98, Math.max(0.02, p + (rng() - 0.5) * 0.06 + (b > 90 ? 0.005 : 0)))
    runs += rng() < 0.7 ? Math.floor(rng() * 5) : 0
    if (rng() < 0.05) w++
    points.push({ innings: b <= 120 ? 2 : 1, ball: b, over: b / 6, runs, wickets: w, p_bat_first_win: 1 - p })
  }
  return wait<MatchCurve>({ match: { team1: 'Gujarat Titans', team2: 'Royal Challengers Bengaluru', date: '2026-05-31' }, in_sample: true, points })
}
const START = 1000
export const paperSummary = () => {
  let b = START
  const path = [{ i: 0, date: '2025-01-01', bankroll: b }]
  for (let i = 1; i <= 60; i++) { b += (rng() - 0.52) * 40; path.push({ i, date: `2025-02-${String(1 + (i % 28)).padStart(2, '0')}`, bankroll: b }) }
  return wait<PaperSummary>({ start: START, final: b, roi: (b - START) / 2000, roi_lo: -0.25, roi_hi: 0.3, hit_rate: 0.38, max_drawdown: 0.16, n_bets: 60, path })
}
const sides = ['Brisbane Heat', 'Sydney Sixers', 'Perth Scorchers']
export const paperLedger = () => wait<LedgerRow[]>(Array.from({ length: 15 }, (_, i) => {
  const won = i % 3 === 0, price = i === 4 ? 24.5 : 1.8 + i * 0.3, stake = 30 + i
  return { date: `2025-02-${String(10 + i).padStart(2, '0')}`, match: `${sides[i % 3]} v ${sides[(i + 1) % 3]}`, checkpoint: 6 + (i % 10), side: sides[i % 3],
    p_model: 0.5, price, ev: 0.05 + i * 0.01, stake, status: won ? 'won' : 'lost', pnl: won ? stake * (price - 1) : -stake }
}))
export const makeBets = (n: number) => wait<MakeBets>({
  placed: Array.from({ length: Math.min(n, 3) }, (_, i) => ({ match: `${sides[i]} v ${sides[(i + 1) % 3]}`, checkpoint: 10, side: sides[i], p_model: 0.55, price: 2.1 + i, ev: 0.08, stake: 40 })),
  explanation: 'MOCK: picked the highest-EV price points, one per match.', note: 'paper trading, fake money',
})
