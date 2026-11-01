import { useEffect, useState } from 'react'
import { ArrowRight, RefreshCw, Server } from 'lucide-react'
import { t } from '../i18n'

type Item = Record<string, any>
type Api = (path: string, options?: RequestInit) => Promise<any>
const clock = (value: string | null) => value || '—'
const dayStatus = (value: string) => value === 'LEAVE' ? t('integration.leave') : t('integration.present')

export function HrWorkspace({ api, query, onOpenCase }: { api: Api; query: string; onOpenCase: (id: number) => void }) {
  const [data, setData] = useState<Item | null>(null)
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    setData(null); setError(''); setNotice('')
    const load = async () => {
      try { const next = await api('/hr/workspace?' + query); if (active) { setData(next); setError('') } }
      catch (e: any) { if (active) setError(e.message) }
    }
    load(); const timer = window.setInterval(load, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [api, query])
  async function seed() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api('/hr/demo/seed?' + query, { method: 'POST' })
      setData(await api('/hr/workspace?' + query))
      setNotice(t('integration.seeded', { count: result.created }))
    } catch (e: any) { setError(e.message) }
    finally { setBusy(false) }
  }
  const items: Item[] = data?.items || []
  return <section className="panel hr-workspace">
    <div className="panel-heading"><div><h2><Server size={20}/>{t('integration.hr_tile')}</h2><p>{t('integration.hr_description')}</p></div><button className="btn secondary" onClick={seed} disabled={busy || !data?.connected || !items.length}><RefreshCw size={16} className={busy ? 'spin' : ''}/>{t('integration.seed')}</button></div>
    <div className="integration-summary"><span className={'connection-dot ' + (data?.connected ? 'online' : '')}/><strong>{t(data?.connected ? 'integration.connected' : 'integration.disconnected')}</strong><span>{t('integration.record_count', { count: items.filter(i => i.record).length })}</span></div>
    {(error || data?.error) && <p className="alert error" role="alert">{error || data?.error}</p>}
    {notice && <p className="alert success" role="status">{notice}</p>}
    <div className="table-scroll"><table><thead><tr><th>{t('integration.employee')}</th><th>{t('integration.work_day')}</th><th>{t('integration.check_in')}</th><th>{t('integration.check_out')}</th><th>{t('integration.day_status')}</th><th/></tr></thead>
      <tbody>{items.map(item => <tr key={item.case_id}><td><strong>{item.employee_name}</strong><small>{item.employee_id} · {item.department}</small><small>{item.case_code}</small></td><td>{item.work_date}<small>{item.shift || '—'}</small></td><td>{clock(item.record?.check_in)}</td><td>{clock(item.record?.check_out)}</td><td>{item.record ? <><strong>{dayStatus(item.record.day_status)}</strong><small>{t('integration.revision', { revision: item.record.revision })}</small></> : <span className="muted">{t('integration.not_seeded')}</span>}</td><td><button className="btn secondary small-btn" onClick={() => onOpenCase(item.case_id)}>{t('integration.review_correction')}<ArrowRight size={14}/></button></td></tr>)}</tbody></table></div>
    {!data && !error && <p className="integration-empty">{t('common.loading')}</p>}
    {data && !items.length && <p className="integration-empty">{t('integration.no_cases')}</p>}
    <p className="integration-environment">{t('integration.seed_notice')}</p>
  </section>
}
