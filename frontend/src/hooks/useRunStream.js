/**
 * useRunStream — WebSocket stream with automatic HTTP polling fallback for Vercel Serverless.
 *
 * Connects to wss://.../v1/runs/{runId}/stream for real-time pushed events.
 * If WebSockets fail or close (e.g. on serverless hosts like Vercel),
 * it seamlessly falls back to 2-second HTTP polling to keep Score View live.
 */
import { useEffect, useRef, useCallback, useState } from 'react'

function getAuthToken() {
  return localStorage.getItem('orchestra_access_token') || ''
}

export function useRunStream(runId, onEvent) {
  const wsRef = useRef(null)
  const lastStateRef = useRef({})
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!runId) return

    let isMounted = true
    let pollInterval = null
    let reconnectTimer = null
    let retryDelay = 1000

    // HTTP polling fallback for Vercel / serverless
    const startPolling = () => {
      if (pollInterval) return
      setConnected(true) // Indicate live streaming via polling

      const poll = async () => {
        if (!isMounted) return
        try {
          const res = await fetch(`/v1/runs/${runId}`, {
            headers: getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {},
          })
          if (!res.ok) return
          const runData = await res.json()

          // Check tasks for state changes and trigger onEvent
          if (runData.tasks) {
            runData.tasks.forEach((task) => {
              const key = task.task_key
              const prevStatus = lastStateRef.current[key]
              if (prevStatus !== task.status) {
                lastStateRef.current[key] = task.status
                onEvent?.({
                  event: 'task.state_changed',
                  run_id: runId,
                  task_id: task.id,
                  task_key: task.task_key,
                  attempt: task.current_attempt,
                  from: prevStatus || 'pending',
                  to: task.status,
                })
              }
            })
          }
        } catch (e) {
          // Ignore poll errors silently
        }
      }

      poll()
      pollInterval = setInterval(poll, 2000)
    }

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host = window.location.host
      const url = `${protocol}//${host}/v1/runs/${runId}/stream`

      try {
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          if (!isMounted) return
          setConnected(true)
          retryDelay = 1000
          if (pollInterval) {
            clearInterval(pollInterval)
            pollInterval = null
          }
        }

        ws.onmessage = (evt) => {
          try {
            const event = JSON.parse(evt.data)
            if (event.event === 'ping') return
            onEvent?.(event)
          } catch (e) {
            console.warn('WS parse error', e)
          }
        }

        ws.onclose = () => {
          if (!isMounted) return
          setConnected(false)
          // Fall back to HTTP polling immediately on serverless environments
          startPolling()

          // Attempt WS reconnection occasionally
          reconnectTimer = setTimeout(() => {
            if (isMounted) {
              retryDelay = Math.min(retryDelay * 2, 30000)
              connect()
            }
          }, retryDelay)
        }

        ws.onerror = () => {
          ws?.close()
        }
      } catch (err) {
        startPolling()
      }
    }

    connect()

    return () => {
      isMounted = false
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (pollInterval) clearInterval(pollInterval)
      if (wsRef.current) wsRef.current.close()
    }
  }, [runId]) // eslint-disable-line react-hooks/exhaustive-deps

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { connected, send }
}
