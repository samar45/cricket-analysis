import { useEffect, useState } from 'react'
import { api, useMock } from './api'
import Paper from './Paper'
import Predictor from './Predictor'
import { Err, useAsync } from './ui'

const TABS = [{ k: 'pred', f: 'F1', t: 'Match Predictor' }, { k: 'paper', f: 'F2', t: 'Paper Trading' }] as const

export default function App() {
  const [tab, setTab] = useState<(typeof TABS)[number]['k']>('pred')
  const [clock, setClock] = useState('')
  useEffect(() => {
    const t = () => setClock(new Date().toISOString().slice(0, 19).replace('T', ' ') + ' UTC')
    t(); const id = setInterval(t, 1000); return () => clearInterval(id)
  }, [])
  const { data: m, err } = useAsync(api.meta, [])
  return (
    <>
      <div className="ticker flex gap-x-5 px-3 py-1">
        <span><b>&#9679; {useMock ? 'MOCK' : 'LIVE'}</b>{useMock ? ' MOCK DATA' : ''}</span>
        <span>DB <span className="num">{m?.data_to ?? '-'}</span></span>
        <span className="hidden md:inline">{m?.competitions.map((c) => c.label).join(' · ')}</span>
        <span className="ml-auto num">{clock}</span>
      </div>
      <header className="flex flex-wrap items-center gap-x-5 gap-y-1 px-3 py-1" style={{ borderBottom: '1px solid var(--line)', background: 'var(--panel)' }}>
        <b className="acc" style={{ letterSpacing: '.16em', fontWeight: 700 }}>CRICKET&nbsp;TERMINAL<span className="cur" /></b>
        <span className="mut lbl" style={{ display: 'inline' }}>Data to <span className="num" style={{ color: 'var(--tx)' }}>{m?.data_to ?? '-'}</span></span>
        <span className="mut lbl" style={{ display: 'inline' }}>Model <span className="num" style={{ color: 'var(--tx)' }}>{m ? `score ${m.model.score} / win ${m.model.chase}` : '-'}</span> &middot; trained to <span className="num" style={{ color: 'var(--tx)' }}>{m?.trained_to ?? '-'}</span></span>
        <span className="badge ml-auto">PAPER TRADING &middot; FAKE MONEY</span>
      </header>
      <Err msg={err && `Backend not reachable (${err}). Start it on port 8600, or open with ?mock=1.`} />
      <div className="flex flex-col md:flex-row" style={{ minHeight: 'calc(100vh - 62px)' }}>
        <nav className="nav md:w-48 shrink-0" style={{ background: 'var(--panel)', borderRight: '1px solid var(--line)' }}>
          {TABS.map((x) => (
            <a key={x.k} className={tab === x.k ? 'on' : ''} tabIndex={0} onClick={() => setTab(x.k)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setTab(x.k)}><b>{x.f}</b> {x.t}</a>
          ))}
        </nav>
        <main className="flex-1 p-3 min-w-0">{tab === 'pred' ? <Predictor meta={m} /> : <Paper />}</main>
      </div>
    </>
  )
}
