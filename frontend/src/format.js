// Every time is shown in the *business's* time zone, not the visitor's, so a customer travelling
// or an owner checking from elsewhere sees the same 9:00 the shop does.

const cache = new Map()
function fmt(tz, options) {
  const key = tz + JSON.stringify(options)
  if (!cache.has(key)) cache.set(key, new Intl.DateTimeFormat('en-US', { timeZone: tz, ...options }))
  return cache.get(key)
}

export const formatTime = (iso, tz) => fmt(tz, { hour: 'numeric', minute: '2-digit' }).format(new Date(iso))

export const formatDateTime = (iso, tz) =>
  fmt(tz, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(
    new Date(iso),
  )

export const formatLongDateTime = (iso, tz) =>
  fmt(tz, { weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(
    new Date(iso),
  )

// Plain dates ("2026-11-10") have no time zone, so format them as UTC to avoid shifting a day.
export const formatDay = (ymd, options = { weekday: 'short', month: 'short', day: 'numeric' }) =>
  fmt('UTC', options).format(new Date(`${ymd}T00:00:00Z`))

// Hour of the day in the business's zone, e.g. 13 -> "1 PM".
export const formatHour = (h) => `${h % 12 || 12} ${h < 12 ? 'AM' : 'PM'}`

// YYYY-MM-DD of an instant in the business's zone (en-CA happens to format dates that way).
export const localDate = (iso, tz) =>
  new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(iso))

export const todayIn = (tz) => localDate(new Date().toISOString(), tz)

export function addDays(ymd, n) {
  const d = new Date(`${ymd}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

const money = new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' })
export const formatMoney = (cents) => money.format(cents / 100)
export const formatMoneyShort = (cents) =>
  cents >= 100000 ? `$${(cents / 100000).toFixed(1).replace(/\.0$/, '')}K` : `$${Math.round(cents / 100)}`

export const formatDuration = (minutes) =>
  minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ''}`

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
