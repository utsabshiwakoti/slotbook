import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { DEMO_LOGIN, useAuth } from '../auth'
import { Brand } from './Landing'

function AuthShell({ title, children }) {
  return (
    <div className="auth-page">
      <Brand />
      <div className="card auth-card">
        <h1>{title}</h1>
        {children}
      </div>
    </div>
  )
}

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e, creds = form) => {
    e?.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(creds.email, creds.password)
      navigate('/admin')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Sign in">
      <form onSubmit={submit} className="stack">
        <label>
          Email
          <input type="email" required autoComplete="email" value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </label>
        <label>
          Password
          <input type="password" required autoComplete="current-password" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="button" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
      <button className="link-button" onClick={() => submit(null, DEMO_LOGIN)}>Use the read-only demo account</button>
      <p className="muted">New here? <Link to="/signup">Create your business</Link></p>
    </AuthShell>
  )
}

const slugify = (text) =>
  text.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)

export function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const [form, setForm] = useState({
    name: '', email: '', password: '', business_name: '', slug: '', timezone: browserZone || 'America/Halifax',
  })
  const [slugTouched, setSlugTouched] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (field) => (e) => {
    const value = e.target.value
    setForm((f) => {
      const next = { ...f, [field]: value }
      // Suggest a booking URL from the business name until the owner edits it themselves.
      if (field === 'business_name' && !slugTouched) next.slug = slugify(value)
      return next
    })
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await signup(form)
      navigate('/admin/services')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Create your business">
      <form onSubmit={submit} className="stack">
        <label>Your name<input required value={form.name} onChange={set('name')} /></label>
        <label>Email<input type="email" required autoComplete="email" value={form.email} onChange={set('email')} /></label>
        <label>
          Password <span className="muted small">(at least 8 characters)</span>
          <input type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set('password')} />
        </label>
        <label>Business name<input required value={form.business_name} onChange={set('business_name')} /></label>
        <label>
          Booking page address
          <div className="prefixed">
            <span>{window.location.host}/b/</span>
            <input required minLength={3} maxLength={40} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={form.slug}
              onChange={(e) => { setSlugTouched(true); set('slug')(e) }} />
          </div>
        </label>
        <label>
          Time zone
          <select value={form.timezone} onChange={set('timezone')}>
            {Intl.supportedValuesOf('timeZone').map((tz) => <option key={tz}>{tz}</option>)}
          </select>
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="button" disabled={busy}>{busy ? 'Creating…' : 'Create business'}</button>
      </form>
      <p className="muted">Already have an account? <Link to="/login">Sign in</Link></p>
    </AuthShell>
  )
}
