import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { setCapacity } from './helpers'

const headers = { Origin: 'http://127.0.0.1:5173' }

test('real message visibility drives Seen and unread; only public typing and replies reach the customer', async ({ browser }) => {
  const customer = await browser.newContext()
  const staff = await browser.newContext({ viewport: { width: 1600, height: 1100 } })
  const source = readFileSync('.local/agent-credentials.txt', 'utf8')
  const credentials = { email: source.match(/Email: (.+)/)![1].trim(), password: source.match(/Password: (.+)/)![1].trim() }
  let id: number | undefined
  let capacity = 5
  try {
    const loggedIn = await staff.request.post('/api/auth/login', { data: credentials, headers })
    expect(loggedIn.status()).toBe(200)
    capacity = (await loggedIn.json()).max_active_chats
    await setCapacity(staff.request, 20)
    const created = await customer.request.post('/api/customer/tickets', { data: {
      customer_email: 'activity-browser@example.com', category: 'CONNECTIVITY', description: `Activity verification ${Date.now()}. My eSIM cannot connect.`,
    }, headers })
    expect(created.status()).toBe(201)
    const ticket = (await created.json()).ticket
    id = ticket.id
    const page = await customer.newPage()
    const agent = await staff.newPage()
    await page.goto('/#/support')
    await agent.goto('/#/agent')
    const row = agent.locator('.ticket-row').filter({ hasText: ticket.number })
    await expect(row.locator('.unread-badge')).toHaveText('1')
    await expect(row.locator('.reply-wait')).toContainText('Awaiting reply')
    await expect(page.locator('.seen-note')).toHaveCount(0)
    await agent.getByRole('button', { name: 'Switch to dark mode', exact: true }).click()
    await agent.screenshot({ path: '.local/agent-unread-dark.png', fullPage: true })
    await row.click()
    await agent.bringToFront()
    await expect(page.locator('.seen-note')).toHaveCount(1)
    await expect(row.locator('.unread-badge')).toHaveCount(0)
    await expect(row.locator('.reply-wait')).toBeVisible()
    await agent.getByLabel('Your reply', { exact: true }).fill('I am checking your installation now.')
    await expect(page.locator('.typing-indicator')).toContainText('is typing')
    await page.screenshot({ path: '.local/customer-typing.png', fullPage: true })
    await agent.getByRole('button', { name: 'Internal note', exact: true }).click()
    await agent.getByLabel('Private note').fill('PRIVATE_ACTIVITY_NOTE: checking a provider case.')
    await expect(page.locator('.typing-indicator')).toHaveCount(0)
    await agent.getByRole('button', { name: 'Add note', exact: true }).click()
    await expect(row.locator('.reply-wait')).toBeVisible()
    await expect(page.locator('.messages')).not.toContainText('PRIVATE_ACTIVITY_NOTE')
    await agent.getByRole('button', { name: 'Public reply', exact: true }).click()
    await agent.getByRole('button', { name: 'Send reply' }).click()
    await expect(page.locator('.messages')).toContainText('I am checking your installation now.')
    await expect(row.locator('.reply-wait')).toHaveCount(0)
    // Merely loading the inbox does not acknowledge an unopened conversation.
    await agent.reload()
    await page.getByLabel('Your reply', { exact: true }).fill('I restarted it and still need help.')
    await page.getByRole('button', { name: 'Send reply' }).click()
    await expect(row.locator('.unread-badge')).toHaveText('1')
    await expect(row.locator('.reply-wait')).toBeVisible()
    await row.click()
    await agent.bringToFront()
    await expect(page.locator('.seen-note')).toHaveCount(2)
    await expect(row.locator('.unread-badge')).toHaveCount(0)
    await agent.screenshot({ path: '.local/agent-activity-dark.png', fullPage: true })
  } finally {
    if (id) await staff.request.patch(`/api/tickets/${id}`, { data: { status: 'CLOSED' }, headers })
    await setCapacity(staff.request, capacity)
    await staff.request.patch('/api/agents/me/availability', { data: { availability: 'OFFLINE' }, headers })
    await staff.request.post('/api/auth/logout', { headers })
    await customer.close(); await staff.close()
  }
})

test('development server does not serve local secrets or backend files', async ({ request }) => {
  for (const path of ['/.env', '/backend/.env', '/.local/agent-credentials.txt', '/.git/config']) {
    const response = await request.get(path)
    expect([403, 404]).toContain(response.status())
    expect(await response.text()).not.toContain('DATABASE_URL=')
  }
})
