/**
 * TaskDetail — Per-task detail panel.
 *
 * Shows task state, attempt history, error details, checkpoint steps.
 * Copy voice per DESIGN.md: actionable, not apologetic.
 * e.g. "Task `send-notification` failed after 3 attempts. Next retry in 47s, or resume manually."
 */
import React, { useState } from 'react'
import { X, RotateCcw, SkipForward, AlertTriangle, CheckCircle, Clock } from 'lucide-react'
import { apiFetch } from '../../hooks/useApi.js'

function StatusIcon({ status }) {
  if (status === 'succeeded') return <CheckCircle size={14} color="var(--sage)" />
  if (status === 'failed' || status === 'dead_letter') return <AlertTriangle size={14} color="var(--brick)" />
  if (status === 'running') return <Clock size={14} color="var(--brass)" />
  return null
}

export function TaskDetail({ task, runId, onClose, onAction }) {
  const [acting, setActing] = useState(null)

  if (!task) return null

  const isFailed = task.status === 'failed' || task.status === 'dead_letter'
  const isRunning = task.status === 'running' || task.status === 'claimed'

  const doAction = async (action) => {
    setActing(action)
    try {
      if (action === 'retry') {
        await apiFetch('POST', `/runs/${runId}/tasks/${task.task_key}/retry`)
      } else if (action === 'skip') {
        await apiFetch('POST', `/runs/${runId}/tasks/${task.task_key}/skip`)
      }
      onAction?.()
    } catch (e) {
      alert(e.message)
    } finally {
      setActing(null)
    }
  }

  return (
    <div
      style={{
        width: 'var(--detail-width)',
        height: '100%',
        background: 'var(--wine)',
        borderLeft: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        overflow: 'hidden',
      }}
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
          <StatusIcon status={task.status} />
          <code style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ivory)' }}>
            {task.task_key}
          </code>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'transparent', color: 'var(--color-muted)', padding: 4, borderRadius: 4 }}
        >
          <X size={14} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
        {/* Status + type */}
        <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <span className={`status-badge status-${task.status}`}>
            {task.status}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)', padding: '2px 8px', background: 'rgba(237,230,214,0.05)', borderRadius: 20 }}>
            {task.task_type}
          </span>
        </div>

        {/* Failure message — actionable, not apologetic */}
        {isFailed && (
          <div
            style={{
              marginBottom: 16,
              padding: '10px 12px',
              background: 'rgba(180,67,46,0.12)',
              border: '1px solid rgba(180,67,46,0.25)',
              borderRadius: 8,
              fontSize: 13,
              lineHeight: 1.5,
              color: 'var(--ivory)',
            }}
          >
            Task <code style={{ fontFamily: 'var(--font-mono)' }}>`{task.task_key}`</code> failed after{' '}
            {task.current_attempt + 1} attempt{task.current_attempt !== 0 ? 's' : ''}.
            {task.status === 'dead_letter' && ' Max retries reached.'}
            {task.status === 'failed' && ' Retry now or skip to continue downstream.'}
          </div>
        )}

        {/* Error detail */}
        {task.error_detail && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Error
            </div>
            <pre
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--brick)',
                background: 'rgba(180,67,46,0.08)',
                padding: '8px 10px',
                borderRadius: 6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                border: '1px solid rgba(180,67,46,0.15)',
              }}
            >
              {task.error_detail}
            </pre>
          </div>
        )}

        {/* Attempts */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Attempts
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ivory)' }}>
            {task.current_attempt + 1} / {task.max_attempts}
          </div>
        </div>

        {/* Dependencies */}
        {task.depends_on?.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Depends On
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {task.depends_on.map((dep) => (
                <code key={dep} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, background: 'rgba(237,230,214,0.06)', padding: '2px 8px', borderRadius: 20, color: 'var(--color-muted)' }}>
                  {dep}
                </code>
              ))}
            </div>
          </div>
        )}

        {/* Output data */}
        {task.output_data && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Output
            </div>
            <pre
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--ivory)',
                background: 'rgba(111,162,135,0.05)',
                padding: '8px 10px',
                borderRadius: 6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                border: '1px solid rgba(111,162,135,0.1)',
                maxHeight: 200,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(task.output_data, null, 2)}
            </pre>
          </div>
        )}

        {/* Input data */}
        {task.input_data && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Input
            </div>
            <pre
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--color-muted)',
                background: 'rgba(237,230,214,0.03)',
                padding: '8px 10px',
                borderRadius: 6,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                border: '1px solid var(--color-border)',
                maxHeight: 150,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(task.input_data, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* Actions — Conductor mode */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--color-border)',
          display: 'flex',
          gap: 8,
        }}
      >
        <button
          id={`btn-retry-${task.task_key}`}
          className="btn btn-ghost btn-sm"
          onClick={() => doAction('retry')}
          disabled={acting !== null || isRunning}
          style={{ flex: 1 }}
        >
          <RotateCcw size={12} />
          {acting === 'retry' ? 'Retrying…' : 'Retry now'}
        </button>
        <button
          id={`btn-skip-${task.task_key}`}
          className="btn btn-ghost btn-sm"
          onClick={() => doAction('skip')}
          disabled={acting !== null}
          style={{ flex: 1 }}
        >
          <SkipForward size={12} />
          {acting === 'skip' ? 'Skipping…' : 'Skip'}
        </button>
      </div>
    </div>
  )
}

export default TaskDetail
