/**
 * ConductorPanel — Manual override panel for mid-run interventions.
 *
 * Pause, resume, force-retry, skip tasks, and trigger Rehearsal mode
 * (deliberate chaos — kills a random worker mid-run for demos).
 * All writes go to the audit log with actor identity.
 * See FEATURES.md: 'Conductor mode' and 'Rehearsal mode'.
 */
import React, { useState } from 'react'
import { PauseCircle, PlayCircle, Zap, Shield } from 'lucide-react'
import { apiFetch } from '../../hooks/useApi.js'

export function ConductorPanel({ run, onAction, onClose }) {
  const [acting, setActing] = useState(null)

  const doAction = async (action, ...args) => {
    setActing(action)
    try {
      if (action === 'pause') {
        await apiFetch('POST', `/runs/${run.id}/pause`)
      } else if (action === 'resume') {
        await apiFetch('POST', `/runs/${run.id}/resume`)
      } else if (action === 'kill-worker') {
        await apiFetch('POST', `/runs/${run.id}/rehearsal/kill-worker`)
      }
      onAction?.()
    } catch (e) {
      alert(`Action failed: ${e.message}`)
    } finally {
      setActing(null)
    }
  }

  if (!run) return null

  const isPaused = run.status === 'paused'
  const isRunning = run.status === 'running'

  return (
    <div
      style={{
        position: 'absolute',
        top: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'var(--wine)',
        border: '1px solid var(--color-border)',
        borderRadius: 40,
        padding: '6px 12px',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      {/* Pause / Resume */}
      {isRunning && (
        <button
          id="btn-pause-run"
          className="btn btn-ghost btn-sm"
          onClick={() => doAction('pause')}
          disabled={acting !== null}
          style={{ borderRadius: 20 }}
        >
          <PauseCircle size={14} />
          {acting === 'pause' ? 'Pausing…' : 'Pause'}
        </button>
      )}
      {isPaused && (
        <button
          id="btn-resume-run"
          className="btn btn-primary btn-sm"
          onClick={() => doAction('resume')}
          disabled={acting !== null}
          style={{ borderRadius: 20 }}
        >
          <PlayCircle size={14} />
          {acting === 'resume' ? 'Resuming…' : 'Resume'}
        </button>
      )}

      {/* Divider */}
      <div style={{ width: 1, height: 20, background: 'var(--color-border)' }} />

      {/* Run status */}
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)' }}>
        {run.id.slice(0, 8)}…
      </span>
      <span className={`status-badge status-${run.status}`}>{run.status}</span>

      {/* Divider */}
      <div style={{ width: 1, height: 20, background: 'var(--color-border)' }} />

      {/* Rehearsal / Chaos mode — demo tooling */}
      <button
        id="btn-rehearsal-kill"
        onClick={() => {
          if (window.confirm('Kill the active worker mid-task? This triggers crash recovery.')) {
            doAction('kill-worker')
          }
        }}
        disabled={acting !== null || !isRunning}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 10px',
          background: 'transparent',
          border: '1px solid rgba(180,67,46,0.3)',
          borderRadius: 20,
          color: isRunning ? 'var(--brick)' : 'var(--color-muted)',
          fontFamily: 'var(--font-body)',
          fontSize: 12,
          cursor: isRunning ? 'pointer' : 'not-allowed',
          opacity: isRunning ? 1 : 0.4,
        }}
        title="Rehearsal mode: kill the active worker to demo crash recovery"
      >
        <Zap size={12} />
        {acting === 'kill-worker' ? 'Killing…' : 'Kill worker'}
      </button>

      <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ borderRadius: 20, padding: '4px 8px' }}>
        ✕
      </button>
    </div>
  )
}

export default ConductorPanel
