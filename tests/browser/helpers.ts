import { request } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'

// Test workload limits through the Administrator API; the agent endpoint
// intentionally rejects capacity changes, even if someone forges the request.
export async function setCapacity(actor: APIRequestContext, capacity: number) {
  const profile = await (await actor.get('/api/auth/me')).json()
  const credentials = readFileSync('.local/admin-credentials.txt', 'utf8')
  const admin = await request.newContext({ baseURL: 'http://127.0.0.1:5173', extraHTTPHeaders: { Origin: 'http://127.0.0.1:5173' } })
  try {
    const login = await admin.post('/api/auth/login', { data: { email: credentials.match(/Email: (.+)/)![1].trim(), password: credentials.match(/Password: (.+)/)![1].trim() } })
    if (login.status() !== 200) throw new Error('Test administrator sign-in failed.')
    const user = await (await admin.get(`/api/admin/users/${profile.id}`)).json()
    const body = Object.fromEntries(['name', 'email', 'role', 'area', 'tier', 'is_active'].map((key) => [key, user[key]]))
    const saved = await admin.put(`/api/admin/users/${profile.id}`, { data: { ...body, max_active_chats: capacity } })
    if (saved.status() !== 200) throw new Error('Could not configure the test workload through Administrator.')
  } finally { await admin.post('/api/auth/logout'); await admin.dispose() }
}
