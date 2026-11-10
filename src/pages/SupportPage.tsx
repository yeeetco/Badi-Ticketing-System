import { useEffect, useState } from 'react'
import { api, ApiError, label } from '../api'
import type { CreatedTicket, CustomerTicket } from '../api'
import { ChatThread } from '../components/ChatThread'
import { CustomerBot } from '../components/CustomerBot'
import { useLiveQuery } from '../hooks/useLiveQuery'

export function SupportPage() {
  const [ticket, setTicket] = useState<CustomerTicket | null>(null)
  const [checking, setChecking] = useState(true)
  const [accessCode, setAccessCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [restored, setRestored] = useState(false)

  useEffect(() => {
    let active = true
    // The browser sends the HttpOnly ticket cookie. React never reads or copies
    // the token into URLs/localStorage. A valid session restores the case.
    api<CustomerTicket>('/customer/session').then((value) => {
      if (active) { setTicket(value); setRestored(true) }
    }).catch((failure) => {
      if (active && !(failure instanceof ApiError && [401, 404].includes(failure.status))) setError(failure.message)
    }).finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [])

  async function create(data: Record<string, string | null>) {
    const result = await api<CreatedTicket>('/customer/tickets', { method: 'POST', body: JSON.stringify(data) })
    setAccessCode(result.access_code)
    setError('')
    setRestored(false)
    setTicket(result.ticket)
  }

  async function endChat() {
    if (!ticket) return
    setBusy(true)
    setError('')
    try {
      setTicket(await api<CustomerTicket>(`/customer/tickets/${ticket.id}/end`, { method: 'POST' }))
      setRestored(false)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not end the chat. Please try again.') }
    finally { setBusy(false) }
  }

  async function startOver() {
    setBusy(true)
    setError('')
    try {
      await api('/customer/logout', { method: 'POST' })
      setTicket(null)
      setAccessCode('')
      setRestored(false)
    } catch { setError('Could not start over. Your saved history is still here; please try again.') }
    finally { setBusy(false) }
  }

  return <section className="badi-help-page">
    <div className="support-hero compact-support-hero"><span className="eyebrow">BADI HELP & CARE</span><h1>A little help. Wherever you are.</h1><p>Tell us what’s happening. We’ll help you get connected.</p></div>
    <div className="support-page-grid support-chat-only"><div className="support-chat-column" id="support-chat">

      {error && <p className="error" role="alert">{error}</p>}
      {checking ? <div className="form-panel"><p role="status">Welcome to Badi. Let me check for a saved conversation…</p></div> : ticket ? <>
        {restored && <p className="restored-session" role="status">Welcome back. We’ve brought your saved conversation with us.</p>}
        {accessCode && <details className="access-card compact-access"><summary>Keep your private access code · {ticket.number}</summary><p>Your browser remembers this conversation. Save this code to find it on another device—we want it to be easy to pick up where you left off.</p><code>{accessCode}</code><button className="secondary-button" onClick={() => {
          const blob = new Blob([`Badi ticket: ${ticket.number}\nPrivate access code: ${accessCode}\nKeep this code private.\n`], { type: 'text/plain' })
          const url = URL.createObjectURL(blob)
          const link = document.createElement('a'); link.href = url; link.download = `${ticket.number}-access.txt`; link.click()
          setTimeout(() => URL.revokeObjectURL(url), 1000)
        }}>Save access details</button></details>}
        <CustomerConversation key={ticket.id} ticket={ticket} onEnd={endChat} onStartOver={startOver} busy={busy} />

      </> : <CustomerBot onCreate={create} onResume={(value) => { setTicket(value); setRestored(true) }} />}
    </div></div>
    <div className="support-contact"><strong>However your trip unfolds, we’re with you.</strong><span>Prefer email? <a href="mailto:support@badiesim.com">support@badiesim.com</a></span></div>
  </section>
}

function CustomerConversation({ ticket: initial, onEnd, onStartOver, busy }: {
  ticket: CustomerTicket; onEnd: () => void; onStartOver: () => void; busy: boolean
}) {
  const endpoint = `/customer/tickets/${initial.id}`
  const live = useLiveQuery<CustomerTicket>(endpoint)
  // The end response is authoritative immediately, before its SSE snapshot.
  const data = initial.customer_ended_at && !live.data?.customer_ended_at ? initial : live.data ?? initial
  const error = live.error
  const ended = !!data.customer_ended_at
  const complete = ['CLOSED', 'RESOLVED'].includes(data.status)
  return <div className={`customer-chat conversation-panel case-${data.status.toLowerCase()}`}>
    <div className="conversation-header"><div><div className="ticket-meta"><strong>{data.number}</strong>{ended && <span className="status-pill status-closed">Disconnected</span>}</div><h2>{ended ? 'Chat closed' : data.routing_state === 'ASSIGNED' ? `Chat with ${data.assigned_agent_name}` : complete ? 'Your saved conversation' : 'Chat with an Agent'}</h2><p>{data.subject}</p></div>{!ended && <button className="secondary-button" onClick={onEnd} disabled={busy}>{busy ? 'Ending…' : 'End Chat'}</button>}</div>
    {!ended && <div className={`routing-banner routing-${data.routing_state.toLowerCase()}`} role="status"><strong>{data.routing_state === 'WAITING' ? `You’re in the queue · Position ${data.queue_position ?? '—'}` : data.routing_state === 'ASSIGNED' ? `Your case is with ${data.assigned_agent_name}` : `Conversation ${label(data.status).toLowerCase()}`}</strong><span>{data.routing_state === 'WAITING' ? 'Thank you for your patience. Your place and messages are saved; we’ll connect you as soon as an agent has room to help.' : complete ? 'Thank you for reaching out. Your history is safe here. If you still need help, you can start another chat.' : 'You’re in good hands. If your agent becomes unavailable, we’ll keep your case safe and find the next available teammate.'}</span></div>}
    {error && <p className="error" role="alert">{error}</p>}
    <ChatThread typingName={data.agent_is_typing ? data.assigned_agent_name ?? 'Agent' : undefined} messages={data.messages} endpoint={endpoint} caseStatus={data.status} readOnly={complete || ended} readOnlyReason={ended ? 'You have disconnected. This chat is closed and its history is saved.' : 'This conversation is complete. Its history is saved.'} readOnlyAction={<button className="button" onClick={onStartOver} disabled={busy}>{busy ? 'Resetting…' : 'Start Over'}</button>} intro={<details className="generated-ticket-summary"><summary>Your ticket details · {data.number}</summary><dl><dt>Customer</dt><dd>{data.customer_email}</dd><dt>Order ID</dt><dd>{data.order_id || 'Not provided'}</dd><dt>Category</dt><dd>{label(data.category)}</dd><dt>Subject</dt><dd>{data.subject}</dd><dt>Status</dt><dd>{label(data.status)}</dd><dt>Priority</dt><dd>{label(data.priority)}</dd></dl></details>} />
  </div>
}
