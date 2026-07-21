/**
 * RunList — Sidebar list of workflow runs with status and timestamps.
 * Active copy voice from DESIGN.md: plain, active, engineer-facing language.
 */
import React, { useEffect, useState, useCallback } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Play, RefreshCw, ChevronRight } from 'lucide-react'
import { useApi, apiFetch } from '../../hooks/useApi.js'

const STATUS_DOT = {
  pending:   { bg: 'rgba(237,230,214,0.3)', anim: false },
  running:   { bg: 'var(--brass)',          anim: true  },
  paused:    { bg: 'rgba(201,162,75,0.5)',  anim: false },
  succeeded: { bg: 'var(--sage)',           anim: false },
  failed:    { bg: 'var(--brick)',          anim: false },
}

function RunItem({ run, isSelected, onClick }) {
  const dot = STATUS_DOT[run.status] || STATUS_DOT.pending
  const ago = run.created_at
    ? formatDistanceToNow(new Date(run.created_at), { addSuffix: true })
    : '—'

  return (
    <button
      id={`run-item-${run.id}`}
      onClick={onClick}
      style={{
        width: '100%',
        padding: '10px 16px',
        background: isSelected ? 'rgba(201,162,75,0.08)' : 'transparent',
        border: 'none',
        borderLeft: isSelected ? '2px solid var(--brass)' : '2px solid transparent',
        borderRadius: 0,
        cursor: 'pointer',
        textAlign: 'left',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        transition: 'all 0.15s ease',
      }}
      onMouseEnter={(e) => {
        if (!isSelected) e.currentTarget.style.background = 'rgba(237,230,214,0.04)'
      }}
      onMouseLeave={(e) => {
        if (!isSelected) e.currentTarget.style.background = 'transparent'
      }}
    >
      {/* Status dot */}
      <div
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: dot.bg,
          flexShrink: 0,
          animation: dot.anim ? 'blink 1.2s ease-in-out infinite' : 'none',
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--ivory)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {run.id.slice(0, 8)}…
        </div>
        <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 2 }}>
          {ago}
        </div>
      </div>
      <div
        style={{
          fontSize: 10,
          fontFamily: 'var(--font-mono)',
          color: run.status === 'running' ? 'var(--brass)'
               : run.status === 'succeeded' ? 'var(--sage)'
               : run.status === 'failed' ? 'var(--brick)'
               : 'var(--color-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        {run.status}
      </div>
    </button>
  )
}

export function RunList({ workflows, selectedWorkflow, onSelectWorkflow, selectedRun, onSelectRun }) {
  const { get, post, loading } = useApi()
  const [runs, setRuns] = useState([])
  const [triggering, setTriggering] = useState(false)

  const loadRuns = useCallback(async () => {
    if (!selectedWorkflow) return
    try {
      const data = await apiFetch('GET', `/runs?workflow_id=${selectedWorkflow.id}`)
      setRuns(data || [])
      if (data && data.length > 0 && !selectedRun) {
        // Fetch detailed run info for the first run
        const fullRun = await apiFetch('GET', `/runs/${data[0].id}`)
        onSelectRun?.(fullRun)
      }
    } catch {}
  }, [selectedWorkflow, selectedRun, onSelectRun])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  const triggerRun = async () => {
    if (!selectedWorkflow) return
    setTriggering(true)
    try {
      const result = await apiFetch('POST', `/workflows/${selectedWorkflow.id}/runs`, { input: {} })
      // Reload run data
      const runData = await apiFetch('GET', `/runs/${result.run_id}`)
      setRuns((prev) => [runData, ...prev])
      onSelectRun?.(runData)
    } catch (e) {
      alert(`Failed to trigger run: ${e.message}`)
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div
      style={{
        width: 'var(--sidebar-width)',
        height: '100%',
        background: 'var(--wine)',
        borderRight: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '16px',
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.25rem',
            fontWeight: 700,
            color: 'var(--ivory)',
            letterSpacing: '-0.02em',
          }}
        >
          Orchestra
        </h1>
        <span style={{ fontSize: 20 }}>𝄞</span>
      </div>

      {/* Workflow selector */}
      {workflows && workflows.length > 0 && (
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)' }}>
          <label style={{ fontSize: 11, color: 'var(--color-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Workflow
          </label>
          <select
            style={{
              width: '100%',
              marginTop: 6,
              background: 'rgba(237,230,214,0.05)',
              border: '1px solid var(--color-border)',
              borderRadius: 6,
              color: 'var(--ivory)',
              padding: '6px 8px',
              fontFamily: 'var(--font-body)',
              fontSize: 13,
              cursor: 'pointer',
            }}
            value={selectedWorkflow?.id || ''}
            onChange={(e) => {
              const wf = workflows.find((w) => w.id === e.target.value)
              onSelectWorkflow?.(wf)
            }}
          >
            <option value="">Select workflow…</option>
            {workflows.map((wf) => (
              <option key={wf.id} value={wf.id}>
                {wf.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Trigger run button */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)' }}>
        <button
          id="btn-trigger-run"
          className="btn btn-primary w-full"
          onClick={triggerRun}
          disabled={!selectedWorkflow || triggering}
          style={{ justifyContent: 'center', opacity: !selectedWorkflow ? 0.4 : 1 }}
        >
          {triggering ? (
            <><div className="spinner" style={{ width: 14, height: 14 }} /> Triggering…</>
          ) : (
            <><Play size={14} /> Run</>
          )}
        </button>
      </div>

      {/* Runs list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ padding: '8px 16px 4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 11, color: 'var(--color-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Runs
          </span>
          <button
            onClick={loadRuns}
            style={{ background: 'transparent', color: 'var(--color-muted)', padding: 4, borderRadius: 4 }}
            title="Refresh runs"
          >
            <RefreshCw size={12} />
          </button>
        </div>

        {runs.length === 0 ? (
          <div style={{ padding: '20px 16px', color: 'var(--color-muted)', fontSize: 13, textAlign: 'center', lineHeight: 1.6 }}>
            No runs yet. Trigger one from the CLI or click Run.
          </div>
        ) : (
          runs.map((run) => (
            <RunItem
              key={run.id}
              run={run}
              isSelected={selectedRun?.id === run.id}
              onClick={() => onSelectRun?.(run)}
            />
          ))
        )}
      </div>

      {/* Footer — auth status */}
      <div
        style={{
          padding: '10px 16px',
          borderTop: '1px solid var(--color-border)',
          fontSize: 11,
          color: 'var(--color-muted)',
          fontFamily: 'var(--font-mono)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--sage)' }} />
        admin · connected
      </div>
    </div>
  )
}

export default RunList
