import { useState } from 'react'
import { ChevronLeft, ChevronRight, FileSpreadsheet, Layers, Mail, RefreshCw, Search, Sparkles } from 'lucide-react'
import { t } from '../i18n'
import './JobsQueue.css'

export type ProcessingJob = {
  id: number
  kind: string
  key: string
  payload: Record<string, any>
  status: string
  attempts: number
  max_attempts: number
  error: string | null
}

const groups = [
  { id: 'SYNC', title: 'jobs.group_sync', description: 'jobs.group_sync_description', icon: Mail },
  { id: 'IMPORT_EMAIL', title: 'jobs.group_import', description: 'jobs.group_import_description', icon: FileSpreadsheet },
  { id: 'ANALYZE', title: 'jobs.group_analysis', description: 'jobs.group_analysis_description', icon: Sparkles },
  { id: 'OTHER', title: 'jobs.group_other', description: 'jobs.group_other_description', icon: Layers },
] as const
type GroupId = typeof groups[number]['id']
const statuses = [
  { id: '', title: 'jobs.filter_all' },
  { id: 'PENDING', title: 'processing.pending' },
  { id: 'RUNNING', title: 'processing.running' },
  { id: 'FAILED', title: 'processing.failed' },
  { id: 'DONE', title: 'processing.done' },
] as const
const pageSize = 8
const groupOf = (job: ProcessingJob): GroupId =>
  job.kind === 'SYNC' || job.kind === 'IMPORT_EMAIL' || job.kind === 'ANALYZE' ? job.kind : 'OTHER'
const priority: Record<string, number> = { RUNNING: 0, PENDING: 1, FAILED: 2, DONE: 3 }

function jobTitle(job: ProcessingJob) {
  if (job.kind === 'IMPORT_EMAIL') return t('jobs.reference_email', { id: job.payload.email_id })
  if (job.kind === 'ANALYZE') return t('jobs.reference_version', { id: job.payload.version_id })
  if (job.kind === 'SYNC') return t('jobs.sync_reference')
  if (job.kind === 'DEMO') return t('jobs.send_demo_mail')
  if (job.kind === 'HR_SUBMIT') return t('integration.hr_submit_job')
  return job.kind
}

export function JobsQueue({ jobs, busy, onRetry }: {
  jobs: ProcessingJob[]; busy: boolean; onRetry: (id: number) => Promise<void>
}) {
  const [group, setGroup] = useState<GroupId>(() => {
    const recent = jobs.find(job => job.status === 'RUNNING' || job.status === 'PENDING') || jobs[0]
    return recent ? groupOf(recent) : 'SYNC'
  })
  const [status, setStatus] = useState(''), [search, setSearch] = useState(''), [page, setPage] = useState(1)
  const category = groups.find(item => item.id === group)!
  const groupJobs = jobs.filter(job => groupOf(job) === group)
  const needle = search.trim().toLocaleLowerCase('vi-VN')
  const filtered = groupJobs
    .filter(job => (!status || job.status === status) && (!needle ||
      `#${job.id} ${job.key} ${jobTitle(job)} ${job.error || ''}`.toLocaleLowerCase('vi-VN').includes(needle)))
    .sort((a, b) => (priority[a.status] ?? 4) - (priority[b.status] ?? 4) || b.id - a.id)
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const currentPage = Math.min(page, pages)
  const visible = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const processing = jobs.filter(job => job.status === 'PENDING' || job.status === 'RUNNING').length
  const failed = jobs.filter(job => job.status === 'FAILED').length

  return <section className="jobs-queue" aria-label={t('jobs.queue_title')}>
    <div className="jobs-introduction">
      <div><h2>{t('jobs.queue_title')}</h2><p>{t('jobs.grouped_description')}</p></div>
      <div className="jobs-overall" aria-live="polite"><span className="chip">{t('jobs.processing_count', { count: processing })}</span>{failed > 0 && <span className="badge b-FAILED">{t('jobs.failed_count', { count: failed })}</span>}</div>
    </div>
    <div className="job-categories" role="group" aria-label={t('jobs.category_label')}>
      {groups.map(item => {
        const items = jobs.filter(job => groupOf(job) === item.id)
        const pending = items.filter(job => job.status === 'PENDING').length
        const running = items.filter(job => job.status === 'RUNNING').length
        const errors = items.filter(job => job.status === 'FAILED').length
        const done = items.filter(job => job.status === 'DONE').length
        return <button key={item.id} className={'job-category ' + (group === item.id ? 'selected' : '')} aria-pressed={group === item.id} onClick={() => { setGroup(item.id); setPage(1); setSearch('') }}>
          <span className="job-category-heading"><span className="job-category-icon"><item.icon size={20}/></span><strong>{t(item.title)}</strong><span className="job-category-total">{items.length}</span></span>
          <span className="job-category-description">{t(item.description)}</span>
          <span className="job-category-counts"><span>{t('jobs.waiting_count', { count: pending })}</span><span>{t('jobs.running_count', { count: running })}</span><span className={errors ? 'has-errors' : ''}>{t('jobs.error_count', { count: errors })}</span><span>{t('jobs.done_count', { count: done })}</span></span>
        </button>
      })}
    </div>
    <section className="panel job-list" aria-label={t(category.title)}>
      <div className="panel-heading"><div><h3>{t(category.title)}<span className="count-label">{groupJobs.length}</span></h3><p>{t('jobs.retry_policy')}</p></div></div>
      <div className="job-list-controls">
        <div className="job-status-filters" role="group" aria-label={t('jobs.status_filter_label')}>
          {statuses.map(item => <button key={item.id} className={status === item.id ? 'active' : ''} aria-pressed={status === item.id} onClick={() => { setStatus(item.id); setPage(1) }}>{t(item.title)}<span>{item.id ? groupJobs.filter(job => job.status === item.id).length : groupJobs.length}</span></button>)}
        </div>
        <label className="job-search"><Search size={16}/><input aria-label={t('jobs.search_label')} placeholder={t('jobs.search_placeholder')} value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}/></label>
      </div>
      <div className="table-scroll"><table className="grouped-jobs-table"><thead><tr><th>{t('jobs.identifier_column')}</th><th>{t('jobs.reference_column')}</th><th>{t('jobs.status_column')}</th><th>{t('jobs.attempts_column')}</th><th>{t('jobs.message_column')}</th><th><span className="sr-only">{t('jobs.actions_column')}</span></th></tr></thead>
        <tbody>{visible.map(job => <tr key={job.id}>
          <td><strong>#{job.id}</strong></td>
          <td><strong>{jobTitle(job)}</strong><details className="job-reference"><summary>{t('jobs.technical_reference')}</summary><code>{job.key}</code></details>{job.kind === 'SYNC' && job.payload.summary && <small>{t('jobs.scan_summary', { scanned: job.payload.summary.scanned || 0, received: job.payload.summary.new || 0 })}</small>}</td>
          <td><span className={'badge b-' + job.status}>{t(statuses.find(item => item.id === job.status)?.title || 'jobs.unknown_status')}</span></td>
          <td><span className="job-attempts" title={t('jobs.attempts_description', { count: job.attempts, max: job.max_attempts })}>{job.attempts}<span> / {job.max_attempts}</span></span></td>
          <td><span className={'job-message ' + (job.error ? 'red-text' : '')}>{job.error || '—'}</span></td>
          <td>{job.status === 'FAILED' && <button className="btn secondary small-btn" disabled={busy} onClick={() => onRetry(job.id)} aria-label={t('jobs.retry_task', { id: job.id })}><RefreshCw size={13}/>{t('actions.retry')}</button>}</td>
        </tr>)}</tbody></table></div>
      {!visible.length && <div className="job-empty"><category.icon size={28}/><strong>{t(groupJobs.length ? 'jobs.empty_filter' : 'jobs.empty_category')}</strong><p>{t(groupJobs.length ? 'jobs.empty_filter_hint' : 'jobs.empty_category_hint')}</p></div>}
      <div className="job-pagination"><span aria-live="polite">{t('jobs.page_range', { from: filtered.length ? (currentPage - 1) * pageSize + 1 : 0, to: Math.min(currentPage * pageSize, filtered.length), total: filtered.length })}</span><div><button className="icon-btn" aria-label={t('actions.previous_page')} disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16}/></button><span>{t('jobs.page_number', { current: currentPage, total: pages })}</span><button className="icon-btn" aria-label={t('actions.next_page')} disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16}/></button></div></div>
    </section>
    <p className="jobs-scope-note">{t('jobs.scope_note')}</p>
  </section>
}
