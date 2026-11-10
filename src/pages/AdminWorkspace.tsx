import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError, label } from '../api'
import type { Agent } from '../api'
import { StaffAccountMenu } from '../components/StaffAccountMenu'

export function AdminWorkspace({ agent, onProfileChange, signOut, busy, error, onSessionExpired }: {
  agent: Agent; onProfileChange: (value: Agent) => void; signOut: () => void;
  busy: boolean; error: string; onSessionExpired: () => void
}) {
  const [view, setView] = useState<'users' | 'roles'>('users')
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('')
  const [page, setPage] = useState(1)
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

  const filtered = users.filter((user) => (!role || user.role === role) && `${user.name} ${user.email} ${user.area}`.toLowerCase().includes(search.toLowerCase()))
  const pages = Math.max(1, Math.ceil(filtered.length / 10))
  const currentPage = Math.min(page, pages)
  const rows = filtered.slice((currentPage - 1) * 10, currentPage * 10)

  return <section className="admin-panel">
    <aside className="admin-sidebar"><a className="brand" href="#/admin">badi <span>Admin</span></a><p className="eyebrow">WORKSPACE</p><nav aria-label="Administration"><button aria-current={view === 'users' ? 'page' : undefined} onClick={() => setView('users')}>Users</button><button aria-current={view === 'roles' ? 'page' : undefined} onClick={() => setView('roles')}>Roles & permissions</button></nav><p className="admin-sidebar-note">Staff access management</p></aside>
    <div className="admin-content"><div className="admin-navbar"><span>Administration / {view === 'users' ? 'Users' : 'Roles'}</span><StaffAccountMenu agent={agent} onProfileChange={onProfileChange} signOut={signOut} signingOut={busy} /></div>
      <div className="admin-page-heading"><div><h1>{view === 'users' ? 'Staff accounts' : 'Roles & permissions'}</h1><p>{view === 'users' ? 'Manage your team’s profiles and access.' : 'Each staff role has a defined set of permissions.'}</p></div>{view === 'users' && <button className="button" onClick={() => { setEditing('new'); setFailure(''); setConfirmDelete(null) }} disabled={saving}>Add user</button>}</div>
      {!editing && (failure || error) && <p className="error" role="alert">{failure || error}</p>}{notice && <p role="status">{notice}</p>}
      {view === 'users' ? <>
        <div className="admin-metrics"><div><span>Total users</span><strong>{users.length}</strong></div><div><span>Active accounts</span><strong>{users.filter((user) => user.is_active).length}</strong></div><div><span>Administrators</span><strong>{users.filter((user) => user.role === 'ADMIN').length}</strong></div></div>
        <div className="admin-directory"><div className="admin-table-toolbar"><label>Search staff<input type="search" placeholder="Name, email, or area" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} /></label><label>Filter by role<select value={role} onChange={(event) => { setRole(event.target.value); setPage(1) }}><option value="">All roles</option><option value="AGENT">Agent</option><option value="TEAM_LEAD">Team leader</option><option value="ADMIN">Administrator</option></select></label><span>{filtered.length} users</span></div>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Staff directory"><table className="admin-users-table"><caption className="sr-only">Staff accounts and access</caption><thead><tr><th scope="col">Name</th><th scope="col">Email</th><th scope="col">Role</th><th scope="col">Area</th><th scope="col">Access</th><th scope="col">Actions</th></tr></thead><tbody>{rows.map((user) => <tr key={user.id} className="admin-user"><td><strong>{user.name}</strong></td><td>{user.email}</td><td><span className="role-badge">{roleName(user.role)}</span></td><td>{label(user.area)}</td><td><span className={`status-pill ${user.is_active ? 'status-open' : 'status-closed'}`}>{user.is_active ? 'Active' : 'Disabled'}</span></td><td><div className="admin-user-actions"><button className="filter-reset" onClick={() => { setEditing(user); setConfirmDelete(null); setFailure('') }} disabled={saving}>Edit {user.name}</button>{user.id !== agent.id && <button className="filter-reset delete-user" onClick={() => setConfirmDelete(user.id)} disabled={saving}>Delete {user.name}</button>}</div>{confirmDelete === user.id && <div className="delete-confirmation"><p>Delete {user.name}’s login? Conversations and history will remain.</p><button className="emergency-button" onClick={() => void remove(user)} disabled={saving}>Confirm delete</button><button className="filter-reset" onClick={() => setConfirmDelete(null)} disabled={saving}>Cancel deletion</button></div>}</td></tr>)}</tbody></table>{rows.length === 0 && <p className="queue-empty" role="status">No staff match your search.</p>}</div>
          <div className="admin-pagination"><span>Page {currentPage} of {pages}</span><div><button className="secondary-button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous</button><button className="secondary-button" disabled={currentPage === pages} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
        </div>
      </> : <div className="admin-directory"><div className="table-scroll" tabIndex={0} role="region" aria-label="Role permissions"><table><caption>Roles are assigned from a staff member’s profile.</caption><thead><tr><th scope="col">Role</th><th scope="col">Conversations</th><th scope="col">User management</th></tr></thead><tbody><tr><th scope="row">Agent</th><td>Reply, add notes, change workflow and transfer assigned cases.</td><td>No</td></tr><tr><th scope="row">Team leader</th><td>Monitor area cases and perform emergency closure.</td><td>No</td></tr><tr><th scope="row">Administrator</th><td>No conversation access.</td><td>Create, edit, disable, delete and assign staff roles.</td></tr></tbody></table></div></div>}
    </div>
    {editing && <StaffEditorDialog error={failure || error} user={editing === 'new' ? null : editing} busy={saving} onSave={save} onCancel={() => setEditing(null)} />}
  </section>
}

function roleName(role: Agent['role']) {
  return role === 'ADMIN' ? 'Administrator' : role === 'TEAM_LEAD' ? 'Team leader' : 'Agent'
}

function StaffEditorDialog({ error, ...props }: Parameters<typeof StaffEditor>[0] & { error: string }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { const modal = dialog.current; modal?.showModal(); return () => modal?.close() }, [])
  return <dialog className="staff-editor-dialog" ref={dialog} onCancel={(event) => { event.preventDefault(); if (!props.busy) props.onCancel() }} aria-label={props.user ? 'Edit staff account' : 'Add staff account'}>{error && <p className="error" role="alert">{error}</p>}<StaffEditor {...props} /></dialog>
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
