import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { api } from '../../api'
import { formatDuration, formatLongDateTime, formatMoney } from '../../format'
import useLoad from '../../useLoad'
import NotFound from '../NotFound'
import SlotPicker from './SlotPicker'

const ANYONE = 'any'

export default function BookingPage() {
  const { slug } = useParams()
  const page = useLoad(() => api(`/businesses/${slug}`), [slug])
  const [service, setService] = useState(null)
  const [staffChoice, setStaffChoice] = useState(ANYONE)
  const [slot, setSlot] = useState(null)
  const [booked, setBooked] = useState(null)
  const [slotError, setSlotError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  if (page.loading) return <div className="centered muted">Loading…</div>
  if (page.error) return <NotFound message={page.error.status === 404 ? "This booking page doesn't exist." : page.error.message} />

  const { business, services, staff } = page.data
  const tz = business.timezone
  const staffForService = service ? staff.filter((p) => p.service_ids.includes(service.id)) : []
  const staffId = staffChoice === ANYONE ? null : Number(staffChoice)
  const staffName = (id) => staff.find((p) => p.id === id)?.name

  const restart = () => {
    setService(null)
    setStaffChoice(ANYONE)
    setSlot(null)
    setBooked(null)
  }

  // The slot was taken between loading and submitting: send them back to pick again.
  const slotTaken = (message) => {
    setSlot(null)
    setSlotError(message)
    setRefreshKey((k) => k + 1)
  }

  return (
    <div className="booking">
      <header className="booking-head">
        <h1>{business.name}</h1>
        {business.description && <p className="muted">{business.description}</p>}
      </header>

      {booked ? (
        <Confirmation booking={booked} onAgain={restart} />
      ) : (
        <div className="booking-steps">
          <Step n={1} title="Service" done={service && `${service.name} · ${formatDuration(service.duration_minutes)}`}
            onEdit={() => { setService(null); setSlot(null) }}>
            {services.length === 0 ? (
              <p className="empty">This business hasn't added any services yet.</p>
            ) : (
              <ul className="service-list">
                {services.map((s) => (
                  <li key={s.id}>
                    <button className="service-option" onClick={() => { setService(s); setStaffChoice(ANYONE); setSlotError('') }}>
                      <span>
                        <strong>{s.name}</strong>
                        {s.description && <span className="muted small block">{s.description}</span>}
                      </span>
                      <span className="service-meta">
                        <span>{formatDuration(s.duration_minutes)}</span>
                        <strong>{formatMoney(s.price_cents)}</strong>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Step>

          {service && (
            <Step n={2} title="Time" done={slot && `${formatLongDateTime(slot.start, tz)} with ${staffId ? staffName(staffId) : 'the first available staff member'}`}
              onEdit={() => setSlot(null)}>
              {staffForService.length > 1 && (
                <label className="inline">
                  With
                  <select value={staffChoice} onChange={(e) => { setStaffChoice(e.target.value); setSlot(null) }}>
                    <option value={ANYONE}>Anyone available</option>
                    {staffForService.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </label>
              )}
              {slotError && <p className="error" role="alert">{slotError}</p>}
              <SlotPicker slug={slug} serviceId={service.id} staffId={staffId} timezone={tz}
                refreshKey={refreshKey} onPick={(s) => { setSlot(s); setSlotError('') }} />
            </Step>
          )}

          {service && slot && (
            <Step n={3} title="Your details">
              <DetailsForm slug={slug} service={service} slot={slot} staffId={staffId} tz={tz}
                onBooked={setBooked} onTaken={slotTaken} />
            </Step>
          )}
        </div>
      )}
      <footer className="booking-foot muted small">Online booking by <Link to="/">SlotBook</Link></footer>
    </div>
  )
}

function Step({ n, title, done, onEdit, children }) {
  return (
    <section className={`step ${done ? 'step-done' : ''}`}>
      <h2>
        <span className="step-n">{n}</span> {title}
      </h2>
      {done ? (
        <div className="step-summary">
          <span>{done}</span>
          {onEdit && <button className="link-button" onClick={onEdit}>Change</button>}
        </div>
      ) : (
        children
      )}
    </section>
  )
}

function DetailsForm({ slug, service, slot, staffId, tz, onBooked, onTaken }) {
  const [form, setForm] = useState({ customer_name: '', customer_email: '', note: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const booking = await api(`/businesses/${slug}/bookings`, {
        method: 'POST',
        body: { ...form, service_id: service.id, staff_id: staffId, start: slot.start },
      })
      onBooked(booking)
    } catch (err) {
      if (err.status === 409) onTaken(err.message)
      else setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="stack details-form">
      <label>Name<input required maxLength={100} autoComplete="name" value={form.customer_name} onChange={set('customer_name')} /></label>
      <label>Email<input type="email" required autoComplete="email" value={form.customer_email} onChange={set('customer_email')} /></label>
      <label>Anything we should know? <span className="muted small">(optional)</span>
        <textarea rows={2} maxLength={500} value={form.note} onChange={set('note')} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="button big" disabled={busy}>
        {busy ? 'Booking…' : `Book ${service.name}, ${formatLongDateTime(slot.start, tz)}`}
      </button>
    </form>
  )
}

function Confirmation({ booking, onAgain }) {
  const tz = booking.business.timezone
  const manageUrl = `/manage/${booking.manage_token}`
  return (
    <div className="card confirmation">
      <div className="check" aria-hidden="true">✓</div>
      <h2>You're booked, {booking.customer_name.split(' ')[0]}!</h2>
      <p className="when">{formatLongDateTime(booking.starts_at, tz)}</p>
      <p>{booking.service.name} with {booking.staff.name}</p>
      <p className="muted">
        We've emailed you a confirmation with a private link to change or cancel. You can also use it now:
      </p>
      <div className="row center">
        <Link to={manageUrl} className="button secondary">Manage this booking</Link>
        <button className="button" onClick={onAgain}>Book something else</button>
      </div>
    </div>
  )
}
