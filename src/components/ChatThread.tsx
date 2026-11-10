import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api, timestamp } from '../api'
import type { Message } from '../api'

export type ComposerDrafts = { PUBLIC: string; INTERNAL: string }

export function ChatThread({ messages, endpoint, agent = false, closed = false, viewerName, initialDraft, onDraftChange, intro, readOnly = false, readOnlyReason, caseStatus = 'OPEN' }: {
  messages: Message[]; endpoint: string; agent?: boolean; closed?: boolean; viewerName?: string;
  initialDraft?: ComposerDrafts; onDraftChange?: (endpoint: string, drafts: ComposerDrafts) => void
  intro?: ReactNode
  readOnly?: boolean; readOnlyReason?: string; caseStatus?: string
}) {
  const [drafts, setDrafts] = useState<ComposerDrafts>(() => initialDraft ?? { PUBLIC: '', INTERNAL: '' })
  const [internal, setInternal] = useState(false)
  const draft = drafts[internal ? 'INTERNAL' : 'PUBLIC']

  function setDraft(value: string) {
    // Keep private and public drafts separate. Switching reply mode must never
    // carry a private note into the public composer. Cache only in workspace
    // memory so switching tickets preserves drafts, while logout clears them.
    const next = { ...drafts, [internal ? 'INTERNAL' : 'PUBLIC']: value }
    setDrafts(next)
    onDraftChange?.(endpoint, next)
  }
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const viewport = useRef<HTMLDivElement>(null)
  const nearBottom = useRef(true)
  const [newMessages, setNewMessages] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  function selectFile(value: File | undefined) {
    setError('')
    if (!value) return
    if (value.size > 2 * 1024 * 1024 || value.size === 0) {
      setError('Choose a nonempty file that is 2 MB or smaller.')
    } else if (!['application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(value.type)) {
      setError('Choose a PDF, PNG, JPEG, GIF, or WebP image.')
    } else { setFile(value) }
    if (fileInput.current) fileInput.current.value = ''
  }

  // Follow replies only if the reader is already near the bottom. Reading an
  // older message must not be interrupted by an incoming reply.
  useEffect(() => {
    if (nearBottom.current) viewport.current?.scrollTo({ top: viewport.current.scrollHeight })
    else if (messages.length) queueMicrotask(() => setNewMessages(true))
  }, [messages.length])

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if ((!draft.trim() && !file) || sending) return
    setSending(true)
    setError('')
    setNotice('')
    try {
      const multipart = new FormData()
      if (file) { multipart.append('file', file); multipart.append('body', draft) }
      await api<Message>(`${endpoint}/${file ? 'attachments' : 'messages'}`, {
        method: 'POST',
        body: file ? multipart : JSON.stringify(agent ? { body: draft, kind: internal ? 'INTERNAL' : 'PUBLIC' } : { body: draft }),
      })
      setDraft('')
      setFile(null)
      setNotice(internal ? 'Internal note saved. Only agents can see it.' : 'Reply saved.')
      nearBottom.current = true
    } catch (failure) {
      // Keep the draft on failure so the user can retry without retyping.
      setError(failure instanceof Error ? failure.message : 'Message could not be sent.')
    } finally {
      setSending(false)
    }
  }

  return <div className={`chat-thread conversation-state-${caseStatus.toLowerCase()}`}>
    <div className="messages" ref={viewport} role="log" aria-label="Conversation messages" aria-live="polite" aria-relevant="additions" onScroll={() => {
      const element = viewport.current
      if (element) nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80
      if (nearBottom.current) setNewMessages(false)
    }}>
      <div className="conversation-start">This is the start of your support conversation</div>
      {intro}
      {messages.map((message) => {
        const own = agent ? message.sender_role === 'AGENT' && message.sender_name !== 'System update' && (!viewerName || message.sender_name === viewerName) : message.sender_role === 'CUSTOMER'
        return <article key={message.id} className={`message ${own ? 'own' : ''} ${message.kind === 'INTERNAL' ? 'internal-message' : ''}`}>
          <div className="message-author">{message.kind === 'INTERNAL' ? '🔒 Internal note · ' : ''}{own ? 'You' : message.sender_role === 'AGENT' ? message.sender_name : 'Customer'}</div>
          {message.body && <p>{message.body}</p>}
          {message.attachments?.map((attachment) => <a key={attachment.id} className="chat-attachment" href={`/api${endpoint}/attachments/${attachment.id}`} download={attachment.filename}>📎 {attachment.filename}<small>{(attachment.size / 1024).toFixed(1)} KB · Download</small></a>)}
          <time dateTime={message.created_at} title={new Date(message.created_at).toLocaleString()}>{timestamp(message.created_at)}</time>
        </article>
      })}
    </div>

    {newMessages && <button className="new-message-button" onClick={() => {
      viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'smooth' })
      nearBottom.current = true
      setNewMessages(false)
    }}>New messages ↓</button>}

    {readOnly ? <div className="read-only-conversation" role="status">{readOnlyReason || 'Read-only conversation. Your message history is preserved.'}</div> : <form className={`composer ${internal ? 'note-composer' : ''}`} onSubmit={send}>
      {agent && <div className="composer-tabs" role="group" aria-label="Message visibility">
        <button type="button" aria-pressed={!internal} disabled={sending} onClick={() => { setInternal(false); setNotice('') }}>Public reply</button>
        <button type="button" aria-pressed={internal} disabled={sending} onClick={() => { setInternal(true); setNotice('') }}>Internal note</button>
      </div>}
      <label htmlFor="chat-reply">{internal ? 'Private note — visible only to support agents' : 'Your reply'}</label>
      <textarea id="chat-reply" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={10000} rows={3}
        placeholder={internal ? 'Add context for your team…' : closed ? 'This ticket is closed.' : 'Write a message…'}
        disabled={sending || (closed && !internal)} required={!file} />
      {!agent && <div className="attachment-picker"><input ref={fileInput} className="sr-only" tabIndex={-1} type="file" aria-label="Attach PDF or image" accept=".pdf,.png,.jpg,.jpeg,.gif,.webp" onChange={(event) => selectFile(event.target.files?.[0])} disabled={sending} /><button type="button" className="secondary-button attachment-button" aria-label="Attach a file" onClick={() => fileInput.current?.click()} disabled={sending}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2a4 4 0 0 1 6 6L8 19" /></svg> Attach</button><span className="helper">PDF or image · Up to 2 MB</span>{file && <span className="selected-attachment">{file.name}<button type="button" className="filter-reset" aria-label="Remove attachment" onClick={() => setFile(null)} disabled={sending}>×</button></span>}</div>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="composer-bottom">
        <span className="helper" role="status">{closed && !internal ? 'An agent must reopen this ticket to continue.' : notice || (internal ? 'Never shared with the customer' : 'Replies are saved even when the other person is offline.')}</span>
        <button className="button" disabled={sending || (!draft.trim() && !file) || (closed && !internal)}>{sending ? 'Saving…' : internal ? 'Add note' : 'Send reply ↗'}</button>
      </div>
    </form>}
  </div>
}
