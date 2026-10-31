import { t } from '../i18n'

export type ReviewCycle = {
  id: string
  number: number
  send_on: string
  due_on: string
  state: 'UPCOMING' | 'COLLECTING' | 'DUE_TODAY' | 'CLOSED'
}

export type ReviewMonth = {
  id: string
  name: string
  starts: string
  ends: string
  cycles: ReviewCycle[]
  saturday_count: number
  monday_count: number
  carryover: { period_id: string; send_on: string; due_on: string } | null
}

export function calendarDate(value: string): string {
  return value.split('-').reverse().join('/')
}

export function cycleReference(value: string | null): string {
  return value ? t('calendar.request_reference', { date: calendarDate(value) }) : t('calendar.unassigned')
}

export function ReviewSchedule({ month, today, selected, onSelect, onOpenCarryover }: {
  month: ReviewMonth
  today: string
  selected: string
  onSelect: (cycle: string) => void
  onOpenCarryover: (period: string, cycle: string) => void
}) {
  const stateLabels = {
    UPCOMING: t('calendar.upcoming'), COLLECTING: t('calendar.collecting'),
    DUE_TODAY: t('calendar.due_today'), CLOSED: t('calendar.closed'),
  }
  return <section className="review-calendar" aria-label={t('calendar.title')}>
    <div className="calendar-heading">
      <div><h2>{t('calendar.title')}</h2><p>{t('calendar.period_range', { start:calendarDate(month.starts), end:calendarDate(month.ends) })}</p><p>{t('calendar.month_counts', { saturdays: month.saturday_count, mondays: month.monday_count })}</p></div>
      <span>{t('calendar.today', { date: calendarDate(today) })}</span>
    </div>
    <div className="calendar-cycles">{month.cycles.map(cycle =>
      <button key={cycle.id} type="button" className={'calendar-cycle ' + cycle.state.toLowerCase() + (selected === cycle.id ? ' selected' : '')}
        aria-pressed={selected === cycle.id} onClick={() => onSelect(selected === cycle.id ? '' : cycle.id)}>
        <span className="cycle-heading"><strong>{t('calendar.cycle_number', { number: cycle.number })}</strong><small>{stateLabels[cycle.state]}</small></span>
        <span>{t('calendar.send_date', { date: calendarDate(cycle.send_on) })}</span>
        <span>{t('calendar.summary_date', { date: calendarDate(cycle.due_on) })}</span>
      </button>
    )}</div>
    {month.carryover&&<div className="calendar-carryover"><span>{t('calendar.carryover', { send:calendarDate(month.carryover.send_on), due:calendarDate(month.carryover.due_on) })}</span><button className="text-btn" onClick={()=>onOpenCarryover(month.carryover!.period_id, month.carryover!.send_on)}>{t('calendar.open_carryover')}</button></div>}
    <p className="calendar-note">{t(selected === 'unassigned' ? 'calendar.unassigned_hint' : 'calendar.month_ownership')}</p>
  </section>
}
