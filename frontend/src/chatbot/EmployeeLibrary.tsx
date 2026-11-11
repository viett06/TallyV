import { useEffect, useState, type FormEvent } from 'react'
import { ArrowUpRight, ChevronLeft, ChevronRight, FileText, Search, SlidersHorizontal, X } from 'lucide-react'
import { documentTypes } from './documentTypes'
import { employeeRequest, sessionExpired } from './employeeApi'

type Document = {
  id: number; title: string; filename: string; issuer: string | null
  document_type: string; page_count: number; url: string
}
type Match = {
  document: Document; page_number: number; match_count: number
  snippets: [string, boolean][][]; url: string
}
type Library = { catalog: Document[]; documents: Document[]; hits: Match[]; total_hits: number; page_size: number }

function DocumentIcon() {
  return <span className="employee-file-icon" aria-hidden="true"><FileText size={22} strokeWidth={1.6} /></span>
}

export function EmployeeLibrary({ onExpired }: { onExpired: () => void }) {
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState({ keyword: '', type: '', document: '', page: 1 })
  const [library, setLibrary] = useState<Library | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const { keyword, type, document, page } = search

  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({ q: keyword, page: String(page) })
    if (type) params.set('document_type', type)
    if (document) params.set('document_id', document)
    setLoading(true)
    setError('')
    employeeRequest<Library>('/library?' + params, undefined, controller.signal)
      .then(result => { if (!controller.signal.aborted) setLibrary(result) })
      .catch((cause: Error) => {
        if (controller.signal.aborted) return
        if (sessionExpired(cause)) onExpired()
        else setError(cause.message)
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [keyword, type, document, page, onExpired])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSearch(current => ({ ...current, keyword: draft.trim(), page: 1 }))
  }

  function reset() {
    setDraft('')
    setSearch({ keyword: '', type: '', document: '', page: 1 })
  }

  const categories = Object.entries(documentTypes)
    .map(([id, label]) => ({ id, label, count: library?.catalog.filter(item => item.document_type === id).length ?? 0 }))
    .filter(category => category.count > 0)
  const pageCount = library ? Math.ceil(library.total_hits / library.page_size) : 0
  const resultsTitle = keyword ? 'Kết quả tìm kiếm' : 'Danh mục tài liệu'

  return (
    <section className="employee-library">
      <div className="employee-search-card">
        <form onSubmit={submit} className="employee-search-form">
          <label htmlFor="employee-library-keyword">Tìm trong nội dung văn bản</label>
          <div className="employee-search-row">
            <div className="employee-search-input">
              <Search size={20} aria-hidden="true" />
              <input id="employee-library-keyword" value={draft} maxLength={120} onChange={event => setDraft(event.target.value)}
                placeholder="Ví dụ: chấm công…" />
              {draft && <button type="button" aria-label="Xóa từ khóa" onClick={() => {
                setDraft('')
                setSearch(current => ({ ...current, keyword: '', page: 1 }))
              }}><X size={17} /></button>}
            </div>
            <button className="employee-primary" type="submit"><Search size={17} />Tìm kiếm</button>
          </div>
        </form>
        <div className="employee-filter-row">
          <div className="employee-categories" aria-label="Lọc theo loại văn bản">
            {[{ id: '', label: 'Tất cả', count: library?.catalog.length ?? 0 }, ...categories].map(category => (
              <button type="button" key={category.id} aria-pressed={type === category.id}
                onClick={() => setSearch(current => ({ ...current, type: category.id, document: '', page: 1 }))}>
                {category.label} <span>{category.count}</span>
              </button>
            ))}
          </div>
          <label className="employee-doc-filter">
            <SlidersHorizontal size={16} aria-hidden="true" />
            <select aria-label="Lọc theo tài liệu" value={document}
              onChange={event => setSearch(current => ({ ...current, document: event.target.value, page: 1 }))}>
              <option value="">Tất cả tài liệu</option>
              {library?.catalog.filter(item => !type || item.document_type === type).map(item =>
                <option key={item.id} value={item.id}>{item.title}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="employee-results-heading">
        <div>
          <h2>{resultsTitle}</h2>
          {!loading && !error && library && (
            <p>{keyword ? `${library.total_hits} trang khớp với “${keyword}”` : `${library.documents.length} tài liệu`}</p>
          )}
        </div>
        {(keyword || type || document) && <button className="employee-text-button" type="button" onClick={reset}>Xóa bộ lọc</button>}
      </div>

      {loading ? <div className="employee-state" role="status">Đang tải tài liệu…</div>
        : error ? <div className="employee-state" role="alert">{error}</div>
        : keyword ? library?.hits.length ? (
          <div className="employee-document-list">
            {library.hits.map(hit => (
              <article className="employee-document employee-hit" key={`${hit.document.id}-${hit.page_number}`}>
                <DocumentIcon />
                <div className="employee-document-info">
                  <div className="employee-doc-meta">{documentTypes[hit.document.document_type]}<span>Trang {hit.page_number}</span></div>
                  <h3><a href={hit.url} target="_blank" rel="noreferrer">{hit.document.title}</a></h3>
                  {hit.document.issuer && <p>{hit.document.issuer}</p>}
                  <div className="employee-snippets">
                    {hit.snippets.map((snippet, index) => <p key={index}>
                      {snippet.map(([part, highlighted], partIndex) => highlighted
                        ? <mark key={partIndex}>{part}</mark> : part)}
                    </p>)}
                  </div>
                </div>
                <a className="employee-open-doc" href={hit.url} target="_blank" rel="noreferrer">Mở trang {hit.page_number}<ArrowUpRight size={17} /></a>
              </article>
            ))}
          </div>
        ) : <div className="employee-state">Không tìm thấy đoạn văn bản khớp với từ khóa này.</div>
        : library?.documents.length ? (
          <div className="employee-document-list">
            {library.documents.map(item => (
              <article className="employee-document" key={item.id}>
                <DocumentIcon />
                <div className="employee-document-info">
                  <div className="employee-doc-meta">{documentTypes[item.document_type]}</div>
                  <h3><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></h3>
                  {item.issuer && <p>{item.issuer}</p>}
                </div>
                <span className="employee-page-count">{item.page_count} trang</span>
                <a className="employee-open-doc" href={item.url} target="_blank" rel="noreferrer">Xem PDF<ArrowUpRight size={17} /></a>
              </article>
            ))}
          </div>
        ) : <div className="employee-state">Chưa có tài liệu trong danh mục này.</div>}
      {!loading && !error && keyword && pageCount > 1 && (
        <nav className="employee-pagination" aria-label="Phân trang kết quả">
          <button type="button" aria-label="Trang kết quả trước" disabled={page <= 1}
            onClick={() => setSearch(current => ({ ...current, page: page - 1 }))}><ChevronLeft size={18} /></button>
          <span>Trang {page} / {pageCount}</span>
          <button type="button" aria-label="Trang kết quả sau" disabled={page >= pageCount}
            onClick={() => setSearch(current => ({ ...current, page: page + 1 }))}><ChevronRight size={18} /></button>
        </nav>
      )}
    </section>
  )
}
