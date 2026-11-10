import { Navigate, NavLink, Outlet } from 'react-router'
import { useAuth } from '../../auth'
import { Brand } from '../Landing'

const LINKS = [
  ['/admin', 'Overview', true],
  ['/admin/bookings', 'Bookings'],
  ['/admin/services', 'Services'],
  ['/admin/staff', 'Staff & hours'],
  ['/admin/time-off', 'Time off'],
  ['/admin/settings', 'Settings'],
]

export default function AdminLayout() {
  const { user, loading, logout } = useAuth()
  if (loading) return <div className="centered muted">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  const business = user.business

  return (
    <div className="admin">
      <aside className="admin-nav">
        <Brand />
        <div className="business-name">
          <strong>{business.name}</strong>
          <a href={`/b/${business.slug}`} target="_blank" rel="noreferrer" className="small">
            View booking page ↗
          </a>
        </div>
        <nav>
          {LINKS.map(([to, label, end]) => (
            <NavLink key={to} to={to} end={end}>{label}</NavLink>
          ))}
        </nav>
        <div className="admin-user small">
          <span className="muted">{user.email}</span>
          <button className="link-button" onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="admin-main">
        {user.is_demo && (
          <p className="demo-banner">
            You're looking at the demo shop. It's read-only; <a href="/signup">create your own business</a> to try editing.
          </p>
        )}
        <Outlet context={{ user, business, readOnly: user.is_demo }} />
      </main>
    </div>
  )
}
