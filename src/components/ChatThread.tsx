import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api, timestamp } from '../api'
import { AttachmentPreview } from './AttachmentPreview'
import type { Attachment, Message } from '../api'
import { useAgentActivity } from '../hooks/useAgentActivity'

export type ComposerDrafts = { PUBLIC: string; INTERNAL: string }

export function ChatThread({ messages, endpoint, agent = false, closed = false, viewerName, initialDraft, onDraftChange, intro, readOnly = false, readOnlyReason, caseStatus = 'OPEN', readOnlyAction, typingName }: {
  messages: Message[]; endpoint: string; agent?: boolean; closed?: boolean; viewerName?: string;
  initialDraft?: ComposerDrafts; onDraftChange?: (endpoint: string, drafts: ComposerDrafts) => void
  intro?: ReactNode; readOnlyAction?: ReactNode
  readOnly?: boolean; readOnlyReason?: string; caseStatus?: string
  typingName?: string
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
  const [preview, setPreview] = useState<Attachment | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const activity = useAgentActivity({ enabled: agent && !readOnly, endpoint, messages, viewport, draft: drafts.PUBLIC, internal, closed })

  function selectFile(value: File | undefined) {
    setError('')
    if (!value) return
    setFile(null)
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
        return <article key={message.id} data-customer-message={message.sender_role === 'CUSTOMER' && message.kind === 'PUBLIC' ? message.id : undefined} className={`message ${own ? 'own' : ''} ${message.kind === 'INTERNAL' ? 'internal-message' : ''}`}>
          <div className="message-author">{message.kind === 'INTERNAL' ? '🔒 Internal note · ' : ''}{own ? 'You' : message.sender_role === 'AGENT' ? message.sender_name : 'Customer'}</div>
          {message.body && <p>{message.body}</p>}
          {message.attachments?.map((attachment) => <div key={attachment.id} className="chat-attachment">{attachment.available !== false ? <><button type="button" className="attachment-open" aria-label={`View attachment ${attachment.filename}`} onClick={() => setPreview(attachment)}>📎 {attachment.filename}</button><small>{(attachment.size / 1024).toFixed(1)} KB</small><a href={`/api${endpoint}/attachments/${attachment.id}`} download={attachment.filename} aria-label={`Download ${attachment.filename}`}>Download</a></> : <span>Attachment unavailable: file security checks failed.</span>}</div>)}
          <time dateTime={message.created_at} title={new Date(message.created_at).toLocaleString()}>{timestamp(message.created_at)}</time>
          {!agent && own && message.seen_at && <em className="seen-note" title={`Seen ${timestamp(message.seen_at)}`}>Seen</em>}
        </article>
      })}
    </div>
    {!agent && typingName && !readOnly && <p className="typing-indicator" role="status"><span aria-hidden="true">•••</span> {typingName} is typing…</p>}

    {newMessages && <button className="new-message-button" onClick={() => {
      viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'smooth' })
      nearBottom.current = true
      setNewMessages(false)
    }}>New messages ↓</button>}

    {readOnly ? <div className="read-only-conversation"><p role="status">{readOnlyReason || 'Read-only conversation. Your message history is preserved.'}</p>{readOnlyAction}</div> : <form className={`composer ${internal ? 'note-composer' : ''}`} onSubmit={send}>
      {agent && <div className="composer-tabs" role="group" aria-label="Message visibility">
        <button type="button" aria-pressed={!internal} disabled={sending} onClick={() => { setInternal(false); setNotice('') }}>Public reply</button>
        <button type="button" aria-pressed={internal} disabled={sending} onClick={() => { setInternal(true); setNotice('') }}>Internal note</button>
      </div>}
      <label className={agent ? undefined : 'sr-only'} htmlFor="chat-reply">{internal ? 'Private note — visible only to support agents' : 'Your reply'}</label>
      <div className={agent ? 'agent-input-shell' : 'chat-input-shell'}>
        {!agent && <button type="button" className="composer-icon paperclip-button" aria-label="Attach a file" title="Attach a PDF or image, up to 2 MB" onClick={() => fileInput.current?.click()} disabled={sending}><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2a4 4 0 0 1 6 6L8 19" /></svg></button>}
        <textarea id="chat-reply" value={draft} onChange={(event) => { activity.onInput(); setDraft(event.target.value) }} maxLength={10000} rows={agent ? 3 : 2}
          placeholder={internal ? 'Add context for your team…' : closed ? 'This ticket is closed.' : 'Write a message…'}
          disabled={sending || (closed && !internal)} required={!file} />
        {!agent && <button className="composer-icon send-icon" aria-label="Send reply" title="Send message" disabled={sending || (!draft.trim() && !file) || closed}>{sending ? '…' : <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m3 3 19 9-19 9 4-9-4-9Zm4 9h15" /></svg>}</button>}
      </div>
      {!agent && <input ref={fileInput} className="sr-only" tabIndex={-1} type="file" aria-label="Attach PDF or image" accept=".pdf,.png,.jpg,.jpeg,.gif,.webp" onChange={(event) => selectFile(event.target.files?.[0])} disabled={sending} />}
      {file && <div className="selected-attachment">{file.name}<button type="button" className="filter-reset" aria-label="Remove attachment" onClick={() => setFile(null)} disabled={sending}>×</button></div>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="composer-bottom">
        <span className="helper" role="status">{closed && !internal ? 'An agent must reopen this ticket to continue.' : notice || (internal ? 'Never shared with the customer' : 'Replies are saved even when the other person is offline.')}</span>
        {agent && <button className="button" disabled={sending || (!draft.trim() && !file) || (closed && !internal)}>{sending ? 'Saving…' : internal ? 'Add note' : 'Send reply ↗'}</button>}
      </div>
    </form>}
    {preview && <AttachmentPreview key={preview.id} attachment={preview} endpoint={endpoint} onClose={() => setPreview(null)} />}
  </div>
}
