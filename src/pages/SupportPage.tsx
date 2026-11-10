import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError, label } from '../api'
import type { CreatedTicket, CustomerTicket } from '../api'
import { ChatThread } from '../components/ChatThread'
import { GuidedIntake } from '../components/GuidedIntake'
import { useLiveQuery } from '../hooks/useLiveQuery'

export function SupportPage() {
  const [ticket, setTicket] = useState<CustomerTicket | null>(null)
  const [checking, setChecking] = useState(true)
  const [mode, setMode] = useState<'home' | 'create' | 'return'>('home')
  const [accessCode, setAccessCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    api<CustomerTicket>('/customer/session').then((value) => { if (active) setTicket(value) })
      .catch((failure) => { if (active && !(failure instanceof ApiError && [401, 404].includes(failure.status))) setError(failure.message) })
      .finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [])

  async function create(data: Record<string, string | null>) {
    const result = await api<CreatedTicket>('/customer/tickets', { method: 'POST', body: JSON.stringify(data) })
    setAccessCode(result.access_code)
    setError('')
    setTicket(result.ticket)
  }

  async function reopen(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = Object.fromEntries(new FormData(event.currentTarget))
    setBusy(true)
    setError('')
    try {
      const result = await api<CustomerTicket>('/customer/access', { method: 'POST', body: JSON.stringify(data) })
      setTicket(result)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not open ticket.') }
    finally { setBusy(false) }
  }

  async function leave() {
    setBusy(true)
    setError('')
    try {
      await api('/customer/logout', { method: 'POST' })
      setTicket(null)
      setAccessCode('')
      setMode('home')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not close ticket.') }
    finally { setBusy(false) }
  }

  if (checking) return <section><p role="status">Checking your support session…</p></section>

  return <section className={`customer-support ${ticket || mode === 'create' ? 'chat-open' : ''}`}>
    {!ticket && mode !== 'create' && <p className="eyebrow">BADI CUSTOMER CARE</p>}
    <h1 className={ticket || mode === 'create' ? 'sr-only' : undefined}>{ticket ? 'Your support conversation' : 'A little help goes a long way.'}</h1>
    {error && <p className="error" role="alert">{error}</p>}
    {ticket ? <>
      {accessCode && <div className="access-card" role="status">
        <strong>Save your private access code</strong>
        <p>Use {ticket.number} and this code to return on another browser. It unlocks your conversation, so keep it private. It is shown only when the ticket is created.</p>
        <code>{accessCode}</code>
        <button className="secondary-button" onClick={() => {
          const blob = new Blob([`Badi support ticket: ${ticket.number}\nPrivate access code: ${accessCode}\nKeep this code private.\n`], { type: 'text/plain' })
          const url = URL.createObjectURL(blob)
          const link = document.createElement('a'); link.href = url; link.download = `${ticket.number}-access.txt`; link.click()
          setTimeout(() => URL.revokeObjectURL(url), 1000)
        }}>Save access details</button>
      </div>}
      <CustomerConversation key={ticket.id} ticketId={ticket.id} />
      <button className="secondary-button leave-ticket" onClick={leave} disabled={busy}>{busy ? 'Leaving…' : 'Leave this ticket / open another'}</button>
      <p className="helper">Leaving signs this browser out of the ticket. Keep your access code to return.</p>
    </> : mode === 'create' ? <GuidedIntake onSubmit={create} onCancel={() => setMode('home')} />
      : mode === 'return' ? <form className="login-form form-panel" onSubmit={reopen}>
        <h2>Return to your ticket</h2>
        <label htmlFor="ticket-number">Ticket number</label><input id="ticket-number" name="ticket_number" placeholder="BD-1004" pattern="BD-[0-9]+" maxLength={30} required />
        <label htmlFor="access-code">Private access code</label><input id="access-code" name="access_code" type="password" autoComplete="off" minLength={20} maxLength={100} required />
        <div className="form-actions"><button className="secondary-button" type="button" onClick={() => setMode('home')}>Back</button><button className="button" disabled={busy}>{busy ? 'Opening…' : 'Open conversation'}</button></div>
      </form> : <>
        <p>Start a request or pick up where you left off. Your conversation stays here even when an agent is offline.</p>
        <div className="support-options">
          <button className="support-option" onClick={() => { setMode('create'); setError('') }}><span aria-hidden="true">＋</span><strong>Start a chat</strong><span>Answer a few quick questions. We’ll prepare your ticket and find a support agent.</span><b>Let’s talk →</b></button>
          <button className="support-option" onClick={() => { setMode('return'); setError('') }}><span aria-hidden="true">↩</span><strong>Return to a ticket</strong><span>Use your ticket number and private access code.</span><b>Continue conversation →</b></button>
        </div>
      </>}
  </section>
}

function CustomerConversation({ ticketId }: { ticketId: number }) {
  const endpoint = `/customer/tickets/${ticketId}`
  const { data, error, connection } = useLiveQuery<CustomerTicket>(endpoint)
  if (!data) return <div className="form-panel"><p role={error ? 'alert' : 'status'}>{error || 'Loading conversation…'}</p></div>
  return <div className="customer-chat conversation-panel">
    <div className="conversation-header"><div><div className="ticket-meta"><strong>{data.number}</strong><span className={`status-pill status-${data.status.toLowerCase()}`}>{label(data.status)}</span></div><h2>{data.routing_state === 'ASSIGNED' ? `Chat with ${data.assigned_agent_name}` : data.routing_state === 'COMPLETE' ? 'Your support conversation' : 'Chat with an Agent'}</h2><p>{data.subject}</p></div><span className={`live-indicator ${connection}`}>{connection === 'live' ? 'Live updates' : 'Reconnecting…'}</span></div>
    <div className={`routing-banner routing-${data.routing_state.toLowerCase()}`} role="status"><strong>{data.routing_state === 'WAITING' ? `Waiting for an agent · Queue position ${data.queue_position ?? '—'}` : data.routing_state === 'ASSIGNED' ? `Assigned to ${data.assigned_agent_name}` : `Case ${label(data.status).toLowerCase()}`}</strong><span>{data.routing_state === 'WAITING' ? 'Your case is saved. We’ll connect you when an agent is available.' : 'Messages stay saved while your agent is away.'}</span></div>
    {error && <p className="error" role="alert">{error}</p>}
    <ChatThread messages={data.messages} endpoint={endpoint} closed={data.status === 'CLOSED'} intro={<details className="generated-ticket-summary"><summary>Automatic ticket summary · {data.number}</summary><dl><dt>Customer</dt><dd>{data.customer_email}</dd><dt>Order ID</dt><dd>{data.order_id || 'Not provided'}</dd><dt>Category</dt><dd>{label(data.category)}</dd><dt>Subject</dt><dd>{data.subject}</dd><dt>Status</dt><dd>{label(data.status)}</dd><dt>Priority</dt><dd>{label(data.priority)}</dd></dl></details>} />
  </div>
}
