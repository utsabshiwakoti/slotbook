import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { DEMO_LOGIN, useAuth } from '../auth'

export function Brand() {
  return (
    <Link to="/" className="brand">
      <img src="/favicon.svg" alt="" width="26" height="26" /> SlotBook
    </Link>
  )
}

export default function Landing() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  const openDemoDashboard = async () => {
    try {
      await login(DEMO_LOGIN.email, DEMO_LOGIN.password)
      navigate('/admin')
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="landing">
      <header className="topbar">
        <Brand />
        <nav>
          {user ? (
            <Link to="/admin" className="button">Dashboard</Link>
          ) : (
            <>
              <Link to="/login">Sign in</Link>
              <Link to="/signup" className="button">Create a business</Link>
            </>
          )}
        </nav>
      </header>

      <main className="hero">
        <h1>Online booking for small businesses</h1>
        <p className="lead">
          Give customers a booking page that only offers times you're actually free, and run the
          day from one dashboard: services, staff hours, time off, and how the week is going.
        </p>
        <div className="hero-actions">
          <Link to="/b/demo" className="button big">Book at the demo shop</Link>
          <button className="button big secondary" onClick={openDemoDashboard}>
            Open the demo dashboard
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        <p className="muted small">The demo is a fictional barber shop. Its dashboard is read-only and resets itself.</p>

        <ul className="features">
          <li>
            <h3>No double-booking</h3>
            <p>Each staff member's calendar is locked while a slot is claimed, and the database rejects overlaps as a backstop.</p>
          </li>
          <li>
            <h3>Real working hours</h3>
            <p>Weekly shifts, split days, clean-up buffers, minimum notice and holidays, all in your local time zone.</p>
          </li>
          <li>
            <h3>No customer accounts</h3>
            <p>Customers get a confirmation email with a private link to cancel or reschedule.</p>
          </li>
          <li>
            <h3>Know your week</h3>
            <p>Bookings per week, revenue by service and your busiest hours at a glance.</p>
          </li>
        </ul>
      </main>
    </div>
  )
}
