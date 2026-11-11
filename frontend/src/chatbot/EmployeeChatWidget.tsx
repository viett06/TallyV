import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowUpRight, Bot, LoaderCircle, Send, X } from 'lucide-react'
import { employeeRequest, sessionExpired } from './employeeApi'

type Source = { id: number; filename: string; page_number: number; section: string; excerpt: string; url: string }
type Claim = { text: string; sources: Source[] }
type Turn = { question: string; claims: Claim[] }

const prompts = [
  'Các khoa phải gửi bảng chấm công khi nào?',
  'Mẫu đăng ký nghỉ phép năm 2026 ở trang nào?',
  'Nội quy quy định gì về trang phục khi làm việc?',
]

export function EmployeeChatWidget({ onExpired }: { onExpired: () => void }) {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const launcher = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const body = useRef<HTMLDivElement>(null)
  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => () => activeRequest.current?.abort(), [])
  useEffect(() => {
    if (!open) return
    input.current?.focus()
    function onEscape(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      event.preventDefault()
      setOpen(false)
      launcher.current?.focus()
    }
    window.addEventListener('keydown', onEscape)
    return () => window.removeEventListener('keydown', onEscape)
  }, [open])
  useEffect(() => {
    if (open && body.current) body.current.scrollTop = body.current.scrollHeight
  }, [turns, busy, open])

  function close() {
    setOpen(false)
    launcher.current?.focus()
  }

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const query = question.trim()
    if (query.length < 3 || busy) return
    const controller = new AbortController()
    activeRequest.current = controller
    setBusy(true)
    setError('')
    try {
      const answer = await employeeRequest<{ claims: Claim[] }>('/ask', { question: query }, controller.signal)
      if (controller.signal.aborted) return
      setTurns(current => [...current, { question: query, claims: answer.claims }])
      setQuestion('')
    } catch (cause) {
      if (controller.signal.aborted) return
      if (sessionExpired(cause)) onExpired()
      else setError((cause as Error).message)
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return (
    <div className="employee-chat">
      {open && (
        <section className="employee-chat-panel" id="employee-chat-panel" aria-label="Trợ lý tra cứu">
          <div className="employee-chat-header">
            <span className="employee-chat-avatar"><Bot size={23} aria-hidden="true" /></span>
            <div><h2>Trợ lý tra cứu</h2><p>Hỏi đáp từ kho văn bản</p></div>
            <button type="button" aria-label="Đóng trợ lý" onClick={close}><X size={20} /></button>
          </div>
          <div className="employee-chat-body" ref={body} aria-live="polite">
            {!turns.length && (
              <div className="employee-chat-welcome">
                <p>Bạn muốn tìm hiểu quy định nào?</p>
                {prompts.map(prompt => <button type="button" key={prompt} disabled={busy} onClick={() => {
                  setQuestion(prompt)
                  input.current?.focus()
                }}>{prompt}</button>)}
              </div>
            )}
            {turns.map((turn, index) => (
              <article className="employee-turn" key={index}>
                <p className="employee-question-bubble">{turn.question}</p>
                <div className="employee-chat-answer">
                  {!turn.claims.length ? <p>Kho tài liệu chưa có đủ căn cứ để trả lời câu hỏi này.</p> :
                    turn.claims.map((claim, claimIndex) => (
                      <div className="employee-claim" key={claimIndex}>
                        <p>{claim.text}</p>
                        {claim.sources.map(source => (
                          <div className="employee-source" key={source.id}>
                            <details>
                              <summary>{source.filename} · Trang {source.page_number}{source.section && ` · ${source.section}`}</summary>
                              <blockquote>{source.excerpt}</blockquote>
                            </details>
                            <a href={source.url} target="_blank" rel="noreferrer">Mở PDF tại trang {source.page_number}<ArrowUpRight size={14} /></a>
                          </div>
                        ))}
                      </div>
                    ))}
                </div>
              </article>
            ))}
            {busy && <p className="employee-chat-status" role="status"><LoaderCircle size={16} className="spin" />Đang tìm căn cứ…</p>}
            {error && <p className="employee-chat-error" role="alert">{error}</p>}
          </div>
          <form className="employee-chat-form" onSubmit={ask}>
            <textarea ref={input} aria-label="Câu hỏi cho trợ lý" value={question}
              onChange={event => setQuestion(event.target.value)} placeholder="Nhập câu hỏi của bạn…" maxLength={800} rows={2} required disabled={busy} />
            <button className="employee-primary" type="submit" aria-label="Gửi câu hỏi" disabled={busy || question.trim().length < 3}><Send size={18} /></button>
          </form>
        </section>
      )}
      <button ref={launcher} type="button" className="employee-chat-launcher" aria-label={open ? 'Đóng trợ lý tra cứu' : 'Mở trợ lý tra cứu'}
        aria-expanded={open} aria-controls={open ? 'employee-chat-panel' : undefined} onClick={() => open ? close() : setOpen(true)}>
        {open ? <X size={25} /> : <Bot size={29} />}
      </button>
    </div>
  )
}
