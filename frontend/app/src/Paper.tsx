import { useState } from 'react'
import { api, type MakeBets } from './api'
import { ax, base, C, Chart, Err, Note, Panel, pc, sgn, useAsync } from './ui'

const LONG = 20
const LongShot = ({ price }: { price: number }) =>
  price > LONG ? <span className="ls" title="extreme long shot: model and market both see a tiny chance; small probability errors create big &quot;EV&quot;">&#9650;</span> : null

function Tile({ l, v, d, cls }: { l: string; v: string; d: string; cls?: string }) {
  return (
    <div className="panel p-3"><div className="lbl">{l}</div>
      <div className="num acc" style={{ fontSize: 22, fontWeight: 500, lineHeight: 1.3 }}>{v}</div>
      <div className={`num ${cls ?? 'mut'}`} style={{ fontSize: 12 }}>{d}</div></div>
  )
}

export default function Paper() {
  const sum = useAsync(api.paperSummary, [])
  const [rev, setRev] = useState(0)
  const led = useAsync(() => api.paperLedger(50), [rev])
  const [n, setN] = useState<number | ''>(2)
  const [out, setOut] = useState<MakeBets>()
  const [err, setErr] = useState<string>()
  const [busy, setBusy] = useState(false)
  const make = () => {
    setBusy(true); setErr(undefined)
    api.makeBets(+n || 1).then((r) => { setOut(r); setRev((x) => x + 1) }, (e: Error) => setErr(e.message)).finally(() => setBusy(false))
  }
  const S = sum.data
  const pnl = S ? S.final - S.start : 0
  const pts = S?.path ?? []
  const eq = S && {
    ...base(),
    tooltip: { ...base().tooltip, formatter: (a: { dataIndex: number; value: number[] }[]) => `Bet ${a[0].value[0]} (${pts[a[0].dataIndex]?.date ?? ''})<br>Bankroll ${a[0].value[1].toFixed(0)}` },
    xAxis: { type: 'value', name: 'bet #', nameLocation: 'middle', nameGap: 22, ...ax() },
    yAxis: { type: 'value', scale: true, ...ax() },
    series: [{ type: 'line', data: pts.map((p) => [p.i, p.bankroll]), showSymbol: false, lineStyle: { color: C.acc, width: 2 }, areaStyle: { color: C.acc, opacity: 0.06 },
      markLine: { symbol: 'none', silent: true, data: [{ yAxis: S.start, lineStyle: { color: C.mut, type: 'dashed' }, label: { formatter: 'start', color: C.mut } }] } }],
  }
  const ci = S ? `${(S.roi_lo * 100).toFixed(0)}% to ${S.roi_hi > 0 ? '+' : ''}${(S.roi_hi * 100).toFixed(0)}%` : ''
  return (
    <section className="grid grid-cols-12 gap-3">
      <Err msg={sum.err} />
      {S && <div className="col-span-12 grid grid-cols-2 md:grid-cols-6 gap-3">
        <Tile l="Start" v={S.start.toLocaleString('en', { maximumFractionDigits: 0 })} d="fake money" />
        <Tile l="Final" v={S.final.toLocaleString('en', { maximumFractionDigits: 0 })} d={`${pnl >= 0 ? '+' : ''}${pnl.toFixed(0)} vs start`} cls={pnl >= 0 ? 'up' : 'dn'} />
        <Tile l="ROI" v={(S.roi * 100).toFixed(2) + '%'} d={`95% range ${ci}`} cls="warn" />
        <Tile l="Hit rate" v={pc(S.hit_rate)} d="bets that won" />
        <Tile l="Max drawdown" v={'-' + pc(S.max_drawdown)} d="peak to trough" cls="dn" />
        <Tile l="Bets" v={String(S.n_bets)} d="replay, one per match" />
      </div>}
      <Panel title="Bankroll path" right="replay, fake money" className="col-span-12 lg:col-span-8">
        {eq && <Chart option={eq} h={290} />}
        {S && <Note>ROI is not distinguishable from zero if the 95% range <span className="num">{ci}</span> includes 0. The market beat this model in the replay.</Note>}
      </Panel>
      <Panel title="Make N bets" className="col-span-12 lg:col-span-4 self-start">
        <div className="p-3">
          <div className="flex items-end gap-2">
            <label style={{ width: 90 }}><span className="lbl">N</span><input className="num" type="number" min={1} value={n} onChange={(e) => setN(e.target.value === '' ? '' : +e.target.value)} /></label>
            <button className="btn" onClick={make} disabled={busy}>{busy ? 'Working...' : 'Make bets'}</button>
          </div>
          <Err msg={err} />
          {out && <div className="mt-3">
            <div className="mut mb-2" style={{ fontSize: 12.5, lineHeight: 1.5 }}>{out.explanation}</div>
            <div className="tw"><table>
              <thead><tr><th>Match</th><th>Side</th><th className="r">p</th><th className="r">Price</th><th className="r">EV</th><th className="r">Stake</th></tr></thead>
              <tbody className="num">{out.placed.map((b, i) => (
                <tr key={i}><td style={{ fontFamily: 'Roboto' }}>{b.match}<div className="mut" style={{ fontSize: 10.5 }}>at over {b.checkpoint / 6}</div></td>
                  <td style={{ fontFamily: 'Roboto' }}>{b.side}</td><td className="r">{b.p_model.toFixed(3)}</td>
                  <td className="r"><LongShot price={b.price} />{b.price.toFixed(2)}</td><td className="r up">{sgn(b.ev)}</td><td className="r">{b.stake.toFixed(0)}</td></tr>))}
              </tbody></table></div>
            <div className="warn mt-2" style={{ fontSize: 11 }}>{out.note}</div>
          </div>}
          <p className="mut mt-3" style={{ fontSize: 11 }}>Rule: bet only if EV is at least 3%; quarter-Kelly stake, capped at 5% of bankroll; one bet per match.</p>
        </div>
      </Panel>
      <Panel title="Ledger" right={`last ${led.data?.length ?? ''} bets`} className="col-span-12">
        <Err msg={led.err} />
        <div className="tw"><table>
          <thead><tr><th>Date</th><th>Match</th><th className="r">Over</th><th>Side</th><th className="r">p model</th><th className="r">Price</th><th className="r">EV</th><th className="r">Stake</th><th>Result</th><th className="r">P&amp;L</th></tr></thead>
          <tbody className="num">{(led.data ?? []).map((r, i) => { const w = r.status === 'won', c = w ? 'up' : r.status === 'lost' ? 'dn' : 'mut'
            return <tr key={i}><td>{r.date}</td><td style={{ fontFamily: 'Roboto' }}>{r.match}</td><td className="r">{r.checkpoint / 6}</td><td style={{ fontFamily: 'Roboto' }}>{r.side}</td>
              <td className="r">{r.p_model.toFixed(3)}</td><td className="r"><LongShot price={r.price} />{r.price.toFixed(2)}</td><td className="r">{sgn(r.ev)}</td>
              <td className="r">{r.stake.toFixed(2)}</td><td className={c}>{r.status.toUpperCase()}</td><td className={`r ${c}`}>{sgn(r.pnl)}</td></tr> })}
          </tbody></table></div>
      </Panel>
      <div className="col-span-12 text-center warn" style={{ fontWeight: 600, letterSpacing: '.04em' }}>Paper trading, fake money. Not betting advice.</div>
    </section>
  )
}
