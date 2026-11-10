import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { api } from '../../api'
import { formatDuration, formatLongDateTime, formatMoney } from '../../format'
import useLoad from '../../useLoad'
import NotFound from '../NotFound'
import SlotPicker from './SlotPicker'

/** Reached from the link in the confirmation email. The token in the URL is the only credential. */
export default function ManagePage() {
  const { token } = useParams()
  const loaded = useLoad(() => api(`/manage/${token}`), [token])
  const [booking, setBooking] = useState(null)
  const [mode, setMode] = useState('view') // view | confirm-cancel | reschedule
  const [anyone, setAnyone] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  if (loaded.loading) return <div className="centered muted">Loading…</div>
  if (loaded.error) return <NotFound message={loaded.error.message} />

  const b = booking ?? loaded.data
  const tz = b.business.timezone

  const act = async (path, body, done) => {
    setError('')
    try {
      setBooking(await api(`/manage/${token}/${path}`, { method: 'POST', body }))
      setMode('view')
      setMessage(done)
    } catch (err) {
      setError(err.message)
      setRefreshKey((k) => k + 1)
    }
  }

  return (
    <div className="booking">
      <header className="booking-head">
        <h1>{b.business.name}</h1>
        <p className="muted">Your appointment</p>
      </header>

      <div className="card manage-card">
        {b.status === 'cancelled' && <p className="badge cancelled">Cancelled</p>}
        <p className="when">{formatLongDateTime(b.starts_at, tz)}</p>
        <p>
          {b.service.name} with {b.staff.name} · {formatDuration(b.service.duration_minutes)} · {formatMoney(b.service.price_cents)}
        </p>
        {message && <p className="success" role="status">{message}</p>}
        {error && <p className="error" role="alert">{error}</p>}

        {b.can_change && mode === 'view' && (
          <div className="row">
            <button className="button" onClick={() => { setMode('reschedule'); setMessage('') }}>Change time</button>
            <button className="button danger-outline" onClick={() => { setMode('confirm-cancel'); setMessage('') }}>Cancel booking</button>
          </div>
        )}

        {mode === 'confirm-cancel' && (
          <div className="confirm-box">
            <p>Cancel this appointment? The time will be offered to other customers.</p>
            <div className="row">
              <button className="button danger" onClick={() => act('cancel', undefined, 'Your booking is cancelled. A confirmation is on its way.')}>
                Yes, cancel it
              </button>
              <button className="button secondary" onClick={() => setMode('view')}>Keep it</button>
            </div>
          </div>
        )}

        {!b.can_change && b.status === 'confirmed' && (
          <p className="muted">This appointment has started or passed, so it can't be changed online.</p>
        )}
      </div>

      {mode === 'reschedule' && (
        <section className="step">
          <h2>Pick a new time</h2>
          <label className="inline">
            <input type="checkbox" checked={anyone} onChange={(e) => setAnyone(e.target.checked)} />
            Show times with other staff too
          </label>
          <SlotPicker
            slug={b.business.slug}
            serviceId={b.service.id}
            staffId={anyone ? null : b.staff.id}
            excludeToken={token}
            timezone={tz}
            refreshKey={refreshKey}
            onPick={(slot) =>
              act('reschedule', { start: slot.start, staff_id: anyone ? null : b.staff.id }, 'Done! Your appointment has moved.')
            }
          />
          <button className="link-button" onClick={() => setMode('view')}>Never mind</button>
        </section>
      )}

      <footer className="booking-foot muted small">
        <Link to={`/b/${b.business.slug}`}>Book another appointment</Link>
      </footer>
    </div>
  )
}
