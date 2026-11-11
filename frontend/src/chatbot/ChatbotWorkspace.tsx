import { useEffect, useState, type FormEvent } from 'react'
import { ExternalLink, FileText, Upload } from 'lucide-react'
import { t } from '../i18n'
import { documentTypes } from './documentTypes'

type PolicyDocument = {
  id: number
  filename: string
  page_count: number
  ocr_page_count: number
  chunk_count: number
  published: boolean
}

type UploadResult = { document: PolicyDocument; created: boolean }

async function request<T>(options?: RequestInit, suffix = ''): Promise<T> {
  const response = await fetch('/api/chatbot/documents' + suffix, options)
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : t('errors.request_failed'))
  }
  return response.json()
}

export function ChatbotWorkspace() {
  const [documents, setDocuments] = useState<PolicyDocument[] | null>(null)
  const [uploading, setUploading] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    request<PolicyDocument[]>({ signal: controller.signal })
      .then(setDocuments)
      .catch((cause: Error) => {
        if (!controller.signal.aborted) setError(cause.message)
      })
    return () => controller.abort()
  }, [])

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const payload = new FormData(form)
    const file = payload.get('file')
    setError('')
    setNotice('')
    if (!(file instanceof File) || file.size === 0) return
    if (file.size > 20 * 1024 * 1024) {
      setError(t('policy.limit_error'))
      return
    }

    setUploading(true)
    try {
      const { document, created } = await request<UploadResult>({ method: 'POST', body: payload })
      setDocuments(await request<PolicyDocument[]>())
      setNotice(t(created ? 'policy.uploaded' : 'policy.duplicate', { filename: document.filename }))
      form.reset()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('errors.request_failed'))
    } finally {
      setUploading(false)
    }
  }

  async function changePublication(document: PolicyDocument) {
    setPublishing(true)
    setError('')
    setNotice('')
    try {
      const updated = await request<PolicyDocument>({
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ published: !document.published }),
      }, `/${document.id}`)
      setDocuments(current => current?.map(row => row.id === updated.id ? updated : row) ?? null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('errors.request_failed'))
    } finally {
      setPublishing(false)
    }
  }

  return (
    <section className="panel" aria-label={t('policy.workspace')}>
      <div className="panel-heading">
        <div>
          <h2>{t('policy.upload_title')}</h2>
          <p>{t('policy.limits')}</p>
        </div>
        <a className="btn secondary" href="/employee" target="_blank" rel="noreferrer">Cổng nhân viên <ExternalLink size={14} /></a>
      </div>
      <form className="table-toolbar" onSubmit={upload} aria-busy={uploading}>
        <label>
          {t('policy.choose_file')}
          <input name="file" type="file" accept=".pdf,application/pdf" required disabled={uploading} />
        </label>
        <label>Tên hiển thị <input name="title" maxLength={255} placeholder="Tên văn bản" disabled={uploading} /></label>
        <label>Đơn vị ban hành <input name="issuer" maxLength={160} placeholder="Tên bệnh viện hoặc đơn vị" disabled={uploading} /></label>
        <label>Loại văn bản
          <select name="document_type" defaultValue="other" disabled={uploading}>
            {Object.entries(documentTypes).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <button className="btn primary" disabled={uploading}>
          <Upload size={16} aria-hidden="true" />
          {t(uploading ? 'policy.processing' : 'policy.upload')}
        </button>
      </form>
      {error && <div className="alert error" role="alert">{error}</div>}
      {notice && <div className="alert success" role="status">{notice}</div>}
      {documents?.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t('policy.filename')}</th>
                <th>{t('policy.pages')}</th>
                <th>{t('policy.ocr_pages')}</th>
                <th>{t('policy.chunks')}</th>
                <th>{t('policy.source')}</th>
                <th>Tra cứu của nhân viên</th>
              </tr>
            </thead>
            <tbody>
              {documents.map(document => (
                <tr key={document.id}>
                  <td><FileText size={16} aria-hidden="true" /> {document.filename}</td>
                  <td>{document.page_count}</td>
                  <td>{document.ocr_page_count}</td>
                  <td>{document.chunk_count}</td>
                  <td>
                    <a
                      className="btn secondary small-btn"
                      href={`/api/chatbot/documents/${document.id}/pdf#page=1`}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={t('policy.open_named_pdf', { filename: document.filename })}
                    >
                      {t('policy.open_pdf')} <ExternalLink size={14} aria-hidden="true" />
                    </a>
                  </td>
                  <td>
                    <button type="button" className="btn secondary small-btn"
                      disabled={publishing || uploading} onClick={() => changePublication(document)}>
                      {document.published ? 'Gỡ công bố' : 'Công bố'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty" role="status">{documents ? t('policy.empty') : !error && t('app.loading')}</div>
      )}
    </section>
  )
}
