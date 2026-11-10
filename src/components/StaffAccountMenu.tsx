import { useEffect, useRef, useState } from 'react'
import { api, label } from '../api'
import type { Agent, Availability } from '../api'

export function StaffAccountMenu({ agent, onProfileChange, signOut, signingOut }: {
  agent: Agent; onProfileChange: (value: Agent) => void; signOut: () => void; signingOut: boolean
}) {
  const menu = useRef<HTMLDetailsElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    function dismiss(event: PointerEvent) {
      if (menu.current && !menu.current.contains(event.target as Node)) menu.current.open = false
    }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [])

  async function update(availability: Availability) {
    setBusy(true)
    setError('')
    try {
      onProfileChange(await api<Agent>('/agents/me/availability', {
        method: 'PATCH', body: JSON.stringify({ availability }),
      }))
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update your availability.') }
    finally { setBusy(false) }
  }

  return <details className="staff-account-menu" ref={menu} onKeyDown={(event) => { if (event.key === 'Escape' && menu.current) { menu.current.open = false; menu.current.querySelector('summary')?.focus() } }}>
    <summary aria-label="Staff account"><span className="avatar">{agent.name.slice(0, 1)}</span><span>{agent.name}<small>{agent.role === 'ADMIN' ? 'Administrator' : agent.role === 'TEAM_LEAD' ? 'Team leader' : label(agent.availability)}</small></span><span aria-hidden="true">⌄</span></summary>
    <div className="staff-account-options">
      <strong>{agent.name}</strong><small>{agent.email}</small>
      {agent.role === 'AGENT' && <>
        <label>Agent status<select aria-label="Agent status" value={agent.availability} disabled={busy} onChange={(event) => void update(event.target.value as Availability)}><option value="ONLINE">Online</option><option value="BREAK">Break</option><option value="OFFLINE">Offline</option></select></label>

      </>}
      {error && <p className="error" role="alert">{error}</p>}
      <button className="secondary-button" onClick={signOut} disabled={signingOut || busy}>{signingOut ? 'Signing out…' : 'Sign out'}</button>
    </div>
  </details>
}
