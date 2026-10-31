import { useEffect, useState } from 'react'
import { RefreshCw, Sparkles } from 'lucide-react'
import { t } from '../i18n'

type AnalysisStatus = { waiting: number; processing: number; completed: number; failed: number; importing: boolean }
type Api = (path: string, options?: RequestInit) => Promise<any>

export function AnalysisControls({ api, query, onUpdated, scopeLabel, disabled = false }: {
  api: Api; query: string; onUpdated: () => Promise<void>; scopeLabel: string; disabled?: boolean
}) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let active = true
    setStatus(null); setError(''); setNotice('')
    const load = async () => {
      try {
        const result = await api('/analysis?' + query)
        if (active) { setStatus(result); setError('') }
      } catch (error: any) { if (active) setError(error.message) }
    }
    load()
    const timer = window.setInterval(load, 4000)
    return () => { active = false; window.clearInterval(timer) }
  }, [api, query])

  async function start() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api('/analysis?' + query, { method: 'POST' })
      setNotice(t('analysis.queued_notice', { count: result.queued }))
      setStatus(await api('/analysis?' + query))
      await onUpdated()
    } catch (error: any) { setError(error.message) }
    finally { setBusy(false) }
  }
  const processing = !!status?.processing
  return <section className="analysis-controls" aria-label={t('analysis.start')}>
    <div className="analysis-controls-heading">
      <div><h3><Sparkles size={18}/>{t('analysis.start')}</h3><p>{t('analysis.manual_description')}</p><small>{scopeLabel}</small></div>
      <button className="btn primary" disabled={disabled || busy || !status || !!error || status.importing || processing || status.waiting + status.failed === 0} onClick={start}>
        {busy || processing ? <RefreshCw size={16} className="spin"/> : <Sparkles size={16}/>}
        {t(processing ? 'analysis.processing' : 'analysis.start')}
      </button>
    </div>
    {status && <div className="analysis-counts" aria-live="polite">
      <span>{t('analysis.waiting_count', { count: status.waiting })}</span>
      <span>{t('analysis.processing_count', { count: status.processing })}</span>
      <span>{t('analysis.completed_count', { count: status.completed })}</span>
      {status.failed > 0 && <span className="red-text">{t('analysis.failed_count', { count: status.failed })}</span>}
    </div>}
    {status?.importing && <p role="status">{t('analysis.intake_in_progress')}</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="red-text" role="alert">{error}</p>}
  </section>
}
