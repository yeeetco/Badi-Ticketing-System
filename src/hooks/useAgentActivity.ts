import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { api } from '../api'
import type { Message } from '../api'

export function useAgentActivity({ enabled, endpoint, messages, viewport, draft, internal, closed }: {
  enabled: boolean; endpoint: string; messages: Message[]; viewport: RefObject<HTMLDivElement | null>;
  draft: string; internal: boolean; closed: boolean
}) {
  const lastInput = useRef(0)
  const draftRef = useRef(draft)
  const acknowledged = useRef(0)
  useEffect(() => { draftRef.current = draft }, [draft])

  useEffect(() => {
    if (!enabled || !viewport.current) return
    let active = true
    let pending = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    function actuallyVisible(element: Element) {
      if (!viewport.current) return false
      const box = element.getBoundingClientRect()
      const bounds = viewport.current.getBoundingClientRect()
      return Math.min(box.bottom, bounds.bottom, window.innerHeight) - Math.max(box.top, bounds.top, 0) >= Math.min(24, box.height)
        && Math.min(box.right, bounds.right, window.innerWidth) > Math.max(box.left, bounds.left, 0)
    }
    function acknowledge(id: number) {
      if (document.visibilityState !== 'visible' || document.querySelector('dialog[open]') || id <= acknowledged.current) return
      pending = Math.max(pending, id)
      clearTimeout(timer)
      timer = setTimeout(() => {
        const target = pending
        pending = 0
        if (!active || document.visibilityState !== 'visible' || document.querySelector('dialog[open]')) return
        const element = viewport.current?.querySelector(`[data-customer-message="${target}"]`)
        if (!element || !actuallyVisible(element)) return
        void api(`${endpoint}/read`, { method: 'POST', body: JSON.stringify({ message_id: target }) })
          .then(() => { if (active) acknowledged.current = Math.max(acknowledged.current, target) })
          .catch(() => { /* A failed receipt stays unread and can be retried on the next snapshot/view. */ })
      }, 200)
    }
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && actuallyVisible(entry.target)) acknowledge(Number((entry.target as HTMLElement).dataset.customerMessage))
      }
    }, { root: viewport.current, threshold: [0, .01, .5, 1] })
    viewport.current.querySelectorAll('[data-customer-message]').forEach((element) => observer.observe(element))
    function visibleAgain() {
      if (document.visibilityState !== 'visible' || !viewport.current) return
      viewport.current.querySelectorAll<HTMLElement>('[data-customer-message]').forEach((element) => {
        if (actuallyVisible(element)) acknowledge(Number(element.dataset.customerMessage))
      })
    }
    document.addEventListener('visibilitychange', visibleAgain)
    document.addEventListener('close', visibleAgain, true)
    document.addEventListener('scroll', visibleAgain, true)
    window.addEventListener('resize', visibleAgain)
    return () => { active = false; clearTimeout(timer); observer.disconnect(); document.removeEventListener('visibilitychange', visibleAgain); document.removeEventListener('close', visibleAgain, true); document.removeEventListener('scroll', visibleAgain, true); window.removeEventListener('resize', visibleAgain) }
  }, [enabled, endpoint, messages, viewport])

  useEffect(() => {
    if (!enabled || internal || closed) return
    let last = { typing: false, at: 0 }
    function tick() {
      const now = Date.now()
      const typing = !!draftRef.current.trim() && document.visibilityState === 'visible' && now - lastInput.current < 3000
      if (typing !== last.typing || (typing && now - last.at >= 2000)) {
        last = { typing, at: now }
        void api(`${endpoint}/typing`, { method: 'POST', body: JSON.stringify({ is_typing: typing, visibility: 'PUBLIC' }) }).catch(() => {})
      }
    }
    const timer = setInterval(tick, 600)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(timer); document.removeEventListener('visibilitychange', tick)
      if (last.typing) void api(`${endpoint}/typing`, { method: 'POST', keepalive: true, body: JSON.stringify({ is_typing: false }) }).catch(() => {})
    }
  }, [enabled, endpoint, internal, closed])

  return { onInput: () => { if (enabled && !internal) lastInput.current = Date.now() } }
}
