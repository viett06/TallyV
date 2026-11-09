import { useState, type FormEvent } from 'react'
import { t } from '../i18n'
import { calendarDate, type ReviewMonth } from './ReviewSchedule'

export function ManualCaseDialog({months, selectedCycle, initialDate, busy, onClose, onSave}: {
  months: ReviewMonth[]
  selectedCycle: string
  initialDate: string
  busy: boolean
  onClose: () => void
  onSave: (data: FormData) => void
}) {
  const [workDate, setWorkDate] = useState(initialDate)
  const [cycle, setCycle] = useState(selectedCycle)
  const [fileError, setFileError] = useState('')
  const month = months.find(item => item.starts <= workDate && workDate <= item.ends)
  const round = month?.cycles.some(item => item.id === cycle) ? cycle : ''

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const files = data.getAll('evidence').filter((file): file is File => file instanceof File && Boolean(file.name))
    if (files.length > 5 || files.some(file => file.size > 8 * 1024 * 1024)) {
      setFileError(t('cases.manual_evidence_limit'))
      return
    }
    data.delete('evidence')
    files.forEach(file => data.append('evidence', file))
    if (!round) data.delete('cycle_start')
    onSave(data)
  }

  return <div className="modal-backdrop centered" onClick={onClose}>
    <form className="confirm-modal case-form" role="dialog" aria-modal="true" aria-labelledby="manual-case-title"
      onClick={event => event.stopPropagation()} onSubmit={submit}>
      <h2 id="manual-case-title">{t('cases.manual_title')}</h2>
      <fieldset disabled={busy}>
        <div className="form-grid">
          <label>{t('fields.employee_code')}<input name="employee_id" maxLength={30} required autoFocus /></label>
          <label>{t('fields.occurrence_date')}<input name="work_date" type="date" value={workDate}
            onChange={event => setWorkDate(event.target.value)} required /></label>
          <label>{t('calendar.cycle_filter')}<select name="cycle_start" value={round}
            onChange={event => setCycle(event.target.value)}>
            <option value="">{t('calendar.unassigned')}</option>
            {month?.cycles.map(item => <option key={item.id} value={item.id}>{calendarDate(item.send_on)}</option>)}
          </select></label>
          <label>{t('fields.shift')}<input name="shift" maxLength={120} placeholder="08:00–16:00" /></label>
          <label>{t('fields.missing_punch')}<select name="punch" defaultValue="">
            <option value="">{t('common.not_provided')}</option>
            <option value="IN">{t('cases.punch_in')}</option>
            <option value="OUT">{t('cases.punch_out')}</option>
            <option value="NA">{t('cases.punch_na')}</option>
          </select></label>
        </div>
        <p className="muted">{t('cases.manual_employee_hint')}</p>
        <label>{t('fields.explanation')}<textarea name="explanation" rows={3} maxLength={2000} required /></label>
        <label>{t('cases.manual_evidence')}<input name="evidence" type="file" accept="image/*" multiple
          onChange={() => setFileError('')} /></label>
        <small className="muted">{t('cases.manual_evidence_hint')}</small>
      </fieldset>
      {fileError && <p className="red-text" role="alert">{fileError}</p>}
      <div className="button-row">
        <button type="button" className="btn secondary" disabled={busy} onClick={onClose}>{t('actions.cancel')}</button>
        <button className="btn primary" disabled={busy}>{t('cases.create_submit')}</button>
      </div>
    </form>
  </div>
}
