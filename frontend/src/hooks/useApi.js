/**
 * API client hook. All requests go through here.
 * Token is read from localStorage and injected as Authorization header.
 */
import { useState, useCallback } from 'react'

const BASE = '/v1'

function getToken() {
  return localStorage.getItem('orchestra_access_token') || ''
}

export function useApi() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const request = useCallback(async (method, path, body = null) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${BASE}${path}`, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || data.message || `HTTP ${res.status}`)
      }
      return data
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const get    = useCallback((path)         => request('GET',    path),        [request])
  const post   = useCallback((path, body)   => request('POST',   path, body),  [request])
  const del    = useCallback((path)         => request('DELETE', path),        [request])

  return { get, post, del, loading, error }
}

/** Standalone helper for one-off API calls outside hooks */
export async function apiFetch(method, path, body = null) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
  return data
}
