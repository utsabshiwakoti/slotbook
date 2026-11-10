import { Link, useOutletContext } from 'react-router'
import { api } from '../../api'
import { BarList, ChartCard, ColumnChart, DataTable } from '../../components/Charts'
import { formatDay, formatHour, formatMoney, formatMoneyShort, formatTime } from '../../format'
import useLoad from '../../useLoad'

export default function Overview() {
  const { business } = useOutletContext()
  const tz = business.timezone
  const stats = useLoad(() => api('/admin/stats', { params: { weeks: 8 } }), [])
  const today = useLoad(() => api('/admin/bookings', { params: { days: 1, status: 'confirmed' } }), [])

  if (stats.loading) return <p className="muted">Loading…</p>
  if (stats.error) return <p className="error">{stats.error.message}</p>
  const s = stats.data

  const weeks = s.weeks.map((w) => ({
    label: formatDay(w.week_start, { month: 'short', day: 'numeric' }),
    value: w.bookings,
    tooltip: (
      <>
        <strong>Week of {formatDay(w.week_start, { month: 'long', day: 'numeric' })}</strong>
        <span>{w.bookings} bookings · {formatMoney(w.revenue_cents)}</span>
      </>
    ),
  }))
  const hours = s.by_hour.map((h) => ({
    label: formatHour(h.hour).replace(' ', ''),
    value: h.bookings,
    tooltip: (
      <>
        <strong>{formatHour(h.hour)}</strong>
        <span>{h.bookings} bookings starting this hour</span>
      </>
    ),
  }))

  return (
    <div className="stack-lg">
      <h1>Overview</h1>

      <div className="tiles">
        <Tile label="Upcoming bookings" value={s.upcoming} />
        <Tile label="Bookings, last 8 weeks" value={s.total_bookings} />
        <Tile label="Revenue, last 8 weeks" value={formatMoney(s.total_revenue_cents)} />
        <Tile label="Cancellation rate" value={`${Math.round(s.cancellation_rate * 100)}%`} />
      </div>

      <div className="grid-2">
        <ChartCard title="Bookings per week" subtitle="Confirmed bookings, by week they take place"
          table={<DataTable columns={['Week of', 'Bookings', 'Revenue']}
            rows={s.weeks.map((w) => [formatDay(w.week_start), w.bookings, formatMoney(w.revenue_cents)])} />}>
          <ColumnChart data={weeks} ariaLabel="Bookings per week" />
        </ChartCard>

        <ChartCard title="Busiest hours" subtitle={`Bookings by start time (${tz})`}
          table={<DataTable columns={['Hour', 'Bookings']} rows={s.by_hour.map((h) => [formatHour(h.hour), h.bookings])} />}>
          {hours.length ? <ColumnChart data={hours} ariaLabel="Bookings by hour of day" /> : <p className="empty">No bookings yet.</p>}
        </ChartCard>

        <ChartCard title="Revenue by service" subtitle="Last 8 weeks"
          table={<DataTable columns={['Service', 'Bookings', 'Revenue']}
            rows={s.by_service.map((r) => [r.service, r.bookings, formatMoney(r.revenue_cents)])} />}>
          {s.by_service.length ? (
            <BarList data={s.by_service.map((r) => ({
              label: r.service, value: r.revenue_cents, display: formatMoneyShort(r.revenue_cents),
              tooltip: `${r.service}: ${r.bookings} bookings, ${formatMoney(r.revenue_cents)}`,
            }))} />
          ) : <p className="empty">No bookings yet.</p>}
        </ChartCard>

        <section className="card">
          <div className="chart-head">
            <h3>Today</h3>
            <Link to="/admin/bookings" className="small">All bookings →</Link>
          </div>
          {today.loading ? <p className="muted">Loading…</p> : today.data?.length ? (
            <ul className="today-list">
              {today.data.slice(0, 8).map((b) => (
                <li key={b.id}>
                  <span className="time">{formatTime(b.starts_at, tz)}</span>
                  <span>{b.customer_name}<span className="muted small block">{b.service.name} · {b.staff.name}</span></span>
                </li>
              ))}
            </ul>
          ) : <p className="empty">Nothing booked today.</p>}
          {today.data?.length > 8 && <p className="muted small">and {today.data.length - 8} more</p>}
        </section>
      </div>
    </div>
  )
}

function Tile({ label, value }) {
  return (
    <div className="card tile">
      <span className="tile-value">{value}</span>
      <span className="muted small">{label}</span>
    </div>
  )
}
