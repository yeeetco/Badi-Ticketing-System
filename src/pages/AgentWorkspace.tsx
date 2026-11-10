import { useCallback, useEffect, useState } from 'react'
import { api, categories, label, priorities, statuses, timestamp } from '../api'
import type { Agent, Ticket, TicketDetail } from '../api'
import { ChatThread } from '../components/ChatThread'
import type { ComposerDrafts } from '../components/ChatThread'
import { useLiveQuery } from '../hooks/useLiveQuery'
import { StaffAccountMenu } from '../components/StaffAccountMenu'

export function AgentWorkspace({ agent, onProfileChange, signOut, busy, error, onSessionExpired }: {
  agent: Agent; onProfileChange: (agent: Agent) => void; signOut: () => void; busy: boolean; error: string; onSessionExpired: () => void
}) {
  const [selected, setSelected] = useState<number | null>(null)
  const directory = useLiveQuery<Agent[]>('/agents')
  const agents = directory.data ?? []
  const directoryError = directory.error
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [category, setCategory] = useState('')
  const [assignee, setAssignee] = useState(agent.role === 'TEAM_LEAD' ? '' : String(agent.id))
  const supervisor = agent.role === 'TEAM_LEAD'
  const [draftCache, setDraftCache] = useState<Record<string, ComposerDrafts>>({})
  const saveDraft = useCallback((endpoint: string, drafts: ComposerDrafts) => {
    setDraftCache((previous) => ({ ...previous, [endpoint]: drafts }))
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
      <div><p className="eyebrow">BADI / {supervisor ? 'TEAM LEADER' : 'AGENT WORKSPACE'}</p><h1>{supervisor ? 'Team overview' : 'Support inbox'}<span className="inbox-count">{queue.data?.length ?? '—'}</span></h1><p>{supervisor ? `Monitor conversations in ${label(agent.area)}. Emergency closure is audited.` : 'Conversations are assigned automatically when you are available.'}</p></div>
      <div className="workspace-actions"><StaffAccountMenu agent={agent} onProfileChange={onProfileChange} signOut={signOut} signingOut={busy} /></div>
    </div>
    {(error || directoryError) && <p className="error" role="alert">{error || directoryError}</p>}




    <div className="queue-toolbar">
      <label className="search-field"><span>Search tickets</span><input type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Ticket, subject, or customer…" maxLength={200} /></label>
      <label>Status<select aria-label="Status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option>{statuses.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
      <label>Priority<select aria-label="Priority" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="">All priorities</option>{priorities.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
      <label>Category<select aria-label="Category" value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{categories.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
      {supervisor && <label>Assignee<select aria-label="Assignee" value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="">All agents</option>{agents.map((person) => <option key={person.id} value={person.id}>{person.id === agent.id ? 'Assigned to me' : person.name}</option>)}</select></label>}
      <button className="filter-reset" onClick={() => { setSearchInput(''); setStatus(''); setPriority(''); setCategory(''); setAssignee(supervisor ? '' : String(agent.id)) }}>Reset</button>
    </div>

    <div className="agent-workspace">
      <aside className="ticket-queue" aria-label="Ticket queue">
        <div className="queue-heading"><strong>Conversations</strong><span className={`live-indicator ${queue.connection}`}>{queue.connection === 'live' ? 'Live' : 'Connecting'}</span></div>
        {queue.error && <p className="error" role="alert">{queue.error}{queue.connection === 'ended' && <button className="secondary-button" onClick={onSessionExpired}>Return to sign-in</button>}</p>}
        {!queue.data && !queue.error && <p className="queue-empty" role="status">Loading tickets…</p>}
        {queue.data?.length === 0 && <div className="queue-empty"><h2>No matching tickets</h2><p>New customer conversations appear here when assigned to you.</p></div>}
        <div className="queue-list">{queue.data?.map((ticket) => <button key={ticket.id} className={`ticket-row case-${ticket.status.toLowerCase()} ${selected === ticket.id ? 'selected' : ''}`} aria-pressed={selected === ticket.id} onClick={() => setSelected(ticket.id)}>
          <span className="ticket-row-top"><strong>{ticket.number}</strong><span className={`priority-dot priority-${ticket.priority.toLowerCase()}`}>{label(ticket.priority)}</span></span>
          <span className="ticket-subject">{ticket.subject}</span><span className="ticket-customer">{ticket.customer_email}</span>
          <span className="ticket-owner">{ticket.assigned_agent_id === agent.id ? 'Assigned to you' : ticket.assigned_agent_id ? `Assigned to ${agents.find((person) => person.id === ticket.assigned_agent_id)?.name ?? 'support agent'}` : 'Awaiting assignment'}</span>
          <span className="ticket-row-bottom"><span className={`status-pill status-${ticket.status.toLowerCase()}`}>{label(ticket.status)}</span><time dateTime={ticket.updated_at}>{timestamp(ticket.updated_at)}</time></span>
        </button>)}</div>
        <p className="queue-footnote">Up to 100 most recently updated tickets</p>
      </aside>
      {selected ? <AgentConversation key={selected} ticketId={selected} agents={agents} agent={agent} draftCache={draftCache} onDraftChange={saveDraft} /> : <div className="conversation-empty"><span aria-hidden="true">☏</span><h2>Good support starts with a conversation.</h2><p>Select a ticket to read its history, reply to the customer, and manage the case.</p></div>}
    </div>

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
  const [transferId, setTransferId] = useState('')
  const [showTransfer, setShowTransfer] = useState(false)
  const [notice, setNotice] = useState('')
  const [emergency, setEmergency] = useState(false)
  const [reason, setReason] = useState('')

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

  // These actions are validated and committed in FastAPI, under the queue lock.
  async function route(action: string, body: Record<string, number>) {
    setBusy(true)
    setError('')
    try {
      setSaved(await api<TicketDetail>(`${endpoint}/${action}`, { method: 'POST', body: JSON.stringify(body) }))
      setNotice(action === 'transfer' ? 'Conversation transferred.' : 'Conversation returned. Automatic reassignment to you is paused for five minutes.')
      setTransferId('')
      setShowTransfer(false)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not route conversation.') }
    finally { setBusy(false) }
  }

  async function closeEmergency(event: import('react').FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      setSaved(await api<TicketDetail>(`${endpoint}/emergency-close`, { method: 'POST', body: JSON.stringify({ reason }) }))
      setEmergency(false)
      setReason('')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Emergency closure failed.') }
    finally { setBusy(false) }
  }

  if (!data || live.connection === 'ended') return <div className="conversation-empty"><p role={live.error ? 'alert' : 'status'}>{live.error || 'Loading conversation…'}</p></div>
  const assigneeName = (value: string | null) => value ? agents.find((person) => person.id === Number(value))?.name ?? `Agent ${value}` : 'Unassigned'
  const supervisor = agent.role === 'TEAM_LEAD'
  const handling = data.assigned_agent_id === agent.id
  const readOnly = supervisor || !handling || data.emergency_closed

  return <>
    <div className="conversation-panel agent-chat">
      <div className="conversation-header"><div><div className="ticket-meta"><strong>{data.number}</strong><span className={`status-pill status-${data.status.toLowerCase()}`}>{label(data.status)}</span></div><h2>{data.subject}</h2><p>{data.customer_email}</p></div><span className={`live-indicator ${live.connection}`}>{live.connection === 'live' ? 'Live updates' : 'Reconnecting…'}</span></div>
      {live.error && <p className="error" role="alert">{live.error}</p>}
      <ChatThread messages={data.messages} endpoint={endpoint} agent viewerName={supervisor ? undefined : agent.name} initialDraft={draftCache[endpoint]} onDraftChange={onDraftChange} caseStatus={data.status} closed={data.status === 'CLOSED'} readOnly={readOnly} readOnlyReason={supervisor ? 'Monitoring only. Team leaders cannot send replies or internal notes.' : data.emergency_closed ? 'Emergency-closed conversation. History is preserved and read-only.' : 'This case is in the pool or parked with another agent. Replying is reserved for its handler.'} />
    </div>
    <aside className="ticket-details" aria-label="Ticket management">
      <div className="details-title"><h2>Case details</h2><span role="status">{busy ? 'Saving…' : 'Saved'}</span></div>
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!supervisor && <fieldset disabled={busy || (!handling && data.assigned_agent_id !== null)} className="management-controls">
        <legend className="sr-only">Manage ticket</legend>
        <label>Status<select aria-label="Status" disabled={!handling || data.emergency_closed} value={data.status} onChange={(event) => void patch({ status: event.target.value })}>{statuses.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        <label>Priority<select aria-label="Priority" disabled={!handling} value={data.priority} onChange={(event) => void patch({ priority: event.target.value })}>{priorities.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
        {handling && !['CLOSED', 'RESOLVED'].includes(data.status) && <>
          {!showTransfer && <button className="secondary-button" onClick={() => setShowTransfer(true)}>Transfer conversation</button>}
          {showTransfer && <><label>Transfer to<select aria-label="Transfer to" value={transferId} onChange={(event) => setTransferId(event.target.value)}><option value="">Choose another agent</option>{agents.filter((person) => person.id !== agent.id).map((person) => <option key={person.id} value={person.id} disabled={person.availability !== 'ONLINE'}>{person.name} · {label(person.availability)}</option>)}</select></label>
          {agents.filter((person) => person.id !== agent.id).length === 0 && <p className="helper">No other agent accounts are available for transfer.</p>}
          <button className="secondary-button" disabled={!transferId} onClick={() => void route('transfer', { agent_id: Number(transferId) })}>Confirm transfer</button><button className="filter-reset" onClick={() => { setShowTransfer(false); setTransferId('') }}>Cancel transfer</button></>}
          <button className="secondary-button" onClick={() => void route('return-to-queue', {})}>Return to queue</button>
          <p className="helper">You won’t receive this conversation again for five minutes. Another available agent can receive it immediately.</p>
        </>}
      </fieldset>}
      {supervisor && <div className="emergency-controls"><p>You can monitor this area's cases. Closing a case requires an emergency reason.</p>{data.status !== 'CLOSED' && !emergency && <button className="emergency-button" onClick={() => setEmergency(true)}>Emergency close</button>}{emergency && <form onSubmit={closeEmergency}><label>Emergency reason<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={10} maxLength={1000} required rows={4} /></label><p>This closes the case, preserves its history, and records your reason. Agents cannot reopen an emergency closure.</p><button className="emergency-button" disabled={busy}>{busy ? 'Closing…' : 'Confirm emergency closure'}</button><button type="button" className="filter-reset" disabled={busy} onClick={() => setEmergency(false)}>Cancel</button></form>}</div>}
      <dl className="case-metadata"><dt>Customer</dt><dd>{data.customer_email}</dd><dt>Category</dt><dd>{label(data.category)}</dd><dt>Order</dt><dd>{data.order_id || 'No order linked'}</dd><dt>Created</dt><dd>{timestamp(data.created_at)}</dd></dl>
      <details className="audit-history" open><summary>Activity history <span>{data.events.length}</span></summary><ol>{data.events.map((event) => <li key={event.id}><strong>{event.field === 'created' ? 'Ticket opened' : event.field === 'assigned_agent_id' ? `Assignment: ${assigneeName(event.old_value)} → ${assigneeName(event.new_value)}` : `${label(event.field)}: ${label(event.old_value ?? '')} → ${label(event.new_value ?? '')}`}</strong><span>{event.actor}</span>{event.reason && <p className="audit-reason">{event.reason}</p>}<time dateTime={event.created_at}>{timestamp(event.created_at)}</time></li>)}</ol></details>
    </aside>
  </>
}
