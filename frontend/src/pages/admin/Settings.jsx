import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { api } from '../../api'
import { useAuth } from '../../auth'

export default function Settings() {
  const { business, readOnly } = useOutletContext()
  const { refresh } = useAuth()
  const [form, setForm] = useState(business)
  const [status, setStatus] = useState({ error: '', saved: false })
  const [copied, setCopied] = useState(false)
  const link = `${window.location.origin}/b/${business.slug}`
  const set = (field, number = false) => (e) =>
    setForm({ ...form, [field]: number ? Number(e.target.value) : e.target.value })

  const save = async (e) => {
    e.preventDefault()
    setStatus({ error: '', saved: false })
    try {
      const { name, description, timezone, slot_interval_minutes, min_notice_minutes, max_days_ahead } = form
      await api('/admin/business', {
        method: 'PATCH',
        body: { name, description, timezone, slot_interval_minutes, min_notice_minutes, max_days_ahead },
      })
      await refresh() // the layout shows the business name and time zone
      setStatus({ error: '', saved: true })
    } catch (err) {
      setStatus({ error: err.message, saved: false })
    }
  }

  const copy = async () => {
    await navigator.clipboard.writeText(link)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="stack-lg">
      <h1>Settings</h1>
      <section className="card">
        <h3>Your booking page</h3>
        <div className="row">
          <code className="grow">{link}</code>
          <button className="button secondary" onClick={copy}>{copied ? 'Copied' : 'Copy link'}</button>
        </div>
      </section>

      <form className="card form-grid" onSubmit={save}>
        <label className="span-2">Business name<input required maxLength={100} value={form.name} onChange={set('name')} disabled={readOnly} /></label>
        <label className="span-2">
          Description <span className="muted small">(shown on your booking page)</span>
          <textarea rows={2} maxLength={2000} value={form.description} onChange={set('description')} disabled={readOnly} />
        </label>
        <label className="span-2">
          Time zone
          <select value={form.timezone} onChange={set('timezone')} disabled={readOnly}>
            {Intl.supportedValuesOf('timeZone').map((tz) => <option key={tz}>{tz}</option>)}
          </select>
        </label>
        <label>
          Offer start times every
          <select value={form.slot_interval_minutes} onChange={set('slot_interval_minutes', true)} disabled={readOnly}>
            {[5, 10, 15, 20, 30, 60].map((m) => <option key={m} value={m}>{m} minutes</option>)}
          </select>
        </label>
        <label>
          Minimum notice
          <select value={form.min_notice_minutes} onChange={set('min_notice_minutes', true)} disabled={readOnly}>
            {[[0, 'None'], [30, '30 minutes'], [60, '1 hour'], [120, '2 hours'], [240, '4 hours'], [1440, '1 day'], [2880, '2 days']].map(
              ([m, label]) => <option key={m} value={m}>{label}</option>,
            )}
          </select>
        </label>
        <label>
          Book up to
          <select value={form.max_days_ahead} onChange={set('max_days_ahead', true)} disabled={readOnly}>
            {[7, 14, 30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} days ahead</option>)}
          </select>
        </label>
        {status.error && <p className="error span-2" role="alert">{status.error}</p>}
        {status.saved && <p className="success span-2" role="status">Saved.</p>}
        {!readOnly && <div className="span-2"><button className="button">Save settings</button></div>}
      </form>
    </div>
  )
}
