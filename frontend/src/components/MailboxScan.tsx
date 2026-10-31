import { useState } from 'react'
import { ArrowRight, CheckCircle2, RefreshCw, Search } from 'lucide-react'
import { t } from '../i18n'

export type ScanStatus = {
  sync_status: string | null
  sync_summary: Record<string, number>
  sync_error: string | null
}

export function MailboxScan({ status, defaultDays, disabled, onScan, onView }: {
  status: ScanStatus; defaultDays: number; disabled: boolean
  onScan: (mode: string, days: number) => void
  onView: (page: 'inbox' | 'cases') => void
}) {
  const [mode, setMode] = useState('incremental')
  const [days, setDays] = useState(defaultDays)
  const scanning = status.sync_status === 'PENDING' || status.sync_status === 'RUNNING'
  const summary = status.sync_summary || {}
  return <section className="mailbox-scan" aria-labelledby="mailbox-scan-title">
    <h3 id="mailbox-scan-title"><Search size={19}/>{t('scan.title')}</h3>
    <p className="scan-description">{t('scan.description')}</p>
    <form className="scan-form" onSubmit={event => { event.preventDefault(); onScan(mode, days) }}>
      <label>{t('scan.mode')}<select value={mode} disabled={disabled || scanning} onChange={event => setMode(event.target.value)}>
        <option value="incremental">{t('scan.incremental')}</option>
        <option value="rescan">{t('scan.rescan')}</option>
      </select></label>
      {mode === 'rescan' && <label className="scan-days">{t('scan.days')}<input type="number" min={1} max={365} required value={days} disabled={disabled || scanning} onChange={event => setDays(Number(event.target.value))}/></label>}
      <button className="btn primary" disabled={disabled || scanning} type="submit"><RefreshCw size={16} className={scanning ? 'spin' : ''}/>{t(scanning ? 'scan.running' : 'scan.start')}</button>
    </form>
    {scanning && <p className="muted" role="status">{t('scan.progress')}</p>}
    {!!Object.keys(summary).length && <div className="scan-counts" aria-live="polite">
      {(['scanned', 'matched', 'new', 'existing'] as const).map(key => <div key={key}><strong>{summary[key] || 0}</strong><span>{t(`scan.count_${key}`)}</span></div>)}
    </div>}
    {status.sync_status === 'DONE' && <p className="scan-completed" role="status"><CheckCircle2 size={16} aria-hidden="true"/><span>{t('scan.completed')}</span></p>}
    {!scanning && status.sync_status === 'DONE' && summary.matched === 0 && <p className="muted">{t('scan.no_match')}</p>}
    <footer className="scan-footer">
      <small>{t('scan.scope')}</small>
      <div className="button-row"><button className="text-btn" onClick={() => onView('inbox')}>{t('scan.view_emails')}<ArrowRight size={14}/></button><button className="text-btn" onClick={() => onView('cases')}>{t('scan.view_cases')}<ArrowRight size={14}/></button></div>
    </footer>
  </section>
}
