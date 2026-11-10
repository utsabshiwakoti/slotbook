import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { api } from '../../api'
import { formatDuration, formatMoney } from '../../format'
import useLoad from '../../useLoad'

const EMPTY = { name: '', description: '', duration_minutes: 30, buffer_minutes: 0, price: '0.00', is_active: true }

const toForm = (s) => ({ ...s, price: (s.price_cents / 100).toFixed(2) })
const toBody = ({ price, ...f }) => ({
  name: f.name, description: f.description, is_active: f.is_active,
  duration_minutes: Number(f.duration_minutes), buffer_minutes: Number(f.buffer_minutes),
  price_cents: Math.round(Number(price) * 100), // dollars in the form, integer cents in the API
})

export default function Services() {
  const { readOnly } = useOutletContext()
  const list = useLoad(() => api('/admin/services'), [])
  const [editing, setEditing] = useState(null) // service id, 'new', or null

  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>Services</h1>
        {!readOnly && editing !== 'new' && <button className="button" onClick={() => setEditing('new')}>Add service</button>}
      </div>
      {editing === 'new' && (
        <ServiceForm initial={EMPTY} onDone={() => { setEditing(null); list.reload() }} onCancel={() => setEditing(null)} />
      )}
      {list.loading ? <p className="muted">Loading…</p> : list.error ? <p className="error">{list.error.message}</p> : (
        list.data.length === 0 && editing !== 'new' ? (
          <div className="card empty">
            <p>No services yet. Add what customers can book, like “Haircut, 30 minutes, $35”.</p>
            <p className="muted small">Then add staff and their working hours so times can be offered.</p>
          </div>
        ) : (
          <ul className="card-list">
            {list.data.map((s) =>
              editing === s.id ? (
                <li key={s.id}><ServiceForm initial={toForm(s)} id={s.id} onDone={() => { setEditing(null); list.reload() }} onCancel={() => setEditing(null)} /></li>
              ) : (
                <li key={s.id} className={`card item ${s.is_active ? '' : 'inactive'}`}>
                  <div>
                    <strong>{s.name}</strong> {!s.is_active && <span className="badge">Hidden</span>}
                    <span className="muted small block">
                      {formatDuration(s.duration_minutes)}
                      {s.buffer_minutes > 0 && ` + ${s.buffer_minutes} min buffer`} · {formatMoney(s.price_cents)}
                    </span>
                    {s.description && <span className="small block">{s.description}</span>}
                  </div>
                  {!readOnly && <button className="link-button" onClick={() => setEditing(s.id)}>Edit</button>}
                </li>
              ),
            )}
          </ul>
        )
      )}
    </div>
  )
}

function ServiceForm({ initial, id, onDone, onCancel }) {
  const [form, setForm] = useState(initial)
  const [error, setError] = useState('')
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  const save = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await api(id ? `/admin/services/${id}` : '/admin/services', { method: id ? 'PATCH' : 'POST', body: toBody(form) })
      onDone()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async () => {
    setError('')
    try {
      await api(`/admin/services/${id}`, { method: 'DELETE' })
      onDone()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="card form-grid" onSubmit={save}>
      <label className="span-2">Name<input required maxLength={100} value={form.name} onChange={set('name')} /></label>
      <label>Length (minutes)<input type="number" min={5} max={480} step={5} required value={form.duration_minutes} onChange={set('duration_minutes')} /></label>
      <label>
        Buffer after (minutes)
        <input type="number" min={0} max={120} step={5} value={form.buffer_minutes} onChange={set('buffer_minutes')} />
      </label>
      <label>Price ($)<input type="number" min={0} step="0.01" required value={form.price} onChange={set('price')} /></label>
      <label className="inline"><input type="checkbox" checked={form.is_active} onChange={set('is_active')} /> Customers can book this</label>
      <label className="span-2">Description<textarea rows={2} maxLength={1000} value={form.description} onChange={set('description')} /></label>
      {error && <p className="error span-2" role="alert">{error}</p>}
      <div className="row span-2">
        <button className="button">Save</button>
        <button type="button" className="button secondary" onClick={onCancel}>Cancel</button>
        {id && <button type="button" className="link-button danger-text push-right" onClick={remove}>Delete</button>}
      </div>
    </form>
  )
}
