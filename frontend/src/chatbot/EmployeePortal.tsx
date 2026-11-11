import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, BookOpen, ChevronRight, LogOut, UserRound } from 'lucide-react'
import vinmecLogo from './assets/vinmec.png'
import { EmployeeChatWidget } from './EmployeeChatWidget'
import { EmployeeLibrary } from './EmployeeLibrary'
import { employeeRequest } from './employeeApi'
import './employee.css'

type User = { username: string }

export function EmployeePortal() {
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const expire = useCallback(() => {
    setUser(null)
    setError('Phiên đăng nhập đã hết. Vui lòng đăng nhập lại.')
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    employeeRequest<User>('/me', undefined, controller.signal).then(setUser).catch((cause: Error) => {
      if (controller.signal.aborted) return
      if (cause.cause !== 401) setError(cause.message)
      setUser(null)
    })
    return () => controller.abort()
  }, [])

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      setUser(await employeeRequest<User>('/login', { username: fields.get('username'), password: fields.get('password') }))
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    setBusy(true)
    setError('')
    try {
      await employeeRequest('/logout', {})
      setUser(null)
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="employee-portal">
      <header className="employee-bar">
        <div className="employee-frame employee-bar-inner">
          <a href="/employee" className="employee-brand">
            <img src={vinmecLogo} alt="Vinmec" width="82" height="51" />
            <span>Cổng nhân viên</span>
          </a>
          {user && <div className="employee-account">
            <span className="employee-avatar"><UserRound size={17} aria-hidden="true" /></span>
            <span className="employee-account-name">{user.username}</span>
            <button type="button" onClick={logout} disabled={busy} aria-label="Đăng xuất" title="Đăng xuất"><LogOut size={18} /></button>
          </div>}
        </div>
      </header>

      <main>
        <div className="employee-hero">
          <div className="employee-frame employee-hero-inner">
            <div>
              <div className="employee-breadcrumb">Cổng nhân viên <ChevronRight size={14} /> Cẩm nang thông tin</div>
              <h1>Cẩm nang thông tin</h1>
              <p>Tra cứu nội quy, quy chế và văn bản dành cho cán bộ nhân viên.</p>
            </div>
            <div className="employee-hero-icon" aria-hidden="true"><BookOpen size={76} strokeWidth={1.15} /></div>
          </div>
        </div>
        <div className="employee-frame employee-content">
          {error && <p className="employee-state employee-chat-error" role="alert">{error}</p>}
          {user === undefined ? <p className="employee-state" role="status">Đang kiểm tra phiên đăng nhập…</p> : !user ? (
            <form className="employee-login" onSubmit={login}>
              <h2>Đăng nhập dành cho nhân viên</h2>
              <label>Tên tài khoản<input name="username" required maxLength={80} autoComplete="username" /></label>
              <label>Mật khẩu<input name="password" required maxLength={200} type="password" autoComplete="current-password" /></label>
              <button className="employee-primary" disabled={busy}>{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}<ArrowRight size={17} /></button>
            </form>
          ) : <EmployeeLibrary onExpired={expire} />}
        </div>
      </main>
      <footer className="employee-footer">
        <div className="employee-frame"><strong>Cẩm nang nhân viên</strong><span>TallyV</span></div>
      </footer>
      {user && <EmployeeChatWidget onExpired={expire} />}
    </div>
  )
}
