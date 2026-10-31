import { useEffect, useState } from 'react'
import { Mail, ShieldCheck, X } from 'lucide-react'
import { t } from '../i18n'
import { MailboxScan, type ScanStatus } from './MailboxScan'
import { AnalysisControls } from './AnalysisControls'

type Department = { id: number; name: string; senders: string[] }
type DepartmentDraft = Department & { addresses: string }
type MailboxStatus = ScanStatus & { transport: 'microsoft' | 'composio'; connected_transport: string | null; configured: boolean; status: string; mailbox: string; connected_at: string | null; last_synced_at: string | null; redirect_uri: string; sync_days: number; test_mode: boolean }
type Api = (path: string, options?: RequestInit) => Promise<any>
const draft = (department: Department): DepartmentDraft => ({ ...department, addresses: department.senders.join('\n') })
const senderList = (addresses: string) => {
  const values=addresses.split(/[,;\n]+/).map(address=>address.trim()).filter(Boolean)
  if(values.length>50||values.some(address=>address.length>200||! /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)))throw new Error(t('outlook.invalid_senders'))
  return values
}

export function OutlookSettings({ api, departments, refresh, onClose, onView }: {
  api: Api; departments: Department[]; refresh: () => Promise<void>; onClose: () => void; onView: (page: 'inbox' | 'cases') => void
}) {
  const [status, setStatus] = useState<MailboxStatus | null>(null)
  const [drafts, setDrafts] = useState(departments.map(draft))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [statusError, setStatusError] = useState('')
  const [notice, setNotice] = useState('')
  const [newDepartment, setNewDepartment] = useState({name:'',addresses:''})
  useEffect(() => {
    let active = true
    const load = async () => {
      try { const value = await api('/outlook'); if(active){setStatus(value);setStatusError('')} }
      catch (error: any) { if(active)setStatusError(error.message) }
    }
    load()
    const timer = window.setInterval(load, 4000)
    window.addEventListener('focus', load)
    return () => { active = false; window.clearInterval(timer); window.removeEventListener('focus', load) }
  }, [api])
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await action() }
    catch (error: any) { setError(error.message) }
    finally {
      try { setStatus(await api('/outlook')); await refresh() }
      catch (error: any) { setError(error.message) }
      setBusy(false)
    }
  }
  const expectedOrigin = status ? new URL(status.redirect_uri).origin : ''
  const connected = status?.status === 'CONNECTED'
  const syncing = status?.sync_status === 'PENDING' || status?.sync_status === 'RUNNING'
  return <div className="modal-backdrop centered" onClick={onClose}>
    <section className="mailbox-dialog" role="dialog" aria-modal="true" aria-label={t('outlook.settings')} onClick={event => event.stopPropagation()}>
      <header><div><h2><Mail size={21}/>{t('outlook.settings')}</h2><p>{t('outlook.description')}</p></div><button className="icon-btn" onClick={onClose} aria-label={t('actions.close_email')}><X/></button></header>
      <div className="mailbox-content">
        {(error||statusError)&&<div className="alert error" role="alert">{error||statusError}</div>}
        {notice&&<div className="alert success" role="status">{notice}</div>}
        {status?.transport==='composio'&&<div className="outlook-setup"><h3>{t('composio.mvp_title')}</h3><p>{t('composio.mvp_description')}</p><small>{t('composio.permission_boundary')}</small></div>}
        <section className="mailbox-connection">
          <ShieldCheck size={25}/><div><h3 role="status">{t(connected?'outlook.connected':status?.status==='REAUTH_REQUIRED'?'outlook.reauth_required':'outlook.not_connected')}</h3>
          {status?.mailbox&&status.status!=='DISCONNECTED'&&<p><strong>{status.mailbox}</strong></p>}
          <p>{t('outlook.read_only')}</p>
          {status?.status === 'REAUTH_REQUIRED'&&<p className="red-text">{t('outlook.reconnect')}</p>}
          {connected&&status?.sync_error&&<p className="red-text" role="alert">{t('outlook.sync_error',{error:status.sync_error})}</p>}
          {connected&&syncing&&!status?.sync_error&&<small role="status">{t('outlook.sync_in_progress')}</small>}
          {connected&&status?.connected_at&&<small>{t('outlook.connected_since',{date:new Date(status.connected_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})})}</small>}
          {status&&<small>{t('outlook.sync_window',{days:status.sync_days})}</small>}
          {status?.transport==='composio'&&<small>{t('composio.sync_notice')}</small>}
          {status?.last_synced_at&&<small>{t('outlook.last_sync',{date:new Date(status.last_synced_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})})}</small>}
          </div>
        </section>
        {connected&&status&&<MailboxScan status={status} defaultDays={status.sync_days} disabled={busy} onScan={(mode,days)=>run(async()=>{await api('/sync',{method:'POST',body:JSON.stringify({mode,lookback_days:days})});setNotice(t('notices.sync_queued'))})} onView={onView}/>}
        {connected && <AnalysisControls api={api} query="source=outlook" onUpdated={refresh} scopeLabel={t('analysis.scope_outlook')} disabled={busy}/>}
        {status?.status==='CONNECTED'&&status.connected_transport!==status.transport&&<div className="alert">{t('composio.transport_changed')}</div>}
        {status&&!status.configured&&<div className="outlook-setup"><h3>{t(status.transport==='composio'?'composio.setup_title':'outlook.setup_title')}</h3><p>{t(status.transport==='composio'?'composio.setup_description':'outlook.setup_description')}</p></div>}
        {status?.configured&&expectedOrigin!==window.location.origin&&<div className="alert">{t('outlook.open_origin')} <a href={expectedOrigin}>{expectedOrigin}</a></div>}
        <div className="button-row">
          {connected?<button className="btn secondary" disabled={busy||syncing} onClick={()=>run(async()=>{await api('/outlook/disconnect',{method:'POST'});setNotice(t('outlook.disconnected'))})}>{t('outlook.disconnect')}</button>:
            <button className="btn primary" disabled={busy||!status?.configured||expectedOrigin!==window.location.origin} onClick={()=>run(async()=>{const result=await api('/outlook/connect',{method:'POST'});window.location.assign(result.authorization_url)})}>{t(status?.transport==='composio'?'composio.sign_in':'outlook.microsoft_sign_in')}</button>}
        </div>
        {status?.test_mode&&<details className="outlook-test-notice"><summary>{t('outlook.test_title')}</summary><p>{t('outlook.test_description')}</p><p>{t('outlook.test_subject')}</p></details>}
        <section className="mailbox-catalog"><h3>{t('outlook.departments')}</h3><p>{t(status?.test_mode?'outlook.test_department_hint':'outlook.department_hint')}</p><a className="text-btn" href="/api/workbooks/template">{t('outlook.workbook_template')}</a>
          {drafts.map((department,index)=><form key={department.id} className="sender-row" onSubmit={event=>{event.preventDefault();run(async()=>{const result=await api('/departments/'+department.id,{method:'PUT',body:JSON.stringify({name:department.name,senders:senderList(department.addresses)})});setDrafts(drafts.map(row=>row.id===result.id?draft(result):row));setNotice(t('outlook.mapping_saved'))})}}>
            <span>#{department.id}</span><input aria-label={t('outlook.department_name',{id:department.id})} required maxLength={100} value={department.name} onChange={event=>setDrafts(drafts.map((row,position)=>position===index?{...row,name:event.target.value}:row))}/>
            <textarea aria-label={t('outlook.department_sender',{id:department.id})} rows={2} placeholder={t('outlook.multiple_senders_hint')} value={department.addresses} onChange={event=>setDrafts(drafts.map((row,position)=>position===index?{...row,addresses:event.target.value}:row))}/>
            <button className="btn secondary small-btn" disabled={busy}>{t('outlook.save')}</button>
          </form>)}
          <form className="sender-row" onSubmit={event=>{event.preventDefault();run(async()=>{const result=await api('/departments',{method:'POST',body:JSON.stringify({name:newDepartment.name,senders:senderList(newDepartment.addresses)})});setDrafts([...drafts,draft(result)]);setNewDepartment({name:'',addresses:''});setNotice(t('outlook.mapping_saved'))})}}><span>+</span><input required maxLength={100} aria-label={t('outlook.new_department_name')} placeholder={t('outlook.new_department_name')} value={newDepartment.name} onChange={event=>setNewDepartment({...newDepartment,name:event.target.value})}/><textarea rows={2} aria-label={t('outlook.new_department_sender')} placeholder={t('outlook.multiple_senders_hint')} value={newDepartment.addresses} onChange={event=>setNewDepartment({...newDepartment,addresses:event.target.value})}/><button className="btn secondary small-btn" disabled={busy}>{t('outlook.add_department')}</button></form>
        </section>
        <section className="mailbox-catalog"><h3>{t('outlook.employees')}</h3><p>{t(status?.test_mode?'outlook.test_employee_hint':'outlook.employee_hint')}</p><div className="button-row"><a className="btn secondary small-btn" href="/api/employees/template">{t('outlook.employee_template')}</a><label className="btn secondary small-btn">{t('outlook.employee_upload')}<input className="visually-hidden" type="file" accept=".csv,text/csv" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(!file)return;run(async()=>{if(file.size>1024*1024)throw new Error(t('outlook.csv_too_large'));const result=await api('/employees/import',{method:'POST',headers:{'Content-Type':'text/csv'},body:file});setNotice(t('outlook.employees_imported',{count:result.imported}))});event.target.value=''}}/></label></div></section>
      </div>
    </section>
  </div>
}
