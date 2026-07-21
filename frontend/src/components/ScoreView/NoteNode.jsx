/**
 * NoteNode — Custom React Flow node styled as a musical note.
 *
 * A circular note positioned on the staff. Color reflects task state:
 *   pending      → dim ivory ring
 *   running      → brass, pulsing
 *   succeeded    → sage, filled
 *   failed       → brick, with hairline crack
 *   dead_letter  → brick, darker
 *   skipped      → muted
 *
 * See DESIGN.md: 'tasks are circular notes… colored by state'
 */
import React, { memo } from 'react'
import { Handle, Position } from 'reactflow'

const STATE_STYLES = {
  pending: {
    bg: 'transparent',
    border: '2px solid rgba(237,230,214,0.25)',
    shadow: 'none',
    label: 'rgba(237,230,214,0.4)',
    pulse: false,
  },
  claimed: {
    bg: 'rgba(201,162,75,0.2)',
    border: '2px solid var(--brass)',
    shadow: '0 0 12px rgba(201,162,75,0.35)',
    label: 'var(--brass)',
    pulse: true,
  },
  running: {
    bg: 'rgba(201,162,75,0.25)',
    border: '2px solid var(--brass)',
    shadow: '0 0 20px rgba(201,162,75,0.5)',
    label: 'var(--brass)',
    pulse: true,
  },
  checkpointing: {
    bg: 'rgba(201,162,75,0.2)',
    border: '2px dashed var(--brass)',
    shadow: '0 0 12px rgba(201,162,75,0.3)',
    label: 'var(--brass)',
    pulse: true,
  },
  succeeded: {
    bg: 'var(--sage)',
    border: '2px solid var(--sage)',
    shadow: '0 0 16px rgba(111,162,135,0.4)',
    label: 'var(--ink)',
    pulse: false,
  },
  failed: {
    bg: 'rgba(180,67,46,0.3)',
    border: '2px solid var(--brick)',
    shadow: '0 0 12px rgba(180,67,46,0.35)',
    label: 'var(--brick)',
    pulse: false,
    crack: true,
  },
  dead_letter: {
    bg: 'var(--brick)',
    border: '2px solid #8a2315',
    shadow: '0 0 16px rgba(180,67,46,0.5)',
    label: 'var(--ivory)',
    pulse: false,
    crack: true,
  },
  skipped: {
    bg: 'transparent',
    border: '2px dashed rgba(237,230,214,0.15)',
    shadow: 'none',
    label: 'rgba(237,230,214,0.2)',
    pulse: false,
  },
}

export const NoteNode = memo(({ data, selected }) => {
  const { label, status, attempt, isRetry } = data
  const style = STATE_STYLES[status] || STATE_STYLES.pending

  return (
    <div style={{ position: 'relative' }}>
      {/* Ghost note for retried tasks — grace note visual */}
      {isRetry && (
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '-18px',
            transform: 'translateY(-50%)',
            width: 28,
            height: 28,
            borderRadius: '50%',
            border: '1px solid rgba(201,162,75,0.3)',
            background: 'rgba(201,162,75,0.08)',
            opacity: 0.5,
            pointerEvents: 'none',
          }}
        />
      )}

      {/* The note circle */}
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: '50%',
          background: style.bg,
          border: style.border,
          boxShadow: `${style.shadow}${selected ? ', 0 0 0 3px rgba(201,162,75,0.5)' : ''}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          animation: style.pulse ? 'pulse-brass 2s infinite' : 'none',
          transition: 'all 0.3s ease',
          position: 'relative',
          overflow: 'hidden',
        }}
        title={`${label} — ${status}${attempt > 0 ? ` (attempt ${attempt + 1})` : ''}`}
      >
        {/* Hairline crack for failed/dead_letter — 'a wrong note' from DESIGN.md */}
        {style.crack && (
          <svg
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
            viewBox="0 0 52 52"
            fill="none"
          >
            <path
              d="M26 8 L24 18 L28 22 L22 34 L26 44"
              stroke="rgba(237,230,214,0.4)"
              strokeWidth="1"
              strokeLinecap="round"
            />
          </svg>
        )}

        {/* Attempt counter badge */}
        {attempt > 0 && (
          <div
            style={{
              position: 'absolute',
              top: -4,
              right: -4,
              width: 16,
              height: 16,
              borderRadius: '50%',
              background: 'var(--brick)',
              color: 'var(--ivory)',
              fontSize: '9px',
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid var(--ink)',
            }}
          >
            {attempt + 1}
          </div>
        )}
      </div>

      {/* Label below the note */}
      <div
        style={{
          position: 'absolute',
          top: 58,
          left: '50%',
          transform: 'translateX(-50%)',
          whiteSpace: 'nowrap',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: style.label,
          letterSpacing: '0.05em',
          maxWidth: 80,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          textAlign: 'center',
        }}
      >
        {label}
      </div>

      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  )
})

NoteNode.displayName = 'NoteNode'
export default NoteNode
