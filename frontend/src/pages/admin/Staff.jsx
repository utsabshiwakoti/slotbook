import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { api } from '../../api'
import { WEEKDAYS } from '../../format'
import useLoad from '../../useLoad'

const short = (t) => t.slice(0, 5) // "09:00:00" -> "09:00"
const clock = (t) => {
  const [h, m] = t.split(':').map(Number)
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, '0')}` : ''} ${h < 12 ? 'AM' : 'PM'}`
}

export default function StaffPage() {
  const { readOnly } = useOutletContext()
  const staff = useLoad(() => api('/admin/staff'), [])
  const services = useLoad(() => api('/admin/services'), [])
  const [editing, setEditing] = useState(null)

  if (staff.loading || services.loading) return <p className="muted">Loading…</p>
  if (staff.error || services.error) return <p className="error">{(staff.error || services.error).message}</p>
  const serviceName = Object.fromEntries(services.data.map((s) => [s.id, s.name]))
  const done = () => { setEditing(null); staff.reload() }
  const blank = {
    name: '', is_active: true, service_ids: services.data.map((s) => s.id),
    hours: [0, 1, 2, 3, 4].map((weekday) => ({ weekday, start_time: '09:00', end_time: '17:00' })),
  }

  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>Staff &amp; hours</h1>
        {!readOnly && editing !== 'new' && <button className="button" onClick={() => setEditing('new')}>Add person</button>}
      </div>
      <p className="muted">Times are in the business's time zone. Add two shifts on one day for a lunch break.</p>
      {editing === 'new' && <StaffForm initial={blank} services={services.data} onDone={done} onCancel={() => setEditing(null)} />}
      {staff.data.length === 0 && editing !== 'new' && <p className="card empty">No staff yet. Customers can only book when someone offering the service is working.</p>}
      <ul className="card-list">
        {staff.data.map((p) =>
          editing === p.id ? (
            <li key={p.id}><StaffForm initial={p} id={p.id} services={services.data} onDone={done} onCancel={() => setEditing(null)} /></li>
          ) : (
            <li key={p.id} className={`card item ${p.is_active ? '' : 'inactive'}`}>
              <div className="grow">
                <strong>{p.name}</strong> {!p.is_active && <span className="badge">Inactive</span>}
                <span className="muted small block">{p.service_ids.map((id) => serviceName[id]).join(', ') || 'No services'}</span>
                <WeekSummary hours={p.hours} />
              </div>
              {!readOnly && <button className="link-button" onClick={() => setEditing(p.id)}>Edit</button>}
            </li>
          ),
        )}
      </ul>
    </div>
  )
}

function WeekSummary({ hours }) {
  return (
    <dl className="week-summary">
      {WEEKDAYS.map((day, i) => {
        const shifts = hours.filter((h) => h.weekday === i)
        return (
          <div key={day} className={shifts.length ? '' : 'off'}>
            <dt>{day.slice(0, 3)}</dt>
            <dd>{shifts.length ? shifts.map((s) => `${clock(s.start_time)}–${clock(s.end_time)}`).join(', ') : 'Off'}</dd>
          </div>
        )
      })}
    </dl>
  )
}

function StaffForm({ initial, id, services, onDone, onCancel }) {
  const [form, setForm] = useState({
    ...initial,
    hours: initial.hours.map((h) => ({ ...h, start_time: short(h.start_time), end_time: short(h.end_time) })),
  })
  const [error, setError] = useState('')

  const toggleService = (sid) =>
    setForm((f) => ({
      ...f,
      service_ids: f.service_ids.includes(sid) ? f.service_ids.filter((x) => x !== sid) : [...f.service_ids, sid],
    }))
  const setShift = (index, field, value) =>
    setForm((f) => ({ ...f, hours: f.hours.map((h, i) => (i === index ? { ...h, [field]: value } : h)) }))
  const addShift = (weekday) => {
    const last = form.hours.filter((h) => h.weekday === weekday).at(-1)
    const shift = last ? { weekday, start_time: last.end_time, end_time: '17:00' } : { weekday, start_time: '09:00', end_time: '17:00' }
    setForm((f) => ({ ...f, hours: [...f.hours, shift] }))
  }
  const removeShift = (index) => setForm((f) => ({ ...f, hours: f.hours.filter((_, i) => i !== index) }))

  const save = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const body = { name: form.name, is_active: form.is_active, service_ids: form.service_ids, hours: form.hours }
      await api(id ? `/admin/staff/${id}` : '/admin/staff', { method: id ? 'PATCH' : 'POST', body })
      onDone()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async () => {
    try {
      await api(`/admin/staff/${id}`, { method: 'DELETE' })
      onDone()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="card stack" onSubmit={save}>
      <div className="row">
        <label className="grow">Name<input required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label className="inline"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Taking bookings</label>
      </div>

      <fieldset>
        <legend>Services they do</legend>
        <div className="chips">
          {services.map((s) => (
            <label key={s.id} className={`chip ${form.service_ids.includes(s.id) ? 'on' : ''}`}>
              <input type="checkbox" checked={form.service_ids.includes(s.id)} onChange={() => toggleService(s.id)} /> {s.name}
            </label>
          ))}
          {services.length === 0 && <span className="muted small">Add services first.</span>}
        </div>
      </fieldset>

      <fieldset>
        <legend>Weekly hours</legend>
        <div className="hours-editor">
          {WEEKDAYS.map((day, weekday) => {
            const shifts = form.hours.map((h, i) => [h, i]).filter(([h]) => h.weekday === weekday)
            return (
              <div key={day} className="hours-row">
                <span className="day-name">{day}</span>
                <div className="shifts">
                  {shifts.length === 0 && <span className="muted small">Off</span>}
                  {shifts.map(([h, i]) => (
                    <span key={i} className="shift">
                      <input type="time" aria-label={`${day} start`} value={h.start_time} required step={900}
                        onChange={(e) => setShift(i, 'start_time', e.target.value)} />
                      –
                      <input type="time" aria-label={`${day} end`} value={h.end_time} required step={900}
                        onChange={(e) => setShift(i, 'end_time', e.target.value)} />
                      <button type="button" className="icon-button" aria-label={`Remove ${day} shift`} onClick={() => removeShift(i)}>×</button>
                    </span>
                  ))}
                  <button type="button" className="link-button small" onClick={() => addShift(weekday)}>+ shift</button>
                </div>
              </div>
            )
          })}
        </div>
      </fieldset>

      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button className="button">Save</button>
        <button type="button" className="button secondary" onClick={onCancel}>Cancel</button>
        {id && <button type="button" className="link-button danger-text push-right" onClick={remove}>Delete</button>}
      </div>
    </form>
  )
}
