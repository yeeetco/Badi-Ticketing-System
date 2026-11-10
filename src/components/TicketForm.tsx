import { useState } from 'react'
import type { FormEvent } from 'react'
import { categories, priorities, label } from '../api'

export function TicketForm({ onSubmit, onCancel }: {
  onSubmit: (data: Record<string, string | null>) => Promise<void>; onCancel: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>
    setBusy(true)
    setError('')
    try {
      await onSubmit({ ...data, order_id: data.order_id.trim() || null })
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not create the ticket.')
    } finally { setBusy(false) }
  }

  return <form className="ticket-form" onSubmit={submit}>
    <div className="form-grid">
      <label>Customer email<input name="customer_email" type="email" autoComplete="email" maxLength={254} required /></label>
      <label>Order ID <span className="muted">(optional)</span><input name="order_id" maxLength={100} placeholder="ORD-10293" /></label>
      <label>Category<select name="category" defaultValue="CONNECTIVITY">{categories.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Priority<select name="priority" defaultValue="MEDIUM">{priorities.map((value) => <option value={value} key={value}>{label(value)}</option>)}</select></label>
    </div>
    <label>Subject<input name="subject" maxLength={200} required placeholder="A short description of the issue" /></label>
    <label>How can we help?<textarea name="description" rows={4} maxLength={10000} required placeholder="Tell us what happened and what you've tried…" /></label>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="form-actions"><button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Cancel</button><button className="button" disabled={busy}>{busy ? 'Creating…' : 'Create ticket'}</button></div>
  </form>
}
