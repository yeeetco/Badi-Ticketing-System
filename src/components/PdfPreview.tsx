import { useEffect, useRef, useState } from 'react'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// Vite serves the worker locally. File bytes never go to an external viewer.
GlobalWorkerOptions.workerSrc = workerUrl

export default function PdfPreview({ data, filename }: { data: Uint8Array; filename: string }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [error, setError] = useState('')
  const [rendering, setRendering] = useState(true)
  const [width, setWidth] = useState(800)
  const container = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    let active = true
    // Draw document content only; PDF scripts and interactive annotations are
    // not executed or mounted into our app.
    // Use already-authorized bytes; no extra blob URL fetch or external access.
    // Copy before worker transfer so StrictMode retries retain the source data.
    const task = getDocument({ data: data.slice(), useSystemFonts: true, maxImageSize: 16000000 })
    task.promise.then((document) => { if (active) setPdf(document) })
      .catch(() => { if (active) setError('This PDF could not be previewed. Use Download to open it with your PDF reader.') })
    return () => { active = false; void task.destroy() }
  }, [data])

  useEffect(() => {
    if (!container.current) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width - 24)))
    observer.observe(container.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!pdf || !canvas.current) return
    const element = canvas.current
    let active = true
    let task: RenderTask | undefined
    async function draw() {
      try {
        const page = await pdf!.getPage(pageNumber)
        if (!active) return
        setRendering(true)
        const natural = page.getViewport({ scale: 1 })
        const viewport = page.getViewport({ scale: Math.min(width / natural.width, 2) })
        const scale = Math.min(window.devicePixelRatio || 1, 2)
        element.width = Math.floor(viewport.width * scale)
        element.height = Math.floor(viewport.height * scale)
        element.style.width = `${viewport.width}px`
        element.style.height = `${viewport.height}px`
        task = page.render({ canvas: element, viewport, transform: [scale, 0, 0, scale, 0, 0] })
        await task.promise
        if (active) setRendering(false)
      } catch { if (active) setError('The PDF page could not be rendered. You can still download the original.') }
    }
    void draw()
    return () => { active = false; task?.cancel() }
  }, [pdf, pageNumber, width])

  return <div className="pdf-reader" ref={container}>
    <div className="pdf-controls"><button className="secondary-button" disabled={!pdf || pageNumber <= 1 || rendering} onClick={() => setPageNumber((page) => page - 1)}>Previous page</button><span role="status">{pdf ? `Page ${pageNumber} of ${pdf.numPages}` : 'Loading PDF…'}</span><button className="secondary-button" disabled={!pdf || pageNumber >= pdf.numPages || rendering} onClick={() => setPageNumber((page) => page + 1)}>Next page</button></div>
    {error ? <p className="error" role="alert">{error}</p> : <div className="pdf-page"><canvas key={pageNumber} ref={canvas} role="img" aria-label={`Preview of ${filename}, page ${pageNumber}`} />{rendering && <p role="status">Rendering page…</p>}</div>}
  </div>
}
