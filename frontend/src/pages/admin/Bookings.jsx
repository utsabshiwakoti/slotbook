import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { api } from '../../api'
import { addDays, formatDay, formatMoney, formatTime, localDate, todayIn } from '../../format'
import useLoad from '../../useLoad'

const mondayOf = (ymd) => {
  const weekday = (new Date(`${ymd}T00:00:00Z`).getUTCDay() + 6) % 7 // Monday = 0
  return addDays(ymd, -weekday)
}

export default function Bookings() {
  const { business, readOnly } = useOutletContext()
  const tz = business.timezone
  const [week, setWeek] = useState(() => mondayOf(todayIn(tz)))
  const [showCancelled, setShowCancelled] = useState(false)
  const [confirming, setConfirming] = useState(null)
  const [error, setError] = useState('')
  const list = useLoad(
    () => api('/admin/bookings', { params: { start: week, days: 7, status: showCancelled ? undefined : 'confirmed' } }),
    [week, showCancelled],
  )

  const cancel = async (id) => {
    setError('')
    try {
      await api(`/admin/bookings/${id}/cancel`, { method: 'POST' })
      setConfirming(null)
      list.reload()
    } catch (e) {
      setError(e.message)
    }
  }

  const days = Array.from({ length: 7 }, (_, i) => addDays(week, i))
  const byDay = Object.groupBy?.(list.data ?? [], (b) => localDate(b.starts_at, tz)) ?? {}

  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>Bookings</h1>
        <div className="row">
          <button className="button secondary" onClick={() => setWeek(addDays(week, -7))} aria-label="Previous week">←</button>
          <button className="button secondary" onClick={() => setWeek(mondayOf(todayIn(tz)))}>This week</button>
          <button className="button secondary" onClick={() => setWeek(addDays(week, 7))} aria-label="Next week">→</button>
        </div>
      </div>
      <div className="row spread">
        <p className="muted">
          Week of {formatDay(week, { weekday: 'long', month: 'long', day: 'numeric' })}
          {list.data && ` · ${list.data.filter((b) => b.status === 'confirmed').length} confirmed`}
        </p>
        <label className="inline small">
          <input type="checkbox" checked={showCancelled} onChange={(e) => setShowCancelled(e.target.checked)} /> Show cancelled
        </label>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {list.loading && !list.data ? <p className="muted">Loading…</p> : list.error ? <p className="error">{list.error.message}</p> : (
        days.map((day) => (
          <section key={day} className="day-block">
            <h3>{formatDay(day, { weekday: 'long', month: 'short', day: 'numeric' })}</h3>
            {(byDay[day] ?? []).length === 0 ? <p className="muted small">No bookings</p> : (
              <table className="data-table bookings-table">
                <tbody>
                  {byDay[day].map((b) => (
                    <tr key={b.id} className={b.status === 'cancelled' ? 'is-cancelled' : ''}>
                      <td className="time">{formatTime(b.starts_at, tz)}–{formatTime(b.ends_at, tz)}</td>
                      <td>
                        <strong>{b.customer_name}</strong>
                        <span className="muted small block">{b.customer_email}</span>
                        {b.note && <span className="small block note">“{b.note}”</span>}
                      </td>
                      <td>{b.service.name}<span className="muted small block">{formatMoney(b.price_cents)}</span></td>
                      <td>{b.staff.name}</td>
                      <td className="actions">
                        {b.status === 'cancelled' ? (
                          <span className="badge cancelled">Cancelled{b.cancelled_by ? ` by ${b.cancelled_by}` : ''}</span>
                        ) : confirming === b.id ? (
                          <span className="row">
                            <button className="button danger small" onClick={() => cancel(b.id)}>Cancel &amp; email</button>
                            <button className="link-button small" onClick={() => setConfirming(null)}>Keep</button>
                          </span>
                        ) : (
                          !readOnly && <button className="link-button small" onClick={() => setConfirming(b.id)}>Cancel</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        ))
      )}
    </div>
  )
}
