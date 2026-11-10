import { useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, categories, label } from '../api'

type Step = 'email' | 'category' | 'description' | 'order' | 'review'
const steps: Step[] = ['email', 'category', 'description', 'order', 'review']
const prompts = {
  email: 'Hi! Before I find an agent, what’s your email address?',
  category: 'What can we help you with? Choose below, or type a category.',
  description: 'In a few words, what’s happening? Type your own description, or choose an example that matches your issue.',
  order: 'Do you have an order ID? You can type it below or skip for now.',
  review: 'Here’s your summary. Shall I start your support chat?',
}
const examples: Record<string, string[]> = {
  INSTALLATION: ['My eSIM QR code won’t scan.', 'I can’t install my eSIM.'],
  ACTIVATION: ['My eSIM won’t activate.', 'I need help activating my eSIM.'],
  CONNECTIVITY: ['My eSIM is installed but I have no internet.', 'My connection keeps dropping.'],
  ORDER: ['I haven’t received my eSIM order.', 'I need help with my order.'],
  TOPUP: ['I need help adding more data.', 'My top-up hasn’t appeared.'],
  REFUND: ['I’d like to request a refund.', 'I need an update on my refund.'],
  OTHER: ['I have a question about my eSIM.', 'I need help with my account.'],
}

function matchCategory(text: string): string | undefined {
  const normalized = text.toLowerCase().replace(/[\s_-]+/g, '')
  const direct = categories.find((value) => value.toLowerCase() === normalized)
  if (direct) return direct
  const aliases: Record<string, string> = {
    internet: 'CONNECTIVITY', nointernet: 'CONNECTIVITY', network: 'CONNECTIVITY', mobiledata: 'CONNECTIVITY',
    setup: 'INSTALLATION', install: 'INSTALLATION', qrcode: 'INSTALLATION', activate: 'ACTIVATION',
    purchase: 'ORDER', billing: 'ORDER', moredata: 'TOPUP', refunds: 'REFUND', general: 'OTHER',
  }
  return aliases[normalized]
}

export function GuidedIntake({ onSubmit, onCancel }: {
  onSubmit: (data: Record<string, string | null>) => Promise<void>; onCancel: () => void
}) {
  // Questions and unsent answers stay in React memory. Only confirmation creates
  // a SQL ticket; quick replies and the typed composer use the same handlers.
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [order, setOrder] = useState('')
  const [summary, setSummary] = useState('')
  const [reply, setReply] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const viewport = useRef<HTMLDivElement>(null)
  const stepIndex = steps.indexOf(step)

  useLayoutEffect(() => {
    const element = viewport.current
    if (!element) return
    const follow = () => { element.scrollTop = element.scrollHeight }
    follow()
    const observer = new ResizeObserver(follow)
    observer.observe(element)
    return () => observer.disconnect()
  }, [step, busy])

  function goTo(nextStep: Step) {
    setError('')
    setStep(nextStep)
    setReply(({ email, category: label(category), description, order, review: '' })[nextStep])
  }

  function chooseCategory(value: string) {
    setCategory(value)
    setSummary('')
    setError('')
    setStep('description')
    setReply(description)
  }

  async function describe(value: string) {
    if (value.trim().length < 5) { setError('Please add a little more detail about the issue.'); return }
    setBusy(true)
    setError('')
    try {
      const result = await api<{ subject: string }>('/customer/intake/summary', {
        method: 'POST', body: JSON.stringify({ category, description: value.trim() }),
      })
      setDescription(value.trim())
      setSummary(result.subject)
      setStep('order')
      setReply(order)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not continue. Your answer is still here.') }
    finally { setBusy(false) }
  }

  async function confirm() {
    setBusy(true)
    setError('')
    try { await onSubmit({ customer_email: email, category, description, order_id: order || null }) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not start the chat. Your answers are still here.') }
    finally { setBusy(false) }
  }

  function skipOrder() { setOrder(''); setReply(''); setError(''); setStep('review') }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const text = reply.trim()
    setError('')
    if (step === 'email') { setEmail(text); setReply(''); setStep('category') }
    else if (step === 'category') {
      const value = matchCategory(text)
      if (value) chooseCategory(value)
      else setError('Choose a category above, or type its name—for example, Connectivity or Refund.')
    } else if (step === 'description') await describe(text)
    else if (step === 'order') {
      if (!text || /^(skip|none|no|not available)$/i.test(text)) skipOrder()
      else { setOrder(text); setReply(''); setStep('review') }
    } else if (/^(yes|confirm|start|continue)[.!]?$/i.test(text)) await confirm()
    else if (/^(edit|change)[.!]?$/i.test(text)) goTo('email')
    else setError('Choose an option above, or type “yes” to start or “edit” to change your answers.')
  }

  const answers: Record<string, string> = { email, category: label(category), description, order: order || 'No order ID' }
  const inputLabel = { email: 'Your email', category: 'Category', description: 'Short description of the issue', order: 'Order ID (optional)', review: 'Your reply' }[step]
  const placeholder = { email: 'Your email address…', category: 'Type a category, or choose above…', description: 'Describe your issue…', order: 'Your order ID, or type skip…', review: 'Type yes to start, or edit…' }[step]

  return <div className="intake-panel conversational-intake">
    <div className="intake-heading"><div className="chat-title-block"><span className="support-avatar" aria-hidden="true">b</span><div><h2>Chat with an Agent</h2><p>{busy ? step === 'review' ? 'Starting your conversation…' : 'Preparing your summary…' : 'Badi assistant · A few details before we connect you'}</p></div></div><button className="chat-close" type="button" aria-label="Cancel chat setup" onClick={onCancel} disabled={busy}>×</button></div>
    <div className="intake-history" ref={viewport} role="log" aria-label="Support setup conversation" aria-live="polite">
      {steps.slice(0, stepIndex + 1).map((value, index) => <div key={value} className="intake-exchange">
        <div className="assistant-turn"><span className="assistant-label">Badi assistant</span><p>{prompts[value]}</p>
          {value === step && step === 'category' && <div className="quick-replies" role="group" aria-label="Pick a category">{categories.map((option) => <button type="button" key={option} disabled={busy} onClick={() => chooseCategory(option)}>{label(option)}</button>)}</div>}
          {value === step && step === 'description' && <div className="quick-replies issue-choices" role="group" aria-label="Common issues">{examples[category]?.map((option) => <button type="button" key={option} disabled={busy} onClick={() => void describe(option)}>{option}</button>)}</div>}
          {value === step && step === 'order' && <div className="quick-replies"><button type="button" disabled={busy} onClick={skipOrder}>Skip for now</button></div>}
          {value === step && step === 'review' && <>
            <div className="intake-review compact-review"><h3>{summary}</h3><p>{email} · {label(category)}{order ? ` · ${order}` : ''}</p><details><summary>Review ticket details</summary><dl><dt>Customer</dt><dd>{email}</dd><dt>Category</dt><dd>{label(category)}</dd><dt>Order ID</dt><dd>{order || 'Not provided'}</dd><dt>Status</dt><dd>Open</dd><dt>Priority</dt><dd>Medium</dd></dl><p>Your agent manages status and priority.</p></details></div>
            <div className="quick-replies"><button type="button" className="confirm-quick-reply" disabled={busy} onClick={() => void confirm()}>{busy ? 'Starting…' : 'Confirm and start chat'}</button><button type="button" disabled={busy} onClick={() => goTo('email')}>Edit answers</button></div>
          </>}
        </div>
        {index < stepIndex && <div className="intake-answer"><p>{answers[value]}</p></div>}
      </div>)}
    </div>
    {error && <p className="error intake-error" role="alert">{error}</p>}
    <form className="intake-chat-composer" onSubmit={send}>
      {stepIndex > 0 && <button className="composer-back" type="button" disabled={busy} aria-label="Previous question" onClick={() => goTo(steps[stepIndex - 1])}>←</button>}
      <label className="sr-only" htmlFor="intake-reply">{inputLabel}</label>
      {step === 'description' ? <textarea id="intake-reply" key={step} value={reply} onChange={(event) => setReply(event.target.value)} minLength={5} maxLength={10000} rows={2} placeholder={placeholder} required disabled={busy} autoFocus />
        : <input id="intake-reply" key={step} type={step === 'email' ? 'email' : 'text'} name={step === 'email' ? 'customer_email' : undefined} value={reply} onChange={(event) => setReply(event.target.value)} autoComplete={step === 'email' ? 'email' : 'off'} maxLength={step === 'email' ? 254 : step === 'order' ? 100 : 200} placeholder={placeholder} required={step !== 'order'} disabled={busy} autoFocus />}
      <button className="button" type="submit" disabled={busy} aria-label="Send answer">{busy ? '…' : 'Send ↑'}</button>
    </form>
    <p className="intake-composer-hint">Choose a quick reply above, or type your own answer.</p>
  </div>
}
