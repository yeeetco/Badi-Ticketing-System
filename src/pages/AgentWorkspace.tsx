import { useCallback, useEffect, useRef, useState } from 'react'
import { api, categories, label, priorities, statuses, timestamp } from '../api'
import type { Agent, Ticket, TicketDetail } from '../api'
import { ChatThread } from '../components/ChatThread'
import type { ComposerDrafts } from '../components/ChatThread'
import { TicketForm } from '../components/TicketForm'
import { useLiveQuery } from '../hooks/useLiveQuery'
import { RoutingPanel } from '../components/RoutingPanel'

export function AgentWorkspace({ agent, signOut, busy, error, onSessionExpired }: {
  agent: Agent; signOut: () => void; busy: boolean; error: string; onSessionExpired: () => void
}) {
  const [selected, setSelected] = useState<number | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [directoryError, setDirectoryError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [created, setCreated] = useState<{ number: string; access_code: string } | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [category, setCategory] = useState('')
  const [assignee, setAssignee] = useState('')
  const [draftCache, setDraftCache] = useState<Record<string, ComposerDrafts>>({})
  const saveDraft = useCallback((endpoint: string, drafts: ComposerDrafts) => {
    setDraftCache((previous) => ({ ...previous, [endpoint]: drafts }))
  }, [])

  useEffect(() => {
    let active = true
    api<Agent[]>('/agents').then((value) => { if (active) setAgents(value) })
      .catch(() => { if (active) setDirectoryError('Could not load the agent directory. Reload to retry assignment controls.') })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 250)
    return () => clearTimeout(timer)
  }, [searchInput])

  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (priority) params.set('priority', priority)
  if (category) params.set('category', category)
  if (search) params.set('q', search)
  if (assignee === 'unassigned') params.set('unassigned', 'true')
  else if (assignee) params.set('assigned_agent_id', assignee)
  const queue = useLiveQuery<Ticket[]>(`/tickets?${params.toString()}`)

  return <section className="agent-section">
    <div className="workspace-topbar">
      <div><p className="eyebrow">BADI / AGENT WORKSPACE</p><h1>Support inbox<span className="inbox-count">{queue.data?.length ?? '—'}</span></h1><p>Every conversation. One place to help.</p></div>
      <div className="workspace-actions"><div className="agent-identity"><span className="avatar">{agent.name.slice(0, 1)}</span><span>{agent.name}<small>Support agent</small></span></div><button className="secondary-button" onClick={signOut} disabled={busy}>{busy ? 'Signing out…' : 'Sign out'}</button><button className="button" onClick={() => setShowCreate(true)}>＋ New ticket</button></div>
    </div>
    {(error || directoryError) && <p className="error" role="alert">{error || directoryError}</p>}
    <RoutingPanel agent={agent} />
    {created && <div className="access-card"><strong>{created.number} created</strong><p>Share this private access code securely with the customer so they can open the conversation:</p><code>{created.access_code}</code><button className="secondary-button" onClick={() => setCreated(null)}>Dismiss</button></div>}

    <div className="queue-toolbar">
      <label className="search-field"><span>Search tickets</span><input type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Ticket, subject, or customer…" maxLength={200} /></label>
      <label>Status<select aria-label="Status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
      <label>Priority<select aria-label="Priority" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="">All priorities</option>{priorities.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
      <label>Category<select aria-label="Category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
      <label>Assignee<select aria-label="Assignee" value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="">All agents</option><option value="unassigned">Unassigned</option>{agents.map((person) => <option key={person.id} value={person.id}>{person.id === agent.id ? 'Assigned to me' : person.name}</option>)}</select></label>
      <button className="filter-reset" onClick={() => { setSearchInput(''); setStatus(''); setPriority(''); setCategory(''); setAssignee('') }}>Reset</button>
    </div>

    <div className="agent-workspace">
      <aside className="ticket-queue" aria-label="Ticket queue">
        <div className="queue-heading"><strong>Conversations</strong><span className={`live-indicator ${queue.connection}`}>{queue.connection === 'live' ? 'Live' : 'Connecting'}</span></div>
        {queue.error && <p className="error" role="alert">{queue.error}{queue.connection === 'ended' && <button className="secondary-button" onClick={onSessionExpired}>Return to sign-in</button>}</p>}
        {!queue.data && !queue.error && <p className="queue-empty" role="status">Loading tickets…</p>}
        {queue.data?.length === 0 && <div className="queue-empty"><h2>No matching tickets</h2><p>Adjust your filters or create a new ticket.</p></div>}
        <div className="queue-list">{queue.data?.map((ticket) => <button key={ticket.id} className={`ticket-row ${selected === ticket.id ? 'selected' : ''}`} aria-pressed={selected === ticket.id} onClick={() => setSelected(ticket.id)}>
          <span className="ticket-row-top"><strong>{ticket.number}</strong><span className={`priority-dot priority-${ticket.priority.toLowerCase()}`}>{label(ticket.priority)}</span></span>
          <span className="ticket-subject">{ticket.subject}</span><span className="ticket-customer">{ticket.customer_email}</span>
          <span className="ticket-owner">{ticket.assigned_agent_id === agent.id ? 'Assigned to you' : ticket.assigned_agent_id ? `Assigned to ${agents.find((person) => person.id === ticket.assigned_agent_id)?.name ?? 'support agent'}` : 'In T1 waiting pool'}</span>
          <span className="ticket-row-bottom"><span className={`status-pill status-${ticket.status.toLowerCase()}`}>{label(ticket.status)}</span><time dateTime={ticket.updated_at}>{timestamp(ticket.updated_at)}</time></span>
        </button>)}</div>
        <p className="queue-footnote">Up to 100 most recently updated tickets</p>
      </aside>
      {selected ? <AgentConversation key={selected} ticketId={selected} agents={agents} agent={agent} draftCache={draftCache} onDraftChange={saveDraft} /> : <div className="conversation-empty"><span aria-hidden="true">☏</span><h2>Good support starts with a conversation.</h2><p>Select a ticket to read its history, reply to the customer, and manage the case.</p></div>}
    </div>
    {showCreate && <CreateTicketDialog onClose={() => setShowCreate(false)} onCreated={(ticket) => { setCreated(ticket); setSelected(ticket.id); setShowCreate(false) }} />}
  </section>
}

function AgentConversation({ ticketId, agents, agent, draftCache, onDraftChange }: {
  ticketId: number; agents: Agent[]; agent: Agent; draftCache: Record<string, ComposerDrafts>;
  onDraftChange: (endpoint: string, drafts: ComposerDrafts) => void
}) {
  const endpoint = `/tickets/${ticketId}`
  const live = useLiveQuery<TicketDetail>(endpoint)
  const [saved, setSaved] = useState<TicketDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // A PATCH response updates the controls immediately. Prefer a newer SSE
  // snapshot if another agent has made a subsequent change.
  const data = saved && (!live.data || new Date(saved.updated_at) > new Date(live.data.updated_at)) ? saved : live.data

  async function patch(changes: Record<string, string | number | null>) {
    setBusy(true)
    setError('')
    try { setSaved(await api<TicketDetail>(endpoint, { method: 'PATCH', body: JSON.stringify(changes) })) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not update ticket.') }
    finally { setBusy(false) }
  }

  if (!data || live.connection === 'ended') return <div className="conversation-empty"><p role={live.error ? 'alert' : 'status'}>{live.error || 'Loading conversation…'}</p></div>
  const assigneeName = (value: string | null) => value ? agents.find((person) => person.id === Number(value))?.name ?? `Agent ${value}` : 'Unassigned'

  return <>
    <div className="conversation-panel agent-chat">
      <div className="conversation-header"><div><div className="ticket-meta"><strong>{data.number}</strong><span className={`status-pill status-${data.status.toLowerCase()}`}>{label(data.status)}</span></div><h2>{data.subject}</h2><p>{data.customer_email}</p></div><span className={`live-indicator ${live.connection}`}>{live.connection === 'live' ? 'Live updates' : 'Reconnecting…'}</span></div>
      {live.error && <p className="error" role="alert">{live.error}</p>}
      <ChatThread messages={data.messages} endpoint={endpoint} agent viewerName={agent.name} initialDraft={draftCache[endpoint]} onDraftChange={onDraftChange} closed={data.status === 'CLOSED'} />
    </div>
    <aside className="ticket-details" aria-label="Ticket management">
      <div className="details-title"><h2>Case details</h2><span role="status">{busy ? 'Saving…' : 'Saved'}</span></div>
      {error && <p className="error" role="alert">{error}</p>}
      <fieldset disabled={busy} className="management-controls">
        <legend className="sr-only">Manage ticket</legend>
        <label>Status<select aria-label="Status" value={data.status} onChange={(event) => void patch({ status: event.target.value })}>{statuses.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label>Priority<select aria-label="Priority" value={data.priority} onChange={(event) => void patch({ priority: event.target.value })}>{priorities.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label>Assigned to<select aria-label="Assigned to" value={data.assigned_agent_id ?? ''} disabled={!agents.length} onChange={(event) => void patch({ assigned_agent_id: event.target.value ? Number(event.target.value) : null })}><option value="">Unassigned</option>{agents.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
        {data.assigned_agent_id !== agent.id && <button className="secondary-button" onClick={() => void patch({ assigned_agent_id: agent.id })}>Assign to me</button>}
      </fieldset>
      <dl className="case-metadata"><dt>Customer</dt><dd>{data.customer_email}</dd><dt>Category</dt><dd>{label(data.category)}</dd><dt>Order</dt><dd>{data.order_id || 'No order linked'}</dd><dt>Created</dt><dd>{timestamp(data.created_at)}</dd></dl>
      <details className="audit-history" open><summary>Activity history <span>{data.events.length}</span></summary><ol>{data.events.map((event) => <li key={event.id}><strong>{event.field === 'created' ? 'Ticket opened' : event.field === 'assigned_agent_id' ? `Assignment: ${assigneeName(event.old_value)} → ${assigneeName(event.new_value)}` : `${label(event.field)}: ${label(event.old_value ?? '')} → ${label(event.new_value ?? '')}`}</strong><span>{event.actor}</span><time dateTime={event.created_at}>{timestamp(event.created_at)}</time></li>)}</ol></details>
    </aside>
  </>
}

function CreateTicketDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (ticket: Ticket & { access_code: string }) => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal() }, [])
  return <dialog className="create-dialog" ref={dialog} onCancel={onClose}><h2>Open a ticket for a customer</h2><p>The description becomes the first public message.</p><TicketForm onCancel={onClose} onSubmit={async (data) => {
    const ticket = await api<Ticket & { access_code: string }>('/tickets', { method: 'POST', body: JSON.stringify(data) })
    onCreated(ticket)
  }} /></dialog>
}
