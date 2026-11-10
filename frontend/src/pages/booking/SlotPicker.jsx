import { useState } from 'react'
import { api } from '../../api'
import { addDays, formatDay, formatTime, localDate } from '../../format'
import useLoad from '../../useLoad'

const PERIODS = [
  ['Morning', (h) => h < 12],
  ['Afternoon', (h) => h >= 12 && h < 17],
  ['Evening', (h) => h >= 17],
]

function hourIn(iso, tz) {
  return Number(new Intl.DateTimeFormat('en-CA', { timeZone: tz, hour: 'numeric', hourCycle: 'h23' }).format(new Date(iso)))
}

/** Pick a date (only days with free slots are enabled), then a time. Shared by booking and rescheduling. */
export default function SlotPicker({ slug, serviceId, staffId, excludeToken, timezone, onPick, refreshKey = 0 }) {
  const [day, setDay] = useState(null)
  const days = useLoad(
    () => api(`/businesses/${slug}/days`, { params: { service_id: serviceId, staff_id: staffId, exclude_token: excludeToken } }),
    [slug, serviceId, staffId, excludeToken, refreshKey],
  )
  const openDays = new Set(days.data?.days ?? [])
  const selected = day && openDays.has(day) ? day : days.data?.days[0] ?? null

  const slots = useLoad(
    () =>
      selected
        ? api(`/businesses/${slug}/availability`, {
            params: { service_id: serviceId, date: selected, staff_id: staffId, exclude_token: excludeToken },
          })
        : Promise.resolve({ slots: [] }),
    [slug, serviceId, staffId, excludeToken, selected, refreshKey],
  )

  if (days.loading && !days.data) return <p className="muted">Finding open days…</p>
  if (days.error) return <p className="error">{days.error.message}</p>
  if (!days.data.days.length) return <p className="empty">No open times in the next {daysBetween(days.data)} days. Try someone else or check back later.</p>

  const allDays = []
  for (let d = days.data.first; d <= days.data.last; d = addDays(d, 1)) allDays.push(d)

  return (
    <div className="slot-picker">
      <div className="day-strip" role="listbox" aria-label="Date">
        {allDays.map((d) => (
          <button
            key={d}
            role="option"
            aria-selected={d === selected}
            className={`day ${d === selected ? 'selected' : ''}`}
            disabled={!openDays.has(d)}
            onClick={() => setDay(d)}
          >
            <span className="dow">{formatDay(d, { weekday: 'short' })}</span>
            <span className="dom">{formatDay(d, { day: 'numeric' })}</span>
            <span className="mon">{formatDay(d, { month: 'short' })}</span>
          </button>
        ))}
      </div>

      <h3>{selected && formatDay(selected, { weekday: 'long', month: 'long', day: 'numeric' })}</h3>
      {slots.loading && !slots.data ? (
        <p className="muted">Loading times…</p>
      ) : slots.error ? (
        <p className="error">{slots.error.message}</p>
      ) : (
        PERIODS.map(([label, test]) => {
          const group = slots.data.slots.filter((s) => localDate(s.start, timezone) === selected && test(hourIn(s.start, timezone)))
          return group.length ? (
            <div key={label} className="slot-group">
              <h4>{label}</h4>
              <div className="slots">
                {group.map((s) => (
                  <button key={s.start} className="slot" onClick={() => onPick(s)}>
                    {formatTime(s.start, timezone)}
                  </button>
                ))}
              </div>
            </div>
          ) : null
        })
      )}
      <p className="muted small">Times are shown in {timezone.replace('_', ' ')} time.</p>
    </div>
  )
}

const daysBetween = ({ first, last }) => Math.round((new Date(last) - new Date(first)) / 86400000) + 1
