import { useEffect, useState, type ReactNode } from 'react'
import CoreMod from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

// CJS package: under bundlers the default import can be the module object itself
const ReactEChartsCore = ((CoreMod as unknown as { default?: typeof CoreMod }).default ?? CoreMod) as typeof CoreMod

echarts.use([BarChart, LineChart, ScatterChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

export const C = { tx: '#B6F2C8', mut: '#7FA88A', line: '#0F2A12', acc: '#00FF66', dn: '#FF3B3B', warn: '#FFB000', pan: '#0A0F0A' }
export const mono = "'Roboto Mono', monospace"
export const f0 = (x: number) => Math.round(x).toString()
export const pc = (x: number) => (x * 100).toFixed(1) + '%'
export const sgn = (x: number) => (x >= 0 ? '+' : '') + x.toFixed(2)
export const code = (t: string) => t.split(' ').map((w) => w[0]).join('').toUpperCase()

export const base = () => ({
  backgroundColor: 'transparent', animation: false,
  textStyle: { fontFamily: mono, color: C.mut, fontSize: 11 },
  grid: { left: 46, right: 16, top: 24, bottom: 34 },
  tooltip: { trigger: 'axis', backgroundColor: C.pan, borderColor: C.line, textStyle: { color: C.tx, fontFamily: mono, fontSize: 12 } },
})
export const ax = (o: object = {}) => ({ axisLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.mut }, splitLine: { lineStyle: { color: C.line } }, ...o })

export function Chart({ option, h }: { option: object; h: number }) {
  return <ReactEChartsCore echarts={echarts} option={option} notMerge style={{ height: h, width: '100%' }} />
}

export const Panel = ({ title, right, className = '', children }: { title: ReactNode; right?: ReactNode; className?: string; children: ReactNode }) => (
  <div className={`panel ${className}`}>
    <div className="ph"><span>{title}</span>{right != null && <span className="mut" style={{ textTransform: 'none', letterSpacing: 0 }}>{right}</span>}</div>
    {children}
  </div>
)
export const Note = ({ children }: { children: ReactNode }) => <div className="note">{children}</div>

export function Num({ label, value, onChange, step = 1, min, max, disabled }: { label: string; value: number | ''; onChange: (v: number | '') => void; step?: number; min?: number; max?: number; disabled?: boolean }) {
  const set = (v: number) => onChange(min != null ? Math.max(min, max != null ? Math.min(max, v) : v) : v)
  return (
    <label><span className="lbl">{label}</span>
      <div className="step">
        <button type="button" disabled={disabled} onClick={() => set((+value || 0) - step)}>-</button>
        <input className="num" type="number" step={step} min={min} max={max} disabled={disabled} value={value} onChange={(e) => onChange(e.target.value === '' ? '' : +e.target.value)} />
        <button type="button" disabled={disabled} onClick={() => set((+value || 0) + step)}>+</button>
      </div>
    </label>
  )
}

export function Select({ label, value, options, onChange, className = '' }: { label: string; value: string; options: { v: string; t: string }[]; onChange: (v: string) => void; className?: string }) {
  return (
    <label className={className}><span className="lbl">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} title={value}>
        {options.map((o) => <option key={o.v} value={o.v}>{o.t}</option>)}
      </select>
    </label>
  )
}

/** Run an async loader; returns {data, err, loading}. Re-runs when deps change. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [s, set] = useState<{ data?: T; err?: string; loading: boolean }>({ loading: true })
  useEffect(() => {
    let live = true
    set((p) => ({ ...p, loading: true }))
    fn().then((data) => live && set({ data, loading: false }), (e: Error) => live && set({ err: e.message, loading: false }))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return s
}
export const Err = ({ msg }: { msg?: string }) => (msg ? <div className="dn p-3" role="alert">Error: {msg}</div> : null)
