import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from '../api'
import type { Agent } from '../api'
import { AdminWorkspace } from './AdminWorkspace'
import { AgentWorkspace } from './AgentWorkspace'


export function AgentPage() {
  // These values only control the screen. FastAPI independently authorizes
  // every queue request using the session stored in PostgreSQL.
  const [agent, setAgent] = useState<Agent | null>(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const staffId = agent?.id

  useEffect(() => {
    if (!staffId) return
    let active = true
    const pulse = () => api<Agent>('/auth/heartbeat', { method: 'POST' })
      .then((profile) => { if (active) setAgent(profile) })
      .catch((failure) => {
        if (active && failure instanceof ApiError && failure.status === 401) {
          setAgent(null)
          setError('Your session ended. Please sign in again.')
        }
      })
    void pulse()
    const timer = setInterval(() => void pulse(), 20000)
    return () => { active = false; clearInterval(timer) }
  }, [staffId])

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

  if (agent?.role === 'ADMIN') return <AdminWorkspace agent={agent} onProfileChange={setAgent} signOut={signOut} busy={busy} error={error} onSessionExpired={sessionExpired} />

  if (agent) return <AgentWorkspace agent={agent} onProfileChange={setAgent} signOut={signOut} busy={busy} error={error} onSessionExpired={sessionExpired} />

  return <section>
    <div className="staff-signin-brand"><span className="support-avatar">b</span><span>Badi support workspace</span></div>
    <p className="eyebrow">STAFF ACCESS</p>
    <h1>Staff sign-in</h1>
    {error && <p className="error" role="alert">{error}</p>}

    <form className="login-form" onSubmit={signIn}>
      <p>Sign in to your staff workspace.</p>
      <label htmlFor="agent-email">Email</label>
      <input id="agent-email" name="email" type="email" autoComplete="username" required maxLength={254} />

      <label htmlFor="agent-password">Password</label>
      <input id="agent-password" name="password" type="password" autoComplete="current-password" required maxLength={256} />

      <button className="button" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
  </section>
}
