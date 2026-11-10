import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from '../api'
import type { Agent, Ticket } from '../api'


export function AgentPage() {
  // These values only control the screen. FastAPI independently authorizes
  // every queue request using the session stored in PostgreSQL.
  const [agent, setAgent] = useState<Agent | null>(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const sessionExpired = useCallback(() => {
    setAgent(null)
    setError('Your session expired. Please sign in again.')
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    api<Agent>('/auth/me', { signal: controller.signal })
      .then((value) => { if (!controller.signal.aborted) setAgent(value) })
      .catch((failure) => {
        if (!controller.signal.aborted && !(failure instanceof ApiError && failure.status === 401)) setError(failure.message)
      })
      .finally(() => { if (!controller.signal.aborted) setChecking(false) })
    return () => controller.abort()
  }, [])

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const values = new FormData(form)
    setBusy(true)
    setError('')
    try {
      const signedIn = await api<Agent>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: values.get('email'), password: values.get('password') }),
      })
      form.reset()
      setAgent(signedIn)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  async function signOut() {
    setBusy(true)
    setError('')
    try {
      await api<void>('/auth/logout', { method: 'POST' })
      setAgent(null)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Sign-out failed. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (checking) return <section><p role="status">Checking agent session…</p></section>

  return <section>
    <p className="eyebrow">AGENT WORKSPACE</p>
    <h1>{agent ? 'Ticket queue' : 'Agent sign-in'}</h1>
    {error && <p className="error" role="alert">{error}</p>}

    {agent ? <>
      <div className="workspace-heading">
        <p>Signed in as {agent.name}</p>
        <button className="secondary-button" onClick={signOut} disabled={busy}>{busy ? 'Signing out…' : 'Sign out'}</button>
      </div>
      <TicketQueue onSessionExpired={sessionExpired} />
    </> : <form className="login-form" onSubmit={signIn}>
      <p>Sign in with your support agent account to view tickets.</p>
      <label htmlFor="agent-email">Email</label>
      <input id="agent-email" name="email" type="email" autoComplete="username" required maxLength={254} />

      <label htmlFor="agent-password">Password</label>
      <input id="agent-password" name="password" type="password" autoComplete="current-password" required maxLength={256} />

      <button className="button" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>}
  </section>
}


function TicketQueue({ onSessionExpired }: { onSessionExpired: () => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true

    // This is real API data, replacing the old frontend mock ticket table.
    api<Ticket[]>('/tickets')
      .then((rows) => { if (active) setTickets(rows) })
      .catch((failure) => {
        if (!active) return
        if (failure instanceof ApiError && failure.status === 401) onSessionExpired()
        else setError(failure.message)
      })
      .finally(() => { if (active) setLoading(false) })

    return () => { active = false }
  }, [reload, onSessionExpired])

  if (loading) return <p role="status">Loading tickets…</p>
  if (error) return <div role="alert"><p className="error">{error}</p><button className="secondary-button" onClick={() => {
    setLoading(true)
    setError('')
    setReload(reload + 1)
  }}>Try again</button></div>
  if (tickets.length === 0) return <p>No tickets yet. Create one through the API or run the demo seed.</p>

  return <>
    <div className="table-scroll">
      <table>
        <caption>Recent support tickets (up to 50)</caption>
        <thead><tr><th scope="col">Ticket</th><th scope="col">Subject</th><th scope="col">Category</th><th scope="col">Status</th><th scope="col">Priority</th></tr></thead>
        <tbody>{tickets.map((ticket) => <tr key={ticket.id}>
          <th scope="row">{ticket.number}</th><td>{ticket.subject}</td><td>{ticket.category.replaceAll('_', ' ')}</td>
          <td>{ticket.status.replaceAll('_', ' ')}</td><td>{ticket.priority}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="helper">Ticket conversations and editing controls will be added in the next steps.</p>
  </>
}
