import { useEffect, useState } from 'react'
import { Clock3, LoaderCircle, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react'
import { t } from '../i18n'

type AnalysisStatus = {
  waiting: number; processing: number; completed: number; failed: number; importing: boolean
  preprocessing?: number; vlm_waiting?: number; vlm_running?: number
}
type Api = (path: string, options?: RequestInit) => Promise<any>

export function AnalysisControls({ api, query, onUpdated, scopeLabel, disabled = false }: {
  api: Api; query: string; onUpdated: () => Promise<void>; scopeLabel: string; disabled?: boolean
}) {
  const [status, setStatus] = useState<AnalysisStatus | null>(null)
  const [request, setRequest] = useState<'preprocess' | 'analyze' | null>(null)
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
    setRequest('analyze'); setError(''); setNotice('')
    try {
      const result = await api('/analysis?' + query, { method: 'POST' })
      setNotice(t('analysis.queued_notice', { count: result.queued }))
      setStatus(await api('/analysis?' + query))
      await onUpdated()
    } catch (error: any) { setError(error.message) }
    finally { setRequest(null) }
  }
  async function preprocess() {
    setRequest('preprocess'); setError(''); setNotice('')
    try {
      const result = await api('/privacy/preprocess?' + query, { method: 'POST' })
      setNotice(t('privacy.queued', { count: result.queued }))
      await onUpdated()
    } catch (error: any) { setError(error.message) }
    finally { setRequest(null) }
  }
  const processing = !!status?.processing
  return <section className="analysis-controls" aria-label={t('analysis.start')}>
    <div className="analysis-controls-heading">
      <div><h3><Sparkles size={18}/>{t('analysis.section_title')}</h3><p>{t('analysis.workflow')}</p><small>{scopeLabel}</small></div>
      <div className="analysis-actions">
        <button className="btn secondary" disabled={disabled || !!request || !status || status.importing || processing} onClick={preprocess}>
          {request === 'preprocess' ? <RefreshCw size={16} className="spin"/> : <ShieldCheck size={16}/>}
          {t('privacy.preprocess')}
        </button>
        <button className="btn primary" disabled={disabled || !!request || !status || !!error || status.importing || processing || status.waiting + status.failed === 0} onClick={start}>
          {request === 'analyze' || processing ? <RefreshCw size={16} className="spin"/> : <Sparkles size={16}/>}
          {t(processing ? 'analysis.processing' : 'analysis.start')}
        </button>
      </div>
    </div>
    {status && <div className="analysis-counts" aria-live="polite">
      <span>{t('analysis.waiting_count', { count: status.waiting })}</span>
      {!!status.preprocessing&&<span><LoaderCircle className="stage-spinner" size={13} aria-hidden="true"/>{t('analysis.preprocessing_count', { count: status.preprocessing })}</span>}
      {!!status.vlm_waiting&&<span><Clock3 size={13} aria-hidden="true"/>{t('analysis.vlm_waiting_count', { count: status.vlm_waiting })}</span>}
      {!!status.vlm_running&&<span><LoaderCircle className="stage-spinner" size={13} aria-hidden="true"/>{t('analysis.vlm_running_count', { count: status.vlm_running })}</span>}
      {status.preprocessing===undefined&&processing&&<span>{t('analysis.processing_count', { count: status.processing })}</span>}
      <span>{t('analysis.completed_count', { count: status.completed })}</span>
      {status.failed > 0 && <span className="red-text">{t('analysis.failed_count', { count: status.failed })}</span>}
    </div>}
    {status?.importing && <p role="status">{t('analysis.intake_in_progress')}</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p className="red-text" role="alert">{error}</p>}
  </section>
}
