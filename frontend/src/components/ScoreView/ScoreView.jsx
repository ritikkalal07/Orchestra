/**
 * ScoreView — The DAG rendered as a musical staff.
 *
 * Five faint horizontal staff lines run the width of the canvas.
 * Tasks are circular notes positioned by:
 *   x-axis: execution order (topological position)
 *   y-axis: DAG depth (which staff line)
 * Dependencies are curved slur arcs.
 * The baton sweeps left-to-right driven by live WebSocket events.
 *
 * This is the signature element. See DESIGN.md for full spec.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { NoteNode } from './NoteNode.jsx'
import { SlurEdge } from './SlurEdge.jsx'
import { BatonLine } from './BatonLine.jsx'
import { useRunStream } from '../../hooks/useRunStream.js'

const nodeTypes = { note: NoteNode }
const edgeTypes = { slur: SlurEdge }

const STAFF_LINES = 5
const NOTE_X_STEP = 160
const NOTE_Y_BASE = 120
const STAFF_Y_STEP = 80
const NOTE_X_OFFSET = 100

function buildGraph(tasks) {
  if (!tasks || tasks.length === 0) return { nodes: [], edges: [] }

  // Compute topological order and depth for layout
  const taskMap = {}
  tasks.forEach((t) => { taskMap[t.task_key] = t })

  // Compute depth (longest path from root)
  const depths = {}
  function depth(key) {
    if (key in depths) return depths[key]
    const task = taskMap[key]
    const deps = task?.depends_on || []
    depths[key] = deps.length === 0 ? 0 : Math.max(...deps.map(depth)) + 1
    return depths[key]
  }
  tasks.forEach((t) => depth(t.task_key))

  // Compute x-position by topological order
  const inDegree = {}
  const adj = {}
  tasks.forEach((t) => {
    inDegree[t.task_key] = 0
    adj[t.task_key] = []
  })
  tasks.forEach((t) => {
    ;(t.depends_on || []).forEach((dep) => {
      adj[dep]?.push(t.task_key)
      inDegree[t.task_key] = (inDegree[t.task_key] || 0) + 1
    })
  })
  const queue = Object.keys(inDegree).filter((k) => inDegree[k] === 0)
  const xPos = {}
  let x = 0
  while (queue.length) {
    const node = queue.shift()
    xPos[node] = x++
    adj[node].forEach((n) => {
      inDegree[n]--
      if (inDegree[n] === 0) queue.push(n)
    })
  }

  const nodes = tasks.map((task) => ({
    id: task.task_key,
    type: 'note',
    position: {
      x: NOTE_X_OFFSET + (xPos[task.task_key] || 0) * NOTE_X_STEP,
      y: NOTE_Y_BASE + (depths[task.task_key] || 0) * STAFF_Y_STEP,
    },
    data: {
      label: task.task_key,
      status: task.status,
      attempt: task.current_attempt,
      isRetry: task.current_attempt > 0,
    },
  }))

  const edges = []
  tasks.forEach((task) => {
    ;(task.depends_on || []).forEach((dep) => {
      edges.push({
        id: `${dep}->${task.task_key}`,
        source: dep,
        target: task.task_key,
        type: 'slur',
        data: {
          active:
            taskMap[dep]?.status === 'succeeded' &&
            task.status === 'running',
        },
      })
    })
  })

  return { nodes, edges }
}

function StaffLines({ height, width }) {
  // Five faint horizontal ivory-at-8%-opacity lines — the musical staff
  const linePositions = Array.from({ length: STAFF_LINES }, (_, i) =>
    NOTE_Y_BASE + i * STAFF_Y_STEP + 26 // center on note rows
  )
  return (
    <svg
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 0 }}
      width={width}
      height={height}
      aria-hidden="true"
    >
      {linePositions.map((y, i) => (
        <line
          key={i}
          x1={0}
          y1={y}
          x2={width}
          y2={y}
          stroke="rgba(237,230,214,0.08)"
          strokeWidth={1}
        />
      ))}
    </svg>
  )
}

function ScoreViewInner({ run, tasks, onTaskSelect }) {
  const containerRef = useRef(null)
  const [containerSize, setContainerSize] = useState({ width: 1200, height: 600 })
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [activeTaskX, setActiveTaskX] = useState(null)

  // Observe container size
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      setContainerSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Build graph from tasks
  useEffect(() => {
    const { nodes: n, edges: e } = buildGraph(tasks)
    setNodes(n)
    setEdges(e)
  }, [tasks]) // eslint-disable-line

  // Update node states on task changes (live WS updates)
  const updateTaskState = useCallback(
    (taskKey, newStatus, attempt) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === taskKey
            ? {
                ...n,
                data: {
                  ...n.data,
                  status: newStatus,
                  attempt: attempt ?? n.data.attempt,
                  isRetry: (attempt ?? n.data.attempt) > 0,
                },
              }
            : n
        )
      )
      // Move baton to running task's X position
      if (newStatus === 'running') {
        setNodes((nds) => {
          const node = nds.find((n) => n.id === taskKey)
          if (node) setActiveTaskX(node.position.x + 26) // center of note
          return nds
        })
      }
    },
    [setNodes]
  )

  // Subscribe to live WebSocket events
  const isRunning = run?.status === 'running'
  const { connected } = useRunStream(
    run?.id,
    useCallback(
      (event) => {
        if (event.event === 'task.state_changed') {
          updateTaskState(event.task_key, event.to, event.attempt)
        }
      },
      [updateTaskState]
    )
  )

  const onNodeClick = useCallback(
    (_, node) => {
      const task = tasks?.find((t) => t.task_key === node.id)
      if (task) onTaskSelect?.(task)
    },
    [tasks, onTaskSelect]
  )

  const isLive = isRunning

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        background: 'var(--ink)',
        overflow: 'hidden',
      }}
    >
      {/* Musical staff lines behind the canvas */}
      <StaffLines width={containerSize.width} height={containerSize.height} />

      {/* Live baton sweep — the ONE animated element */}
      <BatonLine activeTaskX={activeTaskX} isRunning={isLive} />

      {/* WS connection indicator */}
      {run?.id && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            right: 16,
            zIndex: 20,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: connected ? 'var(--sage)' : 'var(--color-muted)',
          }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: connected ? 'var(--sage)' : 'var(--color-muted)',
              animation: connected && isLive ? 'blink 1.2s ease-in-out infinite' : 'none',
            }}
          />
          {connected ? 'live' : 'connecting…'}
        </div>
      )}

      {/* Empty state */}
      {(!tasks || tasks.length === 0) && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 12,
            pointerEvents: 'none',
          }}
        >
          <div style={{ fontSize: 40, opacity: 0.3 }}>𝄞</div>
          <p
            style={{
              color: 'var(--color-muted)',
              fontFamily: 'var(--font-body)',
              fontSize: 14,
              textAlign: 'center',
            }}
          >
            {run ? 'No runs yet. Trigger one from the CLI or click Run.' : 'Select a workflow run to watch it perform.'}
          </p>
        </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: 'transparent' }}
      >
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={(n) => {
            const s = n.data?.status
            if (s === 'succeeded') return 'var(--sage)'
            if (s === 'running' || s === 'claimed') return 'var(--brass)'
            if (s === 'failed' || s === 'dead_letter') return 'var(--brick)'
            return 'rgba(237,230,214,0.15)'
          }}
          maskColor="rgba(20,16,14,0.7)"
        />
      </ReactFlow>
    </div>
  )
}

export function ScoreView(props) {
  return (
    <ReactFlowProvider>
      <ScoreViewInner {...props} />
    </ReactFlowProvider>
  )
}

export default ScoreView
