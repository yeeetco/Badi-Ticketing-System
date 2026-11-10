import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

function contentPolicy(html: string, development = false) {
  const hashes = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
    // HTML normalizes Windows CRLF before CSP hashes are evaluated.
    .map((match) => `'sha256-${createHash('sha256').update(match[1].replace(/\r\n?/g, '\n')).digest('base64')}'`).join(' ')
  return `default-src 'self'; script-src 'self' ${development ? "'unsafe-inline'" : hashes}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data: blob:; connect-src 'self' ${development ? 'ws://localhost:5173 ws://127.0.0.1:5173' : ''}; worker-src 'self' blob:; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'self'`
}
const headers = { 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()' }

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react(), {
    name: 'badi-production-csp',
    transformIndexHtml: { order: 'post', handler(html) {
      if (command !== 'build') return html
      return [{ tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: contentPolicy(html) }, injectTo: 'head-prepend' }]
    } },
  }],
  // Prebundle the lazy PDF reader at startup so opening a first attachment
  // doesn't trigger Vite's dependency-discovery reload during a conversation.
  optimizeDeps: { include: ['pdfjs-dist'] },
  preview: { headers: { ...headers, 'Content-Security-Policy': `${contentPolicy(readFileSync('index.html', 'utf8'))}; frame-ancestors 'none'` } },
  server: {
    headers: { ...headers, 'Content-Security-Policy': `${contentPolicy('', true)}; frame-ancestors 'none'` },
    fs: { strict: true, deny: ['.env', '.env.*', '**/*.{crt,pem,key}', '**/.git/**', '**/.local/**', '**/backend/**'] },
    host: '127.0.0.1',
    port: 5173,
    // Refuse a busy port instead of silently choosing an unconfigured origin.
    strictPort: true,
    // The browser calls /api on Vite; Vite forwards it to FastAPI.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        configure(proxy) {
          proxy.on('proxyReq', (request) => {
            // Untrusted forwarded headers must not become an apparent client IP
            // on the loopback API and bypass its request budgets.
            for (const name of ['x-forwarded-for', 'x-real-ip', 'forwarded', 'x-forwarded-host']) request.removeHeader(name)
          })
        },
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
}))
