import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { Attachment } from '../api'

const PdfPreview = lazy(() => import('./PdfPreview'))

export function AttachmentPreview({ attachment, endpoint, onClose }: {
  attachment: Attachment; endpoint: string; onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [url, setUrl] = useState('')
  const [pdfData, setPdfData] = useState<Uint8Array | null>(null)
  const [error, setError] = useState('')
  const path = `/api${endpoint}/attachments/${attachment.id}`

  useEffect(() => {
    const modal = dialog.current
    modal?.showModal()
    return () => { modal?.close() }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl = ''
    // Fetch bytes through the authorized endpoint, never a public upload URL.
    fetch(path, { credentials: 'same-origin', signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error('Preview unavailable. Your access may have ended; close this window and try again.')
      const blob = await response.blob()
      if (attachment.content_type === 'application/pdf') {
        const data = new Uint8Array(await blob.arrayBuffer())
        if (!controller.signal.aborted) setPdfData(data)
      } else if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) }
    }).catch((failure) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Could not preview file.') })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [path, attachment.content_type])

  return <dialog className="attachment-preview" ref={dialog} onCancel={onClose} aria-labelledby="preview-title">
    <div className="preview-toolbar"><h2 id="preview-title">{attachment.filename}</h2><div><a className="secondary-button" href={path} download={attachment.filename}>Download</a><button className="secondary-button" type="button" onClick={onClose} autoFocus aria-label="Close attachment preview">✕</button></div></div>
    {error ? <p className="error" role="alert">{error}</p> : pdfData ? <Suspense fallback={<p role="status">Loading PDF viewer…</p>}><PdfPreview data={pdfData} filename={attachment.filename} /></Suspense> : url ? <img className="image-preview" src={url} alt={attachment.filename} /> : <p role="status">Loading preview…</p>}
  </dialog>
}
