import { setCapacity } from './helpers'
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

const headers = { Origin: 'http://127.0.0.1:5173' }
function credentials(file: string) {
  const text = readFileSync(file, 'utf8')
  return { email: text.match(/Email: (.+)/)![1].trim(), password: text.match(/Password: (.+)/)![1].trim() }
}

test('customer attachment reaches the agent, validates limits, and End Chat closes with a clean restart', async ({ browser }) => {
  const customer = await browser.newContext()
  const agent = await browser.newContext()
  let ticketId: number | undefined
  try {
    const staff = credentials('.local/agent-credentials.txt')
    await agent.request.post('/api/auth/login', { data: staff, headers })
    await setCapacity(agent.request, 20)
    await agent.request.patch('/api/agents/me/availability', { data: { availability: 'ONLINE' }, headers })
    const creation = await customer.request.post('/api/customer/tickets', { data: { customer_email: 'attachment-browser@example.com', category: 'CONNECTIVITY', description: `Attachment verification ${Date.now()}. My connection is unavailable.` }, headers })
    expect(creation.status()).toBe(201)
    const ticket = (await creation.json()).ticket
    ticketId = ticket.id
    const page = await customer.newPage()
    await page.goto('/#/support')
    await expect(page.locator('.conversation-header .status-pill')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'End Chat', exact: true })).toBeVisible()
    const input = page.getByLabel('Attach PDF or image', { exact: true })
    await input.setInputFiles({ name: 'too-large.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(2097153) })
    await expect(page.getByRole('alert')).toContainText('2 MB or smaller')
    const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABQAAAAUCAIAAAAC64paAAAAK0lEQVR4nGNkaGAgGzCRr5VhVDOpgIlkHUhgVDOJgIlUDchgVDOJgKIAAwDFMgCoOrIAcgAAAABJRU5ErkJggg==', 'base64')
    await input.setInputFiles({ name: 'connection.png', mimeType: 'image/png', buffer: image })
    await page.getByLabel('Your reply', { exact: true }).fill('Here is what my phone shows.')
    await page.getByRole('button', { name: 'Send reply' }).click()
    await expect(page.getByRole('link', { name: /connection.png/ })).toBeVisible()
    const inbox = await agent.newPage()
    await inbox.goto('/#/agent')
    await expect(inbox.getByRole('button', { name: /New ticket/ })).toHaveCount(0)
    await inbox.getByLabel('Staff account', { exact: true }).click()
    await expect(inbox.getByLabel('Chat capacity', { exact: true })).toHaveCount(0)
    await inbox.getByLabel('Staff account', { exact: true }).click()
    await inbox.locator('.ticket-queue').getByRole('button').filter({ hasText: ticket.number }).click()
    await expect(inbox.getByRole('link', { name: /connection.png/ })).toBeVisible()
    await expect(inbox.getByLabel('Transfer to', { exact: true })).toHaveCount(0)
    await inbox.getByRole('button', { name: 'Transfer conversation', exact: true }).click()
    await expect(inbox.getByLabel('Transfer to', { exact: true })).toBeVisible()
    await inbox.getByRole('button', { name: 'Cancel transfer' }).click()
    await expect(inbox.getByLabel('Transfer to', { exact: true })).toHaveCount(0)
    const fileUrl = await inbox.getByRole('link', { name: /connection.png/ }).getAttribute('href')
    expect((await agent.request.get(fileUrl!)).status()).toBe(200)
    let downloads = 0
    inbox.on('download', () => downloads++)
    await inbox.getByRole('button', { name: 'Switch to dark mode', exact: true }).click()
    await inbox.getByRole('button', { name: 'View attachment connection.png', exact: true }).click()
    await expect(inbox.getByRole('dialog')).toBeVisible()
    await expect(inbox.getByRole('img', { name: 'connection.png', exact: true })).toBeVisible()
    expect(downloads).toBe(0)
    await expect(inbox.getByRole('img', { name: 'connection.png', exact: true })).toHaveCSS('filter', 'none')
    await inbox.screenshot({ path: '.local/attachment-preview-dark.png', fullPage: true })
    await inbox.getByRole('button', { name: 'Close attachment preview', exact: true }).click()
    const [download] = await Promise.all([
      inbox.waitForEvent('download'),
      inbox.getByRole('link', { name: 'Download connection.png', exact: true }).click(),
    ])
    expect(download.suggestedFilename()).toBe('connection.png')
    await input.setInputFiles({ name: 'order.pdf', mimeType: 'application/pdf', buffer: readFileSync('tests/fixtures/sample.pdf') })
    await page.getByRole('button', { name: 'Send reply' }).click()
    await inbox.getByRole('button', { name: 'View attachment order.pdf', exact: true }).click()
    await expect(inbox.getByRole('img', { name: 'Preview of order.pdf, page 1', exact: true })).toBeVisible()
    await expect(inbox.getByText('Rendering page…', { exact: true })).toHaveCount(0)
    await expect(inbox.getByText('Page 1 of 1', { exact: true })).toBeVisible()
    await inbox.screenshot({ path: '.local/pdf-preview-dark.png', fullPage: true })
    await inbox.getByRole('button', { name: 'Close attachment preview', exact: true }).click()
    await page.getByRole('button', { name: 'Switch to dark mode', exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await page.screenshot({ path: '.local/attachment-mobile.png', fullPage: true })
    await page.getByRole('button', { name: 'End Chat', exact: true }).click()
    await expect(page.locator('.messages')).toContainText('You have disconnected. This chat is now closed.')
    await expect(page.getByRole('button', { name: 'Start Over', exact: true })).toBeVisible()
    expect((await customer.request.get('/api/customer/session')).status()).toBe(200)
    const detail = await (await agent.request.get(`/api/tickets/${ticketId}`)).json()
    expect(detail.status).toBe('CLOSED')
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await expect(page.getByRole('button', { name: 'Start Over', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Start Over', exact: true }).click()
    await expect(page.locator('.ticket-meta, .routing-banner')).toHaveCount(0)
    expect((await customer.request.get('/api/customer/session')).status()).toBe(401)
  } finally {
    if (ticketId) await agent.request.patch(`/api/tickets/${ticketId}`, { data: { status: 'CLOSED' }, headers })
    await setCapacity(agent.request, 5)
    await agent.request.patch('/api/agents/me/availability', { data: { availability: 'OFFLINE' }, headers })
    await agent.request.post('/api/auth/logout', { headers })
    await customer.close(); await agent.close()
  }
})

test('administrator creates, edits roles and profiles, and deletes a staff account', async ({ page }) => {
  const staff = credentials('.local/admin-credentials.txt')
  const email = `qa-${Date.now()}@example.com`
  let id: number | undefined
  try {
    await page.goto('/#/admin')
    await page.getByLabel('Email', { exact: true }).fill(staff.email)
    await page.getByLabel('Password', { exact: true }).fill(staff.password)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Staff accounts' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Administration', exact: true })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Main navigation', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Roles & permissions', exact: true }).click()
    await expect(page.getByRole('region', { name: 'Role permissions', exact: true })).toContainText('No conversation access')
    await page.getByRole('button', { name: 'Users', exact: true }).click()
    await page.getByRole('button', { name: 'Add user', exact: true }).click()
    const editor = page.locator('.staff-editor')
    await editor.getByLabel('Full name').fill('QA Operator')
    await editor.getByLabel('Email address').fill(email)
    await editor.getByLabel('Password', { exact: true }).fill('Browser-test-password-123')
    await editor.getByRole('button', { name: 'Save user' }).click()
    const row = page.locator('.admin-user').filter({ hasText: email })
    await expect(row).toBeVisible()
    const users = await (await page.request.get('/api/admin/users')).json()
    id = users.find((user: { email: string }) => user.email === email).id
    await row.getByRole('button', { name: 'Edit QA Operator', exact: true }).click()
    await editor.getByLabel('Full name').fill('QA Supervisor')
    await editor.getByLabel('Role', { exact: true }).selectOption('TEAM_LEAD')
    await editor.getByRole('button', { name: 'Save user' }).click()
    await expect(row).toContainText('Team lead')
    await page.screenshot({ path: '.local/admin-desktop.png', fullPage: true })
    await page.getByRole('button', { name: 'Switch to dark mode', exact: true }).click()
    await page.screenshot({ path: '.local/admin-desktop-dark.png', fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await page.screenshot({ path: '.local/admin-mobile.png', fullPage: true })
    await row.getByRole('button', { name: 'Delete QA Supervisor', exact: true }).click()
    await row.getByRole('button', { name: 'Confirm delete', exact: true }).click()
    await expect(row).toHaveCount(0)
  } finally {
    if (id) await page.request.delete(`/api/admin/users/${id}`, { headers })
    await page.request.post('/api/auth/logout', { headers })
  }
})
