/**
 * App — Main application shell.
 *
 * Layout:
 *   [Sidebar: RunList] | [Main: Score View + toolbar] | [Right: TaskDetail (conditional)]
 *
 * Floating:
 *   ConductorPanel (above Score View when a run is selected)
 *   ReplayDebugger (bottom overlay, toggleable)
 *   HeatmapView (modal)
 *
 * Auth: login screen → JWT stored in localStorage → all subsequent requests authorized.
 */
import React, { useState, useEffect, useCallback } from 'react'
import { BarChart2, Film, Sliders, LogOut, Key } from 'lucide-react'

import { RunList } from './components/RunList/RunList.jsx'
import { ScoreView } from './components/ScoreView/ScoreView.jsx'
import { TaskDetail } from './components/TaskDetail/TaskDetail.jsx'
import { ConductorPanel } from './components/ConductorPanel/ConductorPanel.jsx'
import { ReplayDebugger } from './components/ReplayDebugger/ReplayDebugger.jsx'
import { HeatmapView } from './components/HeatmapView/HeatmapView.jsx'
import { apiFetch } from './hooks/useApi.js'

// ---------------------------------------------------------------------------
// Login screen
// ---------------------------------------------------------------------------

function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await fetch('/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      }).then((r) => r.json())

      if (!data.access_token) throw new Error(data.detail || 'Login failed')

      localStorage.setItem('orchestra_access_token', data.access_token)
      localStorage.setItem('orchestra_refresh_token', data.refresh_token)
      onLogin()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--ink)',
        backgroundImage: `
          repeating-linear-gradient(0deg, transparent, transparent 79px, rgba(237,230,214,0.05) 80px)
        `,
      }}
    >
      <div
        style={{
          width: 360,
          padding: '40px 36px',
          background: 'var(--wine)',
          border: '1px solid var(--color-border)',
          borderRadius: 16,
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>𝄞</div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem', marginBottom: 6 }}>
            Orchestra
          </h1>
          <p style={{ color: 'var(--color-muted)', fontSize: 14 }}>
            Workflow orchestrator
          </p>
        </div>

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--color-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Username
            </label>
            <input
              id="input-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={inputStyle}
              placeholder="admin"
              autoComplete="username"
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--color-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Password
            </label>
            <input
              id="input-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
              placeholder="admin123"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div style={{ color: 'var(--brick)', fontSize: 13, padding: '8px 12px', background: 'rgba(180,67,46,0.1)', borderRadius: 6 }}>
              {error}
            </div>
          )}

          <button
            id="btn-login"
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ justifyContent: 'center', marginTop: 6 }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div style={{ marginTop: 24, padding: '12px', background: 'rgba(201,162,75,0.06)', borderRadius: 8, border: '1px solid rgba(201,162,75,0.15)' }}>
          <div style={{ fontSize: 11, color: 'var(--color-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Demo credentials</div>
          {[['admin', 'admin123', 'Full access'], ['operator', 'op123', 'Trigger & manage runs'], ['viewer', 'view123', 'Read-only']].map(([u, p, role]) => (
            <div key={u} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--brass)' }}>{u} / {p}</code>
              <span style={{ fontSize: 11, color: 'var(--color-muted)' }}>{role}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

const inputStyle = {
  width: '100%',
  marginTop: 6,
  padding: '9px 12px',
  background: 'rgba(237,230,214,0.05)',
  border: '1px solid var(--color-border)',
  borderRadius: 8,
  color: 'var(--ivory)',
  fontFamily: 'var(--font-body)',
  fontSize: 14,
  outline: 'none',
  transition: 'border-color 0.2s',
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------

export default function App() {
  const [authed, setAuthed] = useState(!!localStorage.getItem('orchestra_access_token'))
  const [workflows, setWorkflows] = useState([])
  const [selectedWorkflow, setSelectedWorkflow] = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)
  const [selectedTask, setSelectedTask] = useState(null)
  const [showReplay, setShowReplay] = useState(false)
  const [showHeatmap, setShowHeatmap] = useState(false)
  const [showConductor, setShowConductor] = useState(false)

  // Load workflows on login
  useEffect(() => {
    if (!authed) return
    apiFetch('GET', '/workflows')
      .then((data) => {
        setWorkflows(data || [])
        if (data && data.length > 0 && !selectedWorkflow) {
          setSelectedWorkflow(data[0])
        }
      })
      .catch(() => {})
  }, [authed])

  // Refresh run data when an action is taken
  const refreshRun = useCallback(async () => {
    if (!selectedRun) return
    try {
      const data = await apiFetch('GET', `/runs/${selectedRun.id}`)
      setSelectedRun(data)
    } catch {}
  }, [selectedRun])

  if (!authed) {
    return <LoginScreen onLogin={() => setAuthed(true)} />
  }

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--ink)',
        overflow: 'hidden',
      }}
    >
      {/* Top bar */}
      <header
        style={{
          height: 'var(--header-height)',
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 20px',
          gap: 16,
          background: 'var(--wine)',
          flexShrink: 0,
          zIndex: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
          <span style={{ fontSize: 22 }}>𝄞</span>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '1.1rem',
              fontWeight: 700,
              color: 'var(--ivory)',
              letterSpacing: '-0.02em',
            }}
          >
            Orchestra
          </h1>
          {selectedRun && (
            <>
              <span style={{ color: 'var(--color-border)' }}>›</span>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-muted)' }}>
                {selectedRun.id.slice(0, 12)}…
              </code>
              <span className={`status-badge status-${selectedRun.status}`}>
                {selectedRun.status}
              </span>
            </>
          )}
        </div>

        {/* Toolbar */}
        <div style={{ display: 'flex', gap: 8 }}>
          {selectedRun && (
            <>
              <button
                id="btn-conductor"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowConductor((v) => !v)}
                style={{ gap: 6 }}
                title="Conductor mode — manual overrides"
              >
                <Sliders size={13} />
                Conductor
              </button>
              <button
                id="btn-replay"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowReplay((v) => !v)}
                style={{ gap: 6 }}
                title="Replay debugger — scrub through the run"
              >
                <Film size={13} />
                Replay
              </button>
            </>
          )}
          <button
            id="btn-heatmap"
            className="btn btn-ghost btn-sm"
            onClick={() => setShowHeatmap(true)}
            title="Duration heatmap"
          >
            <BarChart2 size={13} />
          </button>
          <button
            id="btn-logout"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              localStorage.clear()
              setAuthed(false)
            }}
            title="Sign out"
          >
            <LogOut size={13} />
          </button>
        </div>
      </header>

      {/* Main layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left sidebar — run list */}
        <RunList
          workflows={workflows}
          selectedWorkflow={selectedWorkflow}
          onSelectWorkflow={setSelectedWorkflow}
          selectedRun={selectedRun}
          onSelectRun={setSelectedRun}
        />

        {/* Center — Score View */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          {/* Conductor panel floats above */}
          {showConductor && selectedRun && (
            <ConductorPanel
              run={selectedRun}
              onAction={refreshRun}
              onClose={() => setShowConductor(false)}
            />
          )}

          <ScoreView
            run={selectedRun}
            tasks={selectedRun?.tasks || []}
            onTaskSelect={(task) => {
              setSelectedTask(task)
            }}
          />

          {/* Replay debugger floats at bottom */}
          {showReplay && selectedRun && (
            <ReplayDebugger
              runId={selectedRun.id}
              onClose={() => setShowReplay(false)}
            />
          )}
        </div>

        {/* Right panel — task detail */}
        {selectedTask && (
          <TaskDetail
            task={selectedTask}
            runId={selectedRun?.id}
            onClose={() => setSelectedTask(null)}
            onAction={() => {
              refreshRun()
              setSelectedTask(null)
            }}
          />
        )}
      </div>

      {/* Heatmap modal */}
      {showHeatmap && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, background: 'rgba(20,16,14,0.7)', zIndex: 190 }}
            onClick={() => setShowHeatmap(false)}
          />
          <HeatmapView onClose={() => setShowHeatmap(false)} />
        </>
      )}
    </div>
  )
}
