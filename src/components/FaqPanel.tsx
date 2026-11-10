import { useEffect, useState } from 'react'
import { api, label } from '../api'
import type { FaqRevision } from '../api'

export function FaqPanel() {
  const [faq, setFaq] = useState<FaqRevision | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api<FaqRevision>('/help/faq').then((data) => { if (active) setFaq(data) })
      .catch(() => { if (active) setError('The quick answers could not load. You can still chat with us or open Badi’s full FAQ.') })
    return () => { active = false }
  }, [])
  const items = faq?.items.filter((item) => `${item.question} ${item.answer} ${item.category}`.toLowerCase().includes(query.toLowerCase()))
  return <aside className="faq-panel" id="support-faq" aria-label="Badi quick answers">
    <div className="faq-heading"><span className="eyebrow">A LITTLE GUIDANCE</span><h2>Answers for your journey.</h2><p>Find a quick answer, or let us help you personally.</p></div>
    <label className="faq-search" htmlFor="faq-search">Search help<input id="faq-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Activation, data, hotspot…" /></label>
    {error && <p role="alert">{error}</p>}
    {!faq && !error && <p role="status">Loading quick answers…</p>}
    {items?.length === 0 && <p>No matching answers yet. Tell our assistant what’s happening—we’ll help you from there.</p>}
    <div className="faq-list">{items?.map((item) => <details key={item.id}><summary>{item.question}</summary><span className="faq-topic">{label(item.category)}</span><p>{item.answer}</p></details>)}</div>
    <div className="faq-source"><a href={faq?.source_url ?? 'https://badiesim.com/help/faq'} target="_blank" rel="noreferrer">Read Badi’s full FAQ ↗</a>{faq && <small>Reviewed {faq.reviewed_on}</small>}</div>
  </aside>
}
