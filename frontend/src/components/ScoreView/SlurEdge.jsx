/**
 * SlurEdge — Custom React Flow edge styled as a musical slur.
 *
 * A curved bezier arc connecting dependent tasks — the same visual grammar
 * as a slur in sheet music, which also reads cleanly as 'depends on'.
 * See DESIGN.md: 'connected by curved beams instead of straight edges'
 */
import React, { memo } from 'react'
import { getBezierPath, EdgeLabelRenderer } from 'reactflow'

export const SlurEdge = memo(({
  id,
  sourceX, sourceY,
  targetX, targetY,
  sourcePosition, targetPosition,
  data,
  selected,
  markerEnd,
}) => {
  // Curve upward (like a slur arc over notes)
  const midX = (sourceX + targetX) / 2
  const controlY = Math.min(sourceY, targetY) - 30

  const path = `M ${sourceX} ${sourceY} Q ${midX} ${controlY} ${targetX} ${targetY}`

  const strokeColor = selected
    ? 'var(--brass)'
    : data?.active
    ? 'rgba(201,162,75,0.6)'
    : 'rgba(237,230,214,0.15)'

  return (
    <>
      {/* Invisible wider hit area for selection */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={12}
        style={{ cursor: 'pointer' }}
      />
      {/* Visible slur arc */}
      <path
        id={id}
        d={path}
        fill="none"
        stroke={strokeColor}
        strokeWidth={selected ? 2 : 1.5}
        strokeLinecap="round"
        style={{
          transition: 'stroke 0.3s ease, stroke-width 0.2s ease',
          filter: data?.active ? 'drop-shadow(0 0 4px rgba(201,162,75,0.4))' : 'none',
        }}
      />
    </>
  )
})

SlurEdge.displayName = 'SlurEdge'
export default SlurEdge
