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
  const [ended, setEnded] = useState(false)

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
    setEnded(false)
    setAccessCode(result.access_code)
    setError('')
    setRestored(false)
    setTicket(result.ticket)
  }

  async function leave() {
    setBusy(true)
    setError('')
    try {
      await api('/customer/logout', { method: 'POST' })
      setTicket(null)
      setAccessCode('')
      setRestored(false)
      setEnded(true)
    } catch { setError('We couldn’t end this chat just yet. Your current conversation is still saved—please try again.') }
    finally { setBusy(false) }
  }

  return <section className="badi-help-page">
    <div className="support-hero"><span className="eyebrow">BADI HELP & CARE</span><h1>Your journey.<br /><em>We’re here for it.</em></h1><p>From your first connection to the next destination, a little help is always close. Find an answer or tell us what’s happening—we’ll take it from here.</p><div className="support-promise"><span>✓ Saved conversations</span><span>✓ A real support team</span><span>✓ Help at your pace</span></div></div>
    <div className="support-page-grid support-chat-only"><div className="support-chat-column" id="support-chat">
      {ended && <p className="restored-session" role="status">Thank you for chatting with Badi. Your conversation is saved; use your private code to return. Your agent will continue to manage the case.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {checking ? <div className="form-panel"><p role="status">Welcome to Badi. Let me check for a saved conversation…</p></div> : ticket ? <>
        {restored && <p className="restored-session" role="status">Welcome back. We’ve brought your saved conversation with us.</p>}
        {accessCode && <details className="access-card compact-access"><summary>Keep your private access code · {ticket.number}</summary><p>Your browser remembers this conversation. Save this code to find it on another device—we want it to be easy to pick up where you left off.</p><code>{accessCode}</code><button className="secondary-button" onClick={() => {
          const blob = new Blob([`Badi ticket: ${ticket.number}\nPrivate access code: ${accessCode}\nKeep this code private.\n`], { type: 'text/plain' })
          const url = URL.createObjectURL(blob)
          const link = document.createElement('a'); link.href = url; link.download = `${ticket.number}-access.txt`; link.click()
          setTimeout(() => URL.revokeObjectURL(url), 1000)
        }}>Save access details</button></details>}
        <CustomerConversation key={ticket.id} ticketId={ticket.id} onEnd={leave} ending={busy} />

      </> : <CustomerBot onCreate={create} onResume={(value) => { setTicket(value); setRestored(true); setEnded(false) }} />}
    </div></div>
    <div className="support-contact"><strong>However your trip unfolds, we’re with you.</strong><span>Prefer email? <a href="mailto:support@badiesim.com">support@badiesim.com</a></span></div>
  </section>
}

function CustomerConversation({ ticketId, onEnd, ending }: { ticketId: number; onEnd: () => void; ending: boolean }) {
  const endpoint = `/customer/tickets/${ticketId}`
  const { data, error } = useLiveQuery<CustomerTicket>(endpoint)
  if (!data) return <div className="form-panel"><p role={error ? 'alert' : 'status'}>{error || 'Let’s bring your conversation back…'}</p></div>
  const complete = ['CLOSED', 'RESOLVED'].includes(data.status)
  return <div className={`customer-chat conversation-panel case-${data.status.toLowerCase()}`}>
    <div className="conversation-header"><div><div className="ticket-meta"><strong>{data.number}</strong></div><h2>{data.routing_state === 'ASSIGNED' ? `Chat with ${data.assigned_agent_name}` : complete ? 'Your saved conversation' : 'Chat with an Agent'}</h2><p>{data.subject}</p></div><button className="secondary-button" onClick={onEnd} disabled={ending}>{ending ? 'Ending…' : 'End Chat'}</button></div>
    <div className={`routing-banner routing-${data.routing_state.toLowerCase()}`} role="status"><strong>{data.routing_state === 'WAITING' ? `You’re in the queue · Position ${data.queue_position ?? '—'}` : data.routing_state === 'ASSIGNED' ? `Your case is with ${data.assigned_agent_name}` : `Conversation ${label(data.status).toLowerCase()}`}</strong><span>{data.routing_state === 'WAITING' ? 'Thank you for your patience. Your place and messages are saved; we’ll connect you as soon as an agent has room to help.' : complete ? 'Thank you for reaching out. Your history is safe here. If you still need help, you can start another chat.' : 'You’re in good hands. If your agent becomes unavailable, we’ll keep your case safe and find the next available teammate.'}</span></div>
    {error && <p className="error" role="alert">{error}</p>}
    <ChatThread messages={data.messages} endpoint={endpoint} caseStatus={data.status} readOnly={complete} readOnlyReason="This conversation is complete. Its history is saved; start another chat if you still need a hand." intro={<details className="generated-ticket-summary"><summary>Your ticket details · {data.number}</summary><dl><dt>Customer</dt><dd>{data.customer_email}</dd><dt>Order ID</dt><dd>{data.order_id || 'Not provided'}</dd><dt>Category</dt><dd>{label(data.category)}</dd><dt>Subject</dt><dd>{data.subject}</dd><dt>Status</dt><dd>{label(data.status)}</dd><dt>Priority</dt><dd>{label(data.priority)}</dd></dl></details>} />
  </div>
}
