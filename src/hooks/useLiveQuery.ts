import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'

type Connection = 'connecting' | 'live' | 'reconnecting' | 'ended'

// REST checks access first. SSE then sends complete, authorized snapshots.
// A reconnect fetches current state, recovering any replies missed offline.
export function useLiveQuery<T>(path: string) {
  const [state, setState] = useState<{ path: string; data: T | null; error: string; connection: Connection }>({ path, data: null, error: '', connection: 'connecting' })

  useEffect(() => {
    let active = true
    let source: EventSource | undefined
    let retry: ReturnType<typeof setTimeout> | undefined
    const controller = new AbortController()

    function reconnect() {
      source?.close()
      if (!active) return
      setState((previous) => ({ ...previous, connection: 'reconnecting' }))
      retry = setTimeout(connect, 3000)
    }

    async function connect() {
      try {
        const data = await api<T>(path, { signal: controller.signal })
        if (!active) return
        setState({ path, data, error: '', connection: 'connecting' })
        const [pathname, query] = path.split('?')
        source = new EventSource(`/api${pathname}/live${query ? `?${query}` : ''}`)

        source.addEventListener('snapshot', (event) => {
          if (!active) return
          setState({ path, data: JSON.parse(event.data) as T, error: '', connection: 'live' })
        })
        source.addEventListener('denied', () => {
          source?.close()
          if (active) setState({ path, data: null, error: 'Access ended. Sign in again or reopen your ticket.', connection: 'ended' })
        })
        source.onerror = reconnect
      } catch (failure) {
        if (!active) return
        if (failure instanceof ApiError && [401, 403, 404].includes(failure.status)) {
          setState({ path, data: null, error: failure.message, connection: 'ended' })
        } else {
          setState((previous) => ({ ...previous, path, error: 'Connection interrupted. Retrying automatically…', connection: 'reconnecting' }))
          retry = setTimeout(connect, 3000)
        }
      }
    }

    void connect()
    return () => {
      active = false
      controller.abort()
      source?.close()
      clearTimeout(retry)
    }
  }, [path])

  // Hide rows from the previous filter/ticket while the new path loads.
  return state.path === path ? state : { path, data: null, error: '', connection: 'connecting' as Connection }
}
