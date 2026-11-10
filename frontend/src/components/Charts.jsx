import { useEffect, useRef, useState } from 'react'

// Small hand-rolled SVG charts. Single series, so no legend: the card title names what's plotted.
// Specs: columns at most 24px wide with a 4px rounded top, hairline gridlines, a tooltip on hover
// and a table view, so nothing depends on seeing the colour.

function useWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

// Round the axis up to a clean number with 4 or fewer even steps (e.g. 0, 25, 50, 75, 100).
function niceTicks(max) {
  if (max <= 0) return [0, 1]
  const rough = max / 4
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= rough)
  const ticks = []
  for (let v = 0; v < max + step; v += step) ticks.push(v)
  return ticks
}

// A column whose top corners are rounded and whose base sits square on the axis.
function columnPath(x, y, w, h) {
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

export function ChartCard({ title, subtitle, table, children }) {
  const [showTable, setShowTable] = useState(false)
  return (
    <section className="card chart-card">
      <div className="chart-head">
        <div>
          <h3>{title}</h3>
          {subtitle && <p className="muted small">{subtitle}</p>}
        </div>
        <button className="link-button small" onClick={() => setShowTable((s) => !s)} aria-pressed={showTable}>
          {showTable ? 'Chart' : 'Table'}
        </button>
      </div>
      {showTable ? table : children}
    </section>
  )
}

export function DataTable({ columns, rows }) {
  return (
    <table className="data-table">
      <thead>
        <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
        ))}
      </tbody>
    </table>
  )
}

/** Vertical columns over a category axis. data: [{ label, value, tooltip }] */
export function ColumnChart({ data, formatAxis = String, height = 200, ariaLabel }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState(null)
  const margin = { top: 12, right: 8, bottom: 26, left: 44 }
  const innerW = Math.max(0, width - margin.left - margin.right)
  const innerH = height - margin.top - margin.bottom
  const ticks = niceTicks(Math.max(...data.map((d) => d.value), 0))
  const top = ticks[ticks.length - 1]
  const band = data.length ? innerW / data.length : 0
  const barW = Math.min(24, band * 0.6)
  const y = (v) => innerH - (v / top) * innerH
  // Thin out x labels when they'd collide (roughly 44px per label).
  const every = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(innerW / 44))))

  return (
    <div ref={ref} className="chart" style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={ariaLabel}>
          <g transform={`translate(${margin.left},${margin.top})`}>
            {ticks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className="grid" />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-label">{formatAxis(t)}</text>
              </g>
            ))}
            {data.map((d, i) => {
              const x = i * band + (band - barW) / 2
              const h = innerH - y(d.value)
              return (
                <g key={d.label}>
                  {h > 0 && (
                    <path d={columnPath(x, y(d.value), barW, h)}
                      className={`mark ${hover !== null && hover !== i ? 'dimmed' : ''}`} />
                  )}
                  {i % every === 0 && (
                    <text x={i * band + band / 2} y={innerH + 18} textAnchor="middle" className="axis-label">{d.label}</text>
                  )}
                  {/* Hit target: the whole band, much bigger than the bar itself. */}
                  <rect x={i * band} width={band} height={innerH} fill="transparent"
                    onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
                </g>
              )
            })}
            <line y1={innerH} y2={innerH} x2={innerW} className="baseline" />
          </g>
        </svg>
      )}
      {hover !== null && (
        <div className="tooltip" style={{
          left: Math.min(Math.max(margin.left + hover * band + band / 2, 70), width - 70),
          top: margin.top + y(data[hover].value) - 8,
        }}>
          {data[hover].tooltip}
        </div>
      )}
    </div>
  )
}

/** Horizontal bars with the value at each bar's tip. data: [{ label, value, display, tooltip }] */
export function BarList({ data }) {
  const [hover, setHover] = useState(null)
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <ul className="bar-list">
      {data.map((d, i) => (
        <li key={d.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} title={d.tooltip}>
          <span className="bar-label">{d.label}</span>
          <span className="bar-track">
            <span className={`bar ${hover !== null && hover !== i ? 'dimmed' : ''}`}
              style={{ width: `${(d.value / max) * 100}%` }} />
            <span className="bar-value">{d.display}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
