import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, label, timestamp } from '../api'
import type { CustomerTicket } from '../api'
import { GuidedIntake } from './GuidedIntake'

export function CustomerBot({ onCreate, onResume }: {
  onCreate: (data: Record<string, string | null>) => Promise<void>; onResume: (ticket: CustomerTicket) => void
}) {
  const [startedAt] = useState(() => new Date().toISOString())
  const [mode, setMode] = useState<'welcome' | 'new' | 'code'>('welcome')
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [found, setFound] = useState<CustomerTicket | null>(null)

  async function startNew() {
    try {
      if (found) await api('/customer/logout', { method: 'POST' })
      setFound(null)
      setError('')
      setReply('')
      setMode('new')
    } catch { setError('We couldn’t prepare a new chat just now. Your history is safe—please try again.') }
  }

  async function recover(code: string) {
    setBusy(true)
    setError('')
    try {
      // Only the private capability code unlocks a case. Email and a readable
      // ticket number cannot enumerate someone else's conversations.
      const ticket = await api<CustomerTicket>('/customer/access', { method: 'POST', body: JSON.stringify({ access_code: code.trim() }) })
      if (!['RESOLVED', 'CLOSED'].includes(ticket.status)) onResume(ticket)
      else setFound(ticket)
    } catch {
      setError('I’m sorry, I couldn’t open a conversation with that code. Please check the private code saved with your ticket, or start a new chat—we can still help.')
    } finally { setBusy(false) }
  }

  function showFaq() {
    location.hash = '/faq'
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const value = reply.trim()
    if (mode === 'code') { await recover(value); return }
    if (/faq|question|answers/i.test(value)) showFaq()
    else if (/code|ticket|BD-\d+/i.test(value)) { setMode('code'); setReply('') }
    else if (/^[\w-]{20,100}$/.test(value)) { setMode('code'); await recover(value) }
    else await startNew()
  }

  if (mode === 'new') return <GuidedIntake onSubmit={onCreate} onCancel={() => setMode('welcome')} />
  return <div className="intake-panel conversational-intake welcome-bot">
    <div className="intake-heading"><div className="chat-title-block"><span className="support-avatar" aria-hidden="true">b</span><div><h2>Chat with Badi Support</h2><p>Your journey matters. We’re here to help.</p></div></div></div>
    <div className="intake-history" role="log" aria-label="Badi assistant" aria-live="polite">
      <div className="assistant-turn"><span className="assistant-label">Badi assistant · Automated</span>
        <p>{mode === 'welcome' ? 'Hi, welcome to Badi. I know connection or travel problems can be frustrating. Let’s find the right help together. Is this a new question, or do you have a private ticket code?' : 'Of course—let’s pick up where you left off. Please enter the private access code saved with your ticket. I’ll check its status and bring back your conversation securely.'}</p>
        <time dateTime={startedAt}>{timestamp(startedAt)}</time>
        {mode === 'welcome' && <div className="quick-replies"><button onClick={() => void startNew()}>Start a new chat</button><button onClick={() => { setMode('code'); setReply(''); setError('') }}>I have a ticket code</button><button onClick={showFaq}>Browse quick answers</button></div>}
        {found && <div className="recovered-ticket"><strong>{found.number} · {label(found.status)}</strong><p>I found your conversation. It’s already {label(found.status).toLowerCase()}, so its history is available to read. If you still need help, we’ll make a fresh request for you.</p><div className="quick-replies"><button onClick={() => onResume(found)}>View conversation history</button><button onClick={() => void startNew()}>Start a new chat</button></div></div>}
        {mode === 'code' && !found && <p className="bot-reassurance">Your ticket number alone won’t unlock private messages. We’ll never ask you to share a password here.</p>}
      </div>
    </div>
    {error && <p className="error intake-error" role="alert">{error}</p>}
    <form className="intake-chat-composer" onSubmit={send}><label className="sr-only" htmlFor="bot-answer">{mode === 'code' ? 'Private access code' : 'Message to Badi assistant'}</label><input id="bot-answer" type={mode === 'code' ? 'password' : 'text'} value={reply} onChange={(event) => setReply(event.target.value)} placeholder={mode === 'code' ? 'Paste your private ticket code…' : 'Tell us how we can help…'} autoComplete="off" maxLength={500} minLength={mode === 'code' ? 20 : 1} disabled={busy || !!found} required /><button className="button" disabled={busy || !!found} aria-label="Send to assistant">{busy ? 'Checking…' : 'Send ↑'}</button></form>
    {mode === 'code' && <button className="filter-reset" onClick={() => { setMode('welcome'); setFound(null); setReply(''); setError('') }}>← Back to assistant</button>}
  </div>
}
