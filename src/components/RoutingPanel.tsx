import { useState } from 'react'
import { api, label } from '../api'
import type { Agent, Availability, RoutingState } from '../api'
import { useLiveQuery } from '../hooks/useLiveQuery'

export function RoutingPanel({ agent, onProfileChange, onSelectAgent }: {
  agent: Agent; onProfileChange: (agent: Agent) => void; onSelectAgent: (id: number) => void
}) {
  const live = useLiveQuery<RoutingState>('/routing')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const current = live.data?.agents.find((person) => person.id === agent.id)
  const supervisor = agent.role === 'TEAM_LEAD'

  async function update(availability: Availability, capacity: number) {
    setBusy(true)
    setError('')
    try {
      const profile = await api<Agent>('/agents/me/availability', { method: 'PATCH', body: JSON.stringify({ availability, max_active_chats: capacity }) })
      onProfileChange(profile)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update availability.') }
    finally { setBusy(false) }
  }

  return <div className="routing-panel">
    <div className="routing-pool-title"><strong>Shared parking pool</strong><span role="status">{live.data?.waiting_count ?? '—'} waiting</span><small>{label(agent.area)} · Balanced by available capacity</small></div>
    <div className="routing-roster">{live.data?.agents.map((person) => <button type="button" key={person.id} className="routing-agent parking-spot" onClick={() => onSelectAgent(person.id)} aria-label={`View ${person.name}'s parked cases`}><span className={`availability-dot availability-${person.availability.toLowerCase()}`} /><span>{person.name}<small>{label(person.availability)} · {person.active_chats}/{person.capacity} handles</small></span></button>)}</div>
    {!supervisor && <div className="routing-self-controls"><label>Agent status<select aria-label="Agent status" disabled={busy || !current} value={agent.availability} onChange={(event) => void update(event.target.value as Availability, agent.max_active_chats)}><option value="ONLINE">Online</option><option value="BREAK">Break</option><option value="OFFLINE">Offline</option></select></label><label>Chat capacity<select aria-label="Chat capacity" disabled={busy || !current} value={agent.max_active_chats} onChange={(event) => void update(agent.availability, Number(event.target.value))}>{Array.from({ length: 20 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{value}</option>)}</select></label></div>}
    {supervisor && <span className="monitoring-badge">Area monitoring · No chat permission</span>}
    {(error || live.error) && <p className="error" role="alert">{error || live.error}</p>}
  </div>
}
