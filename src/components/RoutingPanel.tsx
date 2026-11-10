import { useState } from 'react'
import { api } from '../api'
import type { Agent, RoutingState } from '../api'
import { useLiveQuery } from '../hooks/useLiveQuery'

export function RoutingPanel({ agent }: { agent: Agent }) {
  const live = useLiveQuery<RoutingState>('/routing')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const current = live.data?.agents.find((person) => person.id === agent.id)

  async function update(available: boolean, capacity: number) {
    setBusy(true)
    setError('')
    try {
      await api('/agents/me/availability', { method: 'PATCH', body: JSON.stringify({ is_available: available, max_active_chats: capacity }) })
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update routing availability.') }
    finally { setBusy(false) }
  }

  return <div className="routing-panel">
    <div className="routing-pool-title"><strong>T1 client pool</strong><span role="status">{live.data?.waiting_count ?? '—'} waiting</span><small>Oldest waiting case → least-loaded eligible agent</small></div>
    <div className="routing-roster">{live.data?.agents.map((person) => <div key={person.id} className="routing-agent"><span className={`availability-dot ${person.is_available && person.signed_in ? 'available' : ''}`} /><span>{person.name}<small>{person.tier} · {person.active_chats}/{person.capacity} active · {person.is_available && person.signed_in ? 'Accepting' : 'Not accepting'}</small></span></div>)}</div>
    <div className="routing-self-controls"><label>Chat capacity<select aria-label="Chat capacity" disabled={busy || !current} value={current?.capacity ?? agent.max_active_chats} onChange={(event) => void update(current?.is_available ?? false, Number(event.target.value))}>{Array.from({ length: 20 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{value}</option>)}</select></label><button className="secondary-button" disabled={busy || !current} onClick={() => void update(!current?.is_available, current?.capacity ?? agent.max_active_chats)}>{busy ? 'Saving…' : current?.is_available ? 'Pause new chats' : 'Accept new chats'}</button></div>
    {(error || live.error) && <p className="error" role="alert">{error || live.error}</p>}
  </div>
}
