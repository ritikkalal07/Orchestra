/**
 * BatonLine — The signature animated element of Orchestra.
 *
 * A thin vertical line that sweeps left-to-right across the staff
 * as the run executes, driven by WebSocket state events (not a fixed
 * animation loop). The baton's X position advances when a task transitions
 * to 'running' — it lives at the X coordinate of the active task.
 *
 * This is the ONE animated element. Everything else stays still.
 * See DESIGN.md: 'Signature moment (the one place motion lives)'
 *
 * prefers-reduced-motion: baton becomes an instant state-fill (no animation).
 */
import React, { useEffect, useRef, useState } from 'react'

const CANVAS_WIDTH = 1200

export function BatonLine({ activeTaskX, isRunning, canvasWidth = CANVAS_WIDTH }) {
  const [x, setX] = useState(-40)
  const [opacity, setOpacity] = useState(0)
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  useEffect(() => {
    if (!isRunning) {
      setOpacity(0)
      return
    }
    setOpacity(1)

    if (activeTaskX != null) {
      setX(activeTaskX)
    }
  }, [activeTaskX, isRunning])

  if (!isRunning) return null

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        bottom: 0,
        left: x,
        width: 2,
        background: 'linear-gradient(to bottom, transparent, var(--brass) 20%, var(--brass) 80%, transparent)',
        opacity,
        boxShadow: '0 0 12px rgba(201,162,75,0.6), 0 0 30px rgba(201,162,75,0.2)',
        borderRadius: 1,
        pointerEvents: 'none',
        zIndex: 10,
        transition: prefersReduced
          ? 'none'
          : 'left 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease',
      }}
      aria-hidden="true"
    />
  )
}

export default BatonLine
