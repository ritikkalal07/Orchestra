/**
 * HeatmapView — p50/p95/p99 duration heatmap per task type.
 *
 * Surfaced directly from the durable state used for execution — no
 * separate analytics pipeline required. See FEATURES.md: 'Cost and duration heatmap'.
 */
import React, { useEffect, useState } from 'react'
import { BarChart2, X } from 'lucide-react'
import { apiFetch } from '../../hooks/useApi.js'

function DurationBar({ label, value, max, color }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)' }}>{label}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ivory)' }}>
          {value != null ? `${Math.round(value)}ms` : '—'}
        </span>
      </div>
      <div style={{ height: 4, background: 'rgba(237,230,214,0.08)', borderRadius: 2, overflow: 'hidden' }}>
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: color,
            borderRadius: 2,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
    </div>
  )
}

export function HeatmapView({ onClose }) {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('GET', '/heatmap')
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [])

  const maxP99 = Math.max(...data.map((d) => d.p99_ms || 0), 1)

  return (
    <div
      style={{
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 520,
        maxWidth: '94vw',
        maxHeight: '80vh',
        background: 'var(--wine)',
        border: '1px solid var(--color-border)',
        borderRadius: 12,
        boxShadow: 'var(--shadow-lg)',
        zIndex: 200,
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
      role="dialog"
      aria-label="Duration Heatmap"
    >
      {/* Header */}
      <div
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BarChart2 size={16} color="var(--brass)" />
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, color: 'var(--ivory)' }}>
            Duration Heatmap
          </span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ padding: '4px 8px' }}>
          <X size={14} />
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--color-muted)' }}>
            <div className="spinner" style={{ margin: '0 auto' }} />
          </div>
        ) : data.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--color-muted)', fontSize: 13 }}>
            No completed task attempts yet. Run a workflow to see duration data.
          </div>
        ) : (
          data.map((row) => (
            <div
              key={row.task_type}
              style={{
                marginBottom: 20,
                padding: '14px',
                background: 'rgba(237,230,214,0.03)',
                border: '1px solid var(--color-border)',
                borderRadius: 8,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <code style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ivory)' }}>
                  {row.task_type}
                </code>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)' }}>
                  {row.count} run{row.count !== 1 ? 's' : ''}
                </span>
              </div>
              <DurationBar label="p50" value={row.p50_ms} max={maxP99} color="var(--sage)" />
              <DurationBar label="p95" value={row.p95_ms} max={maxP99} color="var(--brass)" />
              <DurationBar label="p99" value={row.p99_ms} max={maxP99} color="var(--brick)" />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default HeatmapView
