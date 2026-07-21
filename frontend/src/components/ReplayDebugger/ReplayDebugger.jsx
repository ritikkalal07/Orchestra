/**
 * ReplayDebugger — Timeline scrub UI for deterministic replay.
 *
 * Fetches the full replay trace for a run and lets you scrub
 * forward/backward through each task attempt step-by-step,
 * showing exact inputs and outputs without re-executing anything.
 *
 * This is the same concept Temporal calls "workflow replay",
 * built small enough to explain in two minutes. See FEATURES.md.
 */
import React, { useState, useCallback } from 'react'
import { ChevronLeft, ChevronRight, Play, SkipBack } from 'lucide-react'
import { apiFetch } from '../../hooks/useApi.js'

export function ReplayDebugger({ runId, onClose }) {
  const [trace, setTrace] = useState(null)
  const [stepIndex, setStepIndex] = useState(0)
  const [loading, setLoading] = useState(false)

  const loadTrace = useCallback(async () => {
    if (!runId) return
    setLoading(true)
    try {
      const data = await apiFetch('GET', `/runs/${runId}/replay`)
      setTrace(data)
      setStepIndex(0)
    } catch (e) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }, [runId])

  const currentStep = trace?.steps?.[stepIndex]
  const total = trace?.steps?.length || 0

  const panelStyle = {
    position: 'fixed',
    bottom: 24,
    left: '50%',
    transform: 'translateX(-50%)',
    width: 680,
    maxWidth: '96vw',
    background: 'var(--wine)',
    border: '1px solid var(--color-border)',
    borderRadius: 12,
    boxShadow: 'var(--shadow-lg)',
    zIndex: 100,
    overflow: 'hidden',
  }

  return (
    <div style={panelStyle} role="dialog" aria-label="Replay Debugger">
      {/* Header */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, color: 'var(--ivory)' }}>
            Replay Debugger
          </span>
          {trace && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)' }}>
              {total} step{total !== 1 ? 's' : ''} · {trace.status}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {!trace && (
            <button className="btn btn-primary btn-sm" onClick={loadTrace} disabled={loading || !runId}>
              {loading ? 'Loading…' : <><Play size={12} /> Load trace</>}
            </button>
          )}
          {trace && (
            <button className="btn btn-ghost btn-sm" onClick={() => setTrace(null)}>
              <SkipBack size={12} /> Reset
            </button>
          )}
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
      </div>

      {/* Timeline scrubber */}
      {trace && (
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setStepIndex(Math.max(0, stepIndex - 1))}
              disabled={stepIndex === 0}
            >
              <ChevronLeft size={14} />
            </button>

            {/* Step track */}
            <div style={{ flex: 1, display: 'flex', gap: 3, alignItems: 'center' }}>
              {trace.steps.map((step, i) => (
                <button
                  key={i}
                  id={`replay-step-${i}`}
                  onClick={() => setStepIndex(i)}
                  style={{
                    flex: 1,
                    height: 6,
                    borderRadius: 3,
                    border: 'none',
                    cursor: 'pointer',
                    background:
                      i === stepIndex
                        ? 'var(--brass)'
                        : i < stepIndex
                        ? 'var(--sage)'
                        : 'rgba(237,230,214,0.1)',
                    transition: 'background 0.2s',
                  }}
                  title={`${step.task_key} (attempt ${step.attempt})`}
                />
              ))}
            </div>

            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setStepIndex(Math.min(total - 1, stepIndex + 1))}
              disabled={stepIndex === total - 1}
            >
              <ChevronRight size={14} />
            </button>

            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)', minWidth: 50, textAlign: 'right' }}>
              {stepIndex + 1} / {total}
            </span>
          </div>
        </div>
      )}

      {/* Step detail */}
      {currentStep ? (
        <div style={{ padding: '14px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {/* Left: metadata */}
          <div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Task</div>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ivory)' }}>{currentStep.task_key}</code>
              <span style={{ marginLeft: 8, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)' }}>attempt {currentStep.attempt}</span>
            </div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Duration</div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ivory)' }}>
                {currentStep.duration_ms != null ? `${currentStep.duration_ms}ms` : '—'}
              </span>
            </div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Worker</div>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-muted)' }}>{currentStep.worker_id || '—'}</code>
            </div>
            {currentStep.error && (
              <div
                style={{
                  padding: '8px 10px',
                  background: 'rgba(180,67,46,0.12)',
                  border: '1px solid rgba(180,67,46,0.25)',
                  borderRadius: 6,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  color: 'var(--brick)',
                  wordBreak: 'break-all',
                }}
              >
                {currentStep.error}
              </div>
            )}
          </div>

          {/* Right: input / output */}
          <div>
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Input snapshot</div>
              <pre style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--color-muted)', background: 'rgba(237,230,214,0.03)', padding: '6px 8px', borderRadius: 6, border: '1px solid var(--color-border)', maxHeight: 80, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(currentStep.input, null, 2) || '—'}
              </pre>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Output snapshot</div>
              <pre style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: currentStep.output ? 'var(--sage)' : 'var(--color-muted)', background: 'rgba(111,162,135,0.04)', padding: '6px 8px', borderRadius: 6, border: '1px solid rgba(111,162,135,0.1)', maxHeight: 80, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(currentStep.output, null, 2) || '—'}
              </pre>
            </div>
          </div>
        </div>
      ) : !trace ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--color-muted)', fontSize: 13 }}>
          Load the trace to scrub through the exact sequence of events — no re-execution.
        </div>
      ) : null}
    </div>
  )
}

export default ReplayDebugger
