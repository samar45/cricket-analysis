import { useEffect, useMemo, useState } from 'react'
import { api, type Meta, type OverUnder, type PredictReq, type Prediction } from './api'
import { ax, base, C, Chart, code, Err, f0, mono, Note, Num, Panel, pc, Select, useAsync } from './ui'

const BIN = 5

function Hist({ p }: { p: Prediction }) {
  const { x, n, mk } = useMemo(() => {
    const lo = Math.floor(Math.min(...p.sims) / BIN) * BIN, hi = Math.floor(Math.max(...p.sims) / BIN) * BIN
    const x: number[] = [], n: number[] = []
    for (let b = lo; b <= hi; b += BIN) { x.push(b); n.push(0) }
    p.sims.forEach((s) => n[Math.floor((s - lo) / BIN)]++)
    const bin = (v: number) => String(Math.min(hi, Math.max(lo, Math.floor(v / BIN) * BIN)))
    const m = (v: number, name: string, c: string) => ({ xAxis: bin(v), lineStyle: { color: c, type: 'dashed', width: 1.5 }, label: { formatter: name, color: c, fontFamily: mono, fontSize: 10 } })
    return { x, n, mk: [m(p.sim.q10, '10%', C.warn), m(p.sim.q50, '50%', C.tx), m(p.sim.q90, '90%', C.warn)] }
  }, [p])
  // label every k-th bin so ticks never crowd (about 8 labels), rotated on narrow screens
  const every = Math.max(0, Math.ceil(x.length / 8) - 1)
  const opt = {
    ...base(),
    tooltip: { ...base().tooltip, formatter: (a: { axisValue: string; value: number }[]) => `${a[0].axisValue} to ${+a[0].axisValue + BIN - 1} runs<br>${a[0].value} of ${p.sims.length} sims` },
    xAxis: { type: 'category', data: x.map(String), ...ax({ axisLabel: { color: C.mut, interval: every, hideOverlap: true } }) },
    yAxis: { type: 'value', ...ax() },
    series: [{ type: 'bar', data: n, itemStyle: { color: C.acc, opacity: 0.55 }, barCategoryGap: '8%', markLine: { symbol: 'none', silent: true, data: mk } }],
  }
  return <Chart option={opt} h={250} />
}

function OverUnderBox({ p }: { p: Prediction }) {
  const [line, setLine] = useState<number | ''>(Math.round(p.score.q50) + 0.5)
  const [r, setR] = useState<OverUnder>()
  const [err, setErr] = useState<string>()
  useEffect(() => setLine(Math.round(p.score.q50) + 0.5), [p])
  useEffect(() => {
    if (line === '') return
    let live = true
    const t = setTimeout(() => api.overUnder({ ...p.score, line, sims: p.sims }).then((x) => { if (live) { setR(x); setErr(undefined) } }, (e: Error) => live && setErr(e.message)), 200)
    return () => { live = false; clearTimeout(t) }
  }, [line, p])
  const over = r?.sim_over ?? r?.p_over
  return (
    <Panel title="Over / under">
      <div className="p-3">
        <div className="flex items-end gap-3">
          <label style={{ width: 110 }}><span className="lbl">Line</span><input className="num" type="number" step={0.5} value={line} onChange={(e) => setLine(e.target.value === '' ? '' : +e.target.value)} /></label>
          <div className="flex-1 num">
            <div className="flex justify-between"><span className="up">Over <b>{over != null ? pc(over) : '-'}</b></span><span className="dn"><b>{over != null ? pc(1 - over) : '-'}</b> Under</span></div>
            <div className="flex mt-1" style={{ height: 8 }}><div style={{ background: 'var(--up)', width: `${(over ?? 0.5) * 100}%` }} /><div className="flex-1" style={{ background: 'var(--dn)' }} /></div>
          </div>
        </div>
        <div className="mut mt-2" style={{ fontSize: 11 }}>
          Share of {p.sims.length.toLocaleString()} simulated innings finishing over the line{r && r.sim_over != null ? ` (from the range alone: ${pc(r.p_over)})` : ''}.
        </div>
        <Err msg={err} />
      </div>
    </Panel>
  )
}

function Replay({ meta, comp }: { meta?: Meta; comp: string }) {
  const [season, setSeason] = useState('')
  const [mid, setMid] = useState('')
  useEffect(() => { if (meta && !season) setSeason(meta.data_to.slice(0, 4)) }, [meta, season])
  const ms = useAsync(() => (season ? api.matches(comp, season) : Promise.resolve([])), [comp, season])
  useEffect(() => { setMid(ms.data?.[0]?.match_id ?? '') }, [ms.data])
  const cv = useAsync(() => (mid ? api.matchCurve(mid) : Promise.resolve(undefined)), [mid])
  const c = cv.data
  const pts = c?.points ?? []
  const opt = c && {
    ...base(),
    tooltip: { ...base().tooltip, formatter: (a: { dataIndex: number }[]) => { const r = pts[a[0].dataIndex]; return `Inn ${r.innings}, over ${r.over.toFixed(1)}: ${r.runs}/${r.wickets}<br>1st-batting side win ${pc(r.p_bat_first_win)}` } },
    xAxis: { type: 'category', data: pts.map((r) => `${r.innings}:${r.over.toFixed(1)}`), name: 'innings : over', nameLocation: 'middle', nameGap: 24, ...ax({ axisLabel: { color: C.mut, interval: Math.max(0, Math.ceil(pts.length / 8) - 1), hideOverlap: true } }) },
    yAxis: { type: 'value', min: 0, max: 100, ...ax({ axisLabel: { color: C.mut, formatter: '{value}%' } }) },
    series: [
      { type: 'line', data: pts.map((r) => +(r.p_bat_first_win * 100).toFixed(1)), showSymbol: false, lineStyle: { color: C.acc, width: 2 }, areaStyle: { color: C.acc, opacity: 0.06 },
        markLine: { symbol: 'none', silent: true, data: [{ yAxis: 50, lineStyle: { color: C.mut, type: 'dotted' }, label: { show: false } }] } },
      { type: 'scatter', data: pts.map((r, i) => (i && r.innings === pts[i - 1].innings && r.wickets > pts[i - 1].wickets ? [i, +(r.p_bat_first_win * 100).toFixed(1)] : null)).filter(Boolean),
        symbolSize: 9, itemStyle: { color: C.dn, borderColor: '#000', borderWidth: 1 }, tooltip: { show: false }, z: 5 },
    ],
  }
  const m = ms.data?.find((x) => x.match_id === mid)
  return (
    <Panel title="Replay: win probability" right={m ? `${m.team1} v ${m.team2}, ${m.date}` : ''} className="col-span-12 md:col-span-6">
      <div className="p-3 grid grid-cols-3 gap-2">
        <label><span className="lbl">Season</span><input className="num" value={season} onChange={(e) => setSeason(e.target.value)} /></label>
        <Select className="col-span-2" label="Match" value={mid} onChange={setMid} options={(ms.data ?? []).map((x) => ({ v: x.match_id, t: `${x.date} ${x.team1} v ${x.team2}` }))} />
      </div>
      <Err msg={ms.err ?? cv.err} />
      {opt && <Chart option={opt} h={230} />}
      {c && <div className="note" style={c.in_sample ? undefined : { borderColor: 'var(--line)' }}>{c.in_sample ? 'This match was in the training data, so the curve flatters the model.' : 'Out-of-sample match: not in the training data.'} Line = win chance of the side batting first; red dots = wickets.</div>}
      {c?.caveats?.map((t) => <Note key={t}>{t}</Note>)}
    </Panel>
  )
}

export default function Predictor({ meta }: { meta?: Meta }) {
  const [comp, setComp] = useState('ipl')
  const ch = useAsync(() => api.choices(comp), [comp])
  const [f, setF] = useState({ venue: '', bat: '', bowl: '', innings: 1 as 1 | 2, runs: 90 as number | '', wk: 3 as number | '', ov: 10 as number | '', target: 181 as number | '', striker: '', non_striker: '', bowler: '' })
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }))
  useEffect(() => { if (ch.data) setF((p) => ({ ...p, venue: ch.data!.venues[0] ?? '', bat: ch.data!.teams[0] ?? '', bowl: ch.data!.teams[1] ?? '', striker: '', non_striker: '', bowler: '' })) }, [ch.data])

  const [pred, setPred] = useState<{ p: Prediction; req: PredictReq }>()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string>()
  const run = () => {
    const req: PredictReq = { competition: comp, venue: f.venue, batting_team: f.bat, bowling_team: f.bowl, innings: f.innings, runs: +f.runs, wickets: +f.wk, overs: +f.ov, n_sims: 1000 }
    if (f.innings === 2) req.target = +f.target
    if (f.striker) req.striker = f.striker
    if (f.non_striker) req.non_striker = f.non_striker
    if (f.bowler) req.bowler = f.bowler
    setBusy(true); setErr(undefined)
    api.predict(req).then((p) => setPred({ p, req }), (e: Error) => setErr(e.message)).finally(() => setBusy(false))
  }
  const opts = (a: string[] = []) => a.map((v) => ({ v, t: v }))
  const players = [{ v: '', t: '(average player)' }, ...opts(ch.data?.players)]
  const teams = opts(ch.data?.teams)
  const { p, req } = pred ?? {}
  const inn1 = req?.innings === 1

  return (
    <section className="grid grid-cols-12 gap-3">
      <Panel title="Match state" className="col-span-12 lg:col-span-3 self-start">
        <div className="p-3 grid grid-cols-2 gap-2">
          <Select className="col-span-2" label="Competition" value={comp} onChange={setComp} options={(meta?.competitions ?? [{ key: 'ipl', label: 'IPL' }]).map((c) => ({ v: c.key, t: c.label }))} />
          <Select className="col-span-2" label="Venue" value={f.venue} onChange={(v) => set('venue', v)} options={opts(ch.data?.venues)} />
          <Select label="Batting" value={f.bat} onChange={(v) => set('bat', v)} options={teams} />
          <Select label="Bowling" value={f.bowl} onChange={(v) => set('bowl', v)} options={teams} />
          <div className="col-span-2"><span className="lbl">Innings</span>
            <div className="seg flex mt-1">
              <button className={`flex-1 ${f.innings === 1 ? 'on' : ''}`} onClick={() => set('innings', 1)}>1st: set a score</button>
              <button className={`flex-1 ${f.innings === 2 ? 'on' : ''}`} onClick={() => set('innings', 2)}>2nd: chase</button>
            </div></div>
          <Num label="Runs" value={f.runs} onChange={(v) => set('runs', v)} min={0} />
          <Num label="Wickets" value={f.wk} onChange={(v) => set('wk', v)} min={0} max={10} />
          <Num label="Overs" value={f.ov} onChange={(v) => set('ov', v)} min={0} max={20} />
          <Num label="Target" value={f.target} onChange={(v) => set('target', v)} min={1} disabled={f.innings === 1} />
          <Select className="col-span-2" label="Striker (optional)" value={f.striker} onChange={(v) => set('striker', v)} options={players} />
          <Select className="col-span-2" label="Non-striker (optional)" value={f.non_striker} onChange={(v) => set('non_striker', v)} options={players} />
          <Select className="col-span-2" label="Bowler (optional)" value={f.bowler} onChange={(v) => set('bowler', v)} options={players} />
          <button className="btn col-span-2 mt-1" onClick={run} disabled={busy || !f.venue || !f.bat}>{busy ? 'Running...' : 'Predict'}</button>
          <Err msg={err ?? ch.err} />
          <p className="col-span-2 mut" style={{ fontSize: 11 }}>Players not named: the model assumes average batters and bowlers.</p>
        </div>
      </Panel>

      <div className="col-span-12 lg:col-span-9 grid grid-cols-12 gap-3 content-start">
        {!p || !req ? (
          <Panel title="Prediction" className="col-span-12"><div className="p-3 mut">Set the match state and press Predict.</div></Panel>
        ) : (<>
          <Panel title={`${req.batting_team} ${inn1 ? 'batting first' : 'chasing ' + req.target}`} right={`${req.runs}/${req.wickets} after ${req.overs} ov`} className="col-span-12 md:col-span-7">
            <div className="p-3">
              <div className="lbl">{inn1 ? 'Projected final score (median)' : 'Projected chase score (median)'}</div>
              <div className="flex items-baseline gap-3 flex-wrap"><span className="num acc" style={{ fontSize: 40, fontWeight: 500, lineHeight: 1.1 }}>{f0(p.score.q50)}</span><span className="mut num">range {f0(p.score.q10)} to {f0(p.score.q90)}</span></div>
              <RangeBar runs={req.runs} q={p.score} />
              <div className="mt-4"><div className="lbl">Win probability</div>
                <div className="flex mt-1" style={{ height: 24, overflow: 'hidden' }}>
                  <div className="num flex items-center px-2 whitespace-nowrap" title={req.batting_team} style={{ background: 'var(--acc)', color: '#000', fontWeight: 700, width: `${p.win.bat * 100}%`, minWidth: 92 }}>{code(req.batting_team)} {pc(p.win.bat)}</div>
                  <div className="num flex items-center justify-end px-2 flex-1 whitespace-nowrap" title={req.bowling_team} style={{ background: 'var(--panel2)', border: '1px solid var(--line)' }}>{pc(p.win.bowl)} {code(req.bowling_team)}</div>
                </div></div>
            </div>
          </Panel>
          <div className="col-span-12 md:col-span-5 grid gap-3 content-start">
            <Panel title="Model breakdown"><div className="tw"><table>
              <thead><tr><th>Model</th><th className="r">q10</th><th className="r">q50</th><th className="r">q90</th><th className="r">Win %</th></tr></thead>
              <tbody className="num">
                <MRow name="G1" sub="gradient-boosted model" q={inn1 ? p.g1 : {}} win={p.g1.win_bat} />
                <MRow name="Simulator" sub="ball-by-ball simulation" q={p.sim} win={p.sim.win_bat} />
                <MRow name="Shown" sub={inn1 ? 'score: G1 only; win: average' : 'score: simulator; win: average'} q={p.score} win={p.win.bat} bold />
              </tbody></table></div></Panel>
            <OverUnderBox p={p} />
          </div>
          <Panel title="Simulated final score" right={`${p.sims.length.toLocaleString()} runs`} className="col-span-12 md:col-span-6">
            <Hist p={p} />
          </Panel>
        </>)}
        <Replay meta={meta} comp={comp} />
        {p && <div className="col-span-12 grid gap-1" aria-label="Caveats">
          {p.caveats.map((t) => <div key={t} className="mut" style={{ fontSize: 11.5 }}>{t}</div>)}
        </div>}
      </div>
    </section>
  )
}

function RangeBar({ runs, q }: { runs: number; q: { q10: number; q50: number; q90: number } }) {
  const lo = Math.min(runs, q.q10) - 10, hi = q.q90 + 10, pos = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`
  return (
    <div className="mt-3">
      <div className="flex justify-between num mut" style={{ fontSize: 11 }}><span>{f0(q.q10)} (10%)</span><span>{f0(q.q90)} (90%)</span></div>
      <div style={{ position: 'relative', height: 10, background: 'var(--bg)', border: '1px solid var(--line)', marginTop: 3 }}>
        <div style={{ position: 'absolute', top: 0, bottom: 0, background: 'var(--acc)', opacity: 0.3, left: pos(q.q10), width: `${((q.q90 - q.q10) / (hi - lo)) * 100}%` }} />
        <div style={{ position: 'absolute', top: -3, bottom: -3, width: 2, background: 'var(--acc)', left: pos(q.q50) }} />
      </div>
      <div className="mut mt-1" style={{ fontSize: 11 }}>10th to 90th percentile band. Line = median.</div>
    </div>
  )
}

function MRow({ name, sub, q, win, bold }: { name: string; sub: string; q: Partial<{ q10: number; q50: number; q90: number }>; win?: number; bold?: boolean }) {
  const B = bold ? 'b' : 'span'
  return (
    <tr style={bold ? { background: 'var(--panel2)' } : undefined}>
      <td style={{ fontFamily: 'Roboto' }}><B>{name}</B><div className="mut" style={{ fontSize: 10.5 }}>{sub}</div></td>
      {(['q10', 'q50', 'q90'] as const).map((k) => <td key={k} className="r"><B>{q[k] != null ? f0(q[k]!) : '-'}</B></td>)}
      <td className={`r ${bold ? 'acc' : ''}`}><B>{win != null ? pc(win) : '-'}</B></td>
    </tr>
  )
}
