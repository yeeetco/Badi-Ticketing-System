import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError, label } from '../api'
import type { Agent } from '../api'
import { StaffAccountMenu } from '../components/StaffAccountMenu'

export function AdminWorkspace({ agent, onProfileChange, signOut, busy, error, onSessionExpired }: {
  agent: Agent; onProfileChange: (value: Agent) => void; signOut: () => void;
  busy: boolean; error: string; onSessionExpired: () => void
}) {
  const [users, setUsers] = useState<Agent[]>([])
  const [editing, setEditing] = useState<Agent | 'new' | null>(null)
  const [failure, setFailure] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const load = useCallback(async () => {
    try { setUsers(await api<Agent[]>('/admin/users')) }
    catch (reason) {
      if (reason instanceof ApiError && [401, 403].includes(reason.status)) onSessionExpired()
      else setFailure(reason instanceof Error ? reason.message : 'Could not load staff accounts.')
    }
  }, [onSessionExpired])
  useEffect(() => {
    const controller = new AbortController()
    api<Agent[]>('/admin/users', { signal: controller.signal }).then((rows) => {
      if (!controller.signal.aborted) setUsers(rows)
    }).catch((reason) => {
      if (!controller.signal.aborted) {
        if (reason instanceof ApiError && [401, 403].includes(reason.status)) onSessionExpired()
        else setFailure(reason instanceof Error ? reason.message : 'Could not load accounts.')
      }
    })
    return () => controller.abort()
  }, [onSessionExpired])

  async function save(values: Record<string, unknown>) {
    setSaving(true); setFailure(''); setNotice('')
    try {
      const user = await api<Agent>(editing === 'new' ? '/admin/users' : `/admin/users/${editing && editing.id}`, {
        method: editing === 'new' ? 'POST' : 'PUT', body: JSON.stringify(values),
      })
      if (user.id === agent.id) {
        // Access-changing edits revoke the current session on the server too.
        const current = await api<Agent>('/auth/me')
        onProfileChange(current)
      }
      setEditing(null); setNotice('Staff account saved. Access changes require a fresh sign-in.')
      await load()
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) onSessionExpired()
      else setFailure(reason instanceof Error ? reason.message : 'Could not save account.')
    } finally { setSaving(false) }
  }

  async function remove(user: Agent) {
    setSaving(true); setFailure(''); setNotice('')
    try {
      await api(`/admin/users/${user.id}`, { method: 'DELETE' })
      setConfirmDelete(null); setEditing(null); setNotice('Staff account deleted. Conversation history is preserved.')
      await load()
    } catch (reason) { setFailure(reason instanceof Error ? reason.message : 'Could not delete account.') }
    finally { setSaving(false) }
  }

  return <section className="agent-section admin-workspace">
    <div className="workspace-topbar"><div><p className="eyebrow">BADI / ADMINISTRATION</p><h1>Staff accounts</h1><p>Manage profiles, roles, and access to the support workspace.</p></div><StaffAccountMenu agent={agent} onProfileChange={onProfileChange} signOut={signOut} signingOut={busy} /></div>
    {(failure || error) && <p className="error" role="alert">{failure || error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="admin-layout"><div className="admin-user-list"><div className="queue-heading"><h2>Users</h2><button className="button" onClick={() => { setEditing('new'); setFailure(''); setConfirmDelete(null) }} disabled={saving}>Add user</button></div>
      {users.map((user) => <article key={user.id} className="admin-user"><div><strong>{user.name}</strong><span>{user.email}</span><small>{user.role === 'ADMIN' ? 'Administrator' : label(user.role)} · {label(user.area)} · {user.is_active ? 'Active' : 'Disabled'}</small></div><div className="admin-user-actions"><button className="secondary-button" onClick={() => { setEditing(user); setConfirmDelete(null); setFailure('') }} disabled={saving}>Edit {user.name}</button>{user.id !== agent.id && <button className="filter-reset" onClick={() => setConfirmDelete(user.id)} disabled={saving}>Delete {user.name}</button>}</div>{confirmDelete === user.id && <div className="delete-confirmation"><p>Delete {user.name}’s login permanently? Their conversations and history will remain.</p><button className="emergency-button" onClick={() => void remove(user)} disabled={saving}>Confirm delete</button><button className="filter-reset" onClick={() => setConfirmDelete(null)} disabled={saving}>Cancel deletion</button></div>}</article>)}
    </div><div className="admin-editor">{editing ? <StaffEditor key={editing === 'new' ? 'new' : editing.id} user={editing === 'new' ? null : editing} busy={saving} onSave={save} onCancel={() => setEditing(null)} /> : <><h2>Access follows the role</h2><p>Agents handle assigned conversations. Team leaders monitor their area and can close cases in an emergency. Administrators manage staff access.</p><p>Customers use private ticket sessions; they are not staff accounts.</p></>}</div></div>
  </section>
}

function StaffEditor({ user, busy, onSave, onCancel }: {
  user: Agent | null; busy: boolean; onSave: (values: Record<string, unknown>) => Promise<void>; onCancel: () => void
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const values: Record<string, unknown> = Object.fromEntries(form)
    values.is_active = form.get('is_active') === 'on'
    values.max_active_chats = Number(form.get('max_active_chats'))
    if (!values.password && user) delete values.password
    await onSave(values)
  }
  return <form className="staff-editor" onSubmit={submit}><h2>{user ? 'Edit profile and access' : 'Create staff account'}</h2><fieldset disabled={busy}>
    <label>Full name<input name="name" defaultValue={user?.name} required maxLength={100} /></label>
    <label>Email address<input name="email" type="email" defaultValue={user?.email} required maxLength={254} /></label>
    <label>Role<select name="role" aria-label="Role" defaultValue={user?.role ?? 'AGENT'}><option value="AGENT">Agent</option><option value="TEAM_LEAD">Team leader</option><option value="ADMIN">Administrator</option></select></label>
    <label>Support area<input name="area" defaultValue={user?.area ?? 'BADI_SUPPORT'} pattern="[A-Z0-9_]+" required maxLength={80} /></label>
    <label>Support tier<select name="tier" defaultValue={user?.tier ?? 'T1'}><option value="T1">T1</option><option value="T2">T2</option></select></label>
    <label>Chat capacity<input name="max_active_chats" type="number" min={1} max={20} defaultValue={user?.max_active_chats ?? 5} required /></label>
    <label>{user ? 'New password (optional)' : 'Password'}<input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={256} required={!user} /></label>
    <label className="checkbox-label"><input name="is_active" type="checkbox" defaultChecked={user?.is_active ?? true} /> Account enabled</label>
    <p className="helper">Role, area, email, password, or access changes sign the user out and return active conversations for reassignment.</p>
    <button className="button">{busy ? 'Saving…' : 'Save user'}</button><button type="button" className="filter-reset" onClick={onCancel}>Cancel</button>
  </fieldset></form>
}
