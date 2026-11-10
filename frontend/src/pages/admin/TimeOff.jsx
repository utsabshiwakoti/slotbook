import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { api } from '../../api'
import { addDays, formatDateTime, todayIn } from '../../format'
import useLoad from '../../useLoad'

export default function TimeOff() {
  const { business, readOnly } = useOutletContext()
  const tz = business.timezone
  const blocks = useLoad(() => api('/admin/time-off'), [])
  const staff = useLoad(() => api('/admin/staff'), [])
  const today = todayIn(tz)
  const [form, setForm] = useState({
    staff_id: '', allDay: true, startDate: today, endDate: today, startTime: '12:00', endTime: '13:00', reason: '',
  })
  const [error, setError] = useState('')
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const who = (id) => (id === null ? 'Whole business' : staff.data?.find((p) => p.id === id)?.name ?? 'Staff')

  const add = async (e) => {
    e.preventDefault()
    setError('')
    // Sent as local wall-clock times; the server applies the business's time zone.
    const body = form.allDay
      ? { starts_local: `${form.startDate}T00:00`, ends_local: `${addDays(form.endDate, 1)}T00:00` }
      : { starts_local: `${form.startDate}T${form.startTime}`, ends_local: `${form.endDate}T${form.endTime}` }
    try {
      await api('/admin/time-off', {
        method: 'POST',
        body: { ...body, staff_id: form.staff_id ? Number(form.staff_id) : null, reason: form.reason },
      })
      setForm({ ...form, reason: '' })
      blocks.reload()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (id) => {
    await api(`/admin/time-off/${id}`, { method: 'DELETE' }).catch((err) => setError(err.message))
    blocks.reload()
  }

  return (
    <div className="stack-lg">
      <h1>Time off &amp; holidays</h1>
      <p className="muted">Blocked times disappear from the booking page. Existing bookings are kept, so check the Bookings page if you need to cancel any.</p>

      {!readOnly && (
        <form className="card form-grid" onSubmit={add}>
          <label>
            Who
            <select value={form.staff_id} onChange={set('staff_id')}>
              <option value="">Whole business (closed)</option>
              {staff.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label>Reason <span className="muted small">(optional)</span><input maxLength={200} value={form.reason} onChange={set('reason')} placeholder="e.g. Holiday" /></label>
          <label className="inline span-2"><input type="checkbox" checked={form.allDay} onChange={set('allDay')} /> Whole days</label>
          <label>From<input type="date" required min={today} value={form.startDate} onChange={set('startDate')} /></label>
          {!form.allDay && <label>Start time<input type="time" required value={form.startTime} onChange={set('startTime')} /></label>}
          <label>{form.allDay ? 'To (inclusive)' : 'Until'}<input type="date" required min={form.startDate} value={form.endDate} onChange={set('endDate')} /></label>
          {!form.allDay && <label>End time<input type="time" required value={form.endTime} onChange={set('endTime')} /></label>}
          {error && <p className="error span-2" role="alert">{error}</p>}
          <div className="span-2"><button className="button">Block this time</button></div>
        </form>
      )}

      <section>
        <h2>Upcoming</h2>
        {blocks.loading ? <p className="muted">Loading…</p> : blocks.data?.length ? (
          <ul className="card-list">
            {blocks.data.map((b) => (
              <li key={b.id} className="card item">
                <div>
                  <strong>{who(b.staff_id)}</strong> {b.reason && <span className="muted">· {b.reason}</span>}
                  <span className="small block">{formatDateTime(b.starts_at, tz)} → {formatDateTime(b.ends_at, tz)}</span>
                </div>
                {!readOnly && <button className="link-button" onClick={() => remove(b.id)}>Remove</button>}
              </li>
            ))}
          </ul>
        ) : <p className="muted">Nothing blocked.</p>}
      </section>
    </div>
  )
}
