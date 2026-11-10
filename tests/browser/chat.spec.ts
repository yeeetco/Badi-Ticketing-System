import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

test('customer and agent exchange live replies; notes stay private and reconnect recovers history', async ({ browser }) => {
  const credentials = readFileSync('.local/agent-credentials.txt', 'utf8')
  const email = credentials.match(/Email: (.+)/)![1].trim()
  const password = credentials.match(/Password: (.+)/)![1].trim()
  const customerContext = await browser.newContext()
  const agentContext = await browser.newContext({ viewport: { width: 1600, height: 1050 } })
  const customer = await customerContext.newPage()
  const agent = await agentContext.newPage()
  const runtimeErrors: string[] = []
  customer.on('pageerror', (error) => runtimeErrors.push(error.message))
  agent.on('pageerror', (error) => runtimeErrors.push(error.message))
  let ticketId: number | undefined
  let originalCapacity = 5

  try {
    await customer.goto('http://127.0.0.1:5173/')
    await expect(customer.getByRole('navigation')).not.toContainText('Agent')
    await customer.getByRole('main').getByRole('link', { name: 'Contact Support', exact: true }).click()
    await customer.getByRole('button', { name: /Start a chat/ }).click()
    await customer.getByLabel('Your email').fill('browser-test@example.com')
    await customer.getByRole('button', { name: 'Send answer', exact: true }).click()
    await customer.getByRole('button', { name: /Connectivity/ }).click()
    const subject = `[Browser test] Connection help ${Date.now()}`
    await customer.getByLabel('Short description of the issue').fill(`${subject}. My eSIM connects but I cannot access the internet.`)
    await customer.getByRole('button', { name: 'Send answer', exact: true }).click()
    await customer.getByLabel('Order ID (optional)').fill('ORD-10293')
    await customer.getByRole('button', { name: 'Send answer', exact: true }).click()
    await expect(customer.locator('.intake-review')).toContainText(subject)
    await expect(customer.locator('.intake-review h3')).toBeInViewport()
    await expect(customer.getByRole('combobox')).toHaveCount(0)
    await customer.screenshot({ path: '.local/intake-review-desktop.png', fullPage: true })
    await customer.setViewportSize({ width: 390, height: 844 })
    await expect(customer.locator('.intake-review h3')).toBeInViewport()
    await expect.poll(() => customer.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await customer.screenshot({ path: '.local/intake-review-mobile.png', fullPage: true })
    await customer.setViewportSize({ width: 1600, height: 1050 })
    const [createdResponse] = await Promise.all([
      customer.waitForResponse((response) => response.url().endsWith('/api/customer/tickets') && response.request().method() === 'POST'),
      customer.getByRole('button', { name: 'Confirm and start chat', exact: true }).click(),
    ])
    const created = await createdResponse.json()
    ticketId = created.ticket.id
    await expect(customer.locator('.customer-chat .live-indicator')).toHaveText('Live updates')

    await agent.goto('http://127.0.0.1:5173/#/agent')
    await agent.getByLabel('Email', { exact: true }).fill(email)
    await agent.getByLabel('Password', { exact: true }).fill(password)
    await agent.getByRole('button', { name: 'Sign in', exact: true }).click()
    originalCapacity = Number(await agent.getByLabel('Chat capacity', { exact: true }).inputValue())
    await agent.getByLabel('Chat capacity', { exact: true }).selectOption('20')
    await agent.getByRole('button').filter({ hasText: subject }).click()
    await expect(agent.locator('.agent-chat .messages')).toContainText('My eSIM connects')

    await customer.getByLabel('Your reply', { exact: true }).fill('I have restarted my phone twice.')
    await customer.getByRole('button', { name: 'Send reply' }).click()
    await expect(agent.locator('.agent-chat .messages')).toContainText('I have restarted my phone twice.')
    await agent.getByLabel('Your reply', { exact: true }).fill('Please enable data roaming for your Badi eSIM.')
    await agent.getByRole('button', { name: 'Send reply' }).click()
    await expect(customer.locator('.messages')).toContainText('Please enable data roaming')

    await agent.getByRole('button', { name: 'Internal note', exact: true }).click()
    await agent.getByLabel('Private note').fill('PRIVATE_BROWSER_NOTE: upstream escalation context')
    await agent.getByRole('button', { name: 'Public reply', exact: true }).click()
    await expect(agent.getByLabel('Your reply', { exact: true })).toHaveValue('')
    await agent.getByRole('button', { name: 'Internal note', exact: true }).click()
    await expect(agent.getByLabel('Private note')).toHaveValue('PRIVATE_BROWSER_NOTE: upstream escalation context')
    await agent.getByRole('button', { name: 'Add note', exact: true }).click()
    await expect(agent.locator('.internal-message')).toContainText('PRIVATE_BROWSER_NOTE')
    const publicResponse = await customer.request.get(`/api/customer/tickets/${ticketId}`, { timeout: 5000 })
    expect(await publicResponse.text()).not.toContain('PRIVATE_BROWSER_NOTE')
    await expect(customer.locator('.messages')).not.toContainText('PRIVATE_BROWSER_NOTE')

    await agent.locator('.ticket-details').getByLabel('Status', { exact: true }).selectOption('WAITING_FOR_CUSTOMER')
    await expect(customer.locator('.customer-chat .status-pill')).toHaveText('Waiting for customer')
    await agent.locator('.ticket-details').getByLabel('Priority', { exact: true }).selectOption('URGENT')
    await expect(customer.locator('.routing-banner')).toContainText('Assigned to Badi Support')
    await expect(agent.locator('.audit-history')).toContainText('Assignment: Unassigned')
    await expect(agent.locator('.audit-history')).toContainText('Priority: Medium → Urgent')
    await agent.locator('.ticket-details').getByLabel('Assigned to', { exact: true }).selectOption({ label: 'Mia Support' })
    await expect(agent.locator('.audit-history')).toContainText('Badi Support → Mia Support')

    // An unsent public draft belongs to this ticket, even when switching cases.
    await agent.getByRole('button', { name: 'Public reply', exact: true }).click()
    await agent.getByLabel('Your reply', { exact: true }).fill('A draft kept for this case only.')
    await agent.getByRole('button').filter({ hasText: 'eSIM QR code will not scan' }).click()
    await expect(agent.getByLabel('Your reply', { exact: true })).toHaveValue('')
    await agent.getByRole('button').filter({ hasText: subject }).click()
    await expect(agent.getByLabel('Your reply', { exact: true })).toHaveValue('A draft kept for this case only.')
    await agent.getByLabel('Your reply', { exact: true }).fill('')

    // A failed network request preserves the unsent draft.
    await customerContext.route('**/api/customer/tickets/*/messages', (route) => route.abort('failed'))
    await customer.getByLabel('Your reply', { exact: true }).fill('Keeping this draft after a failed send.')
    await customer.getByRole('button', { name: 'Send reply' }).click()
    await expect(customer.getByRole('alert')).toContainText('Cannot reach the API')
    await expect(customer.getByLabel('Your reply', { exact: true })).toHaveValue('Keeping this draft after a failed send.')
    await customerContext.unroute('**/api/customer/tickets/*/messages')
    await customer.getByRole('button', { name: 'Send reply' }).click()
    await expect(agent.locator('.messages')).toContainText('Keeping this draft after a failed send.')
    await expect(customer.locator('.customer-chat .status-pill')).toHaveText('Waiting for customer')

    // While the customer is offline, an agent's reply is still stored.
    await customerContext.setOffline(true)
    await agent.getByRole('button', { name: 'Public reply', exact: true }).click()
    await agent.getByLabel('Your reply', { exact: true }).fill('This reply was sent while your browser was offline.')
    await agent.getByRole('button', { name: 'Send reply' }).click()
    await expect(agent.locator('.messages')).toContainText('This reply was sent while your browser was offline.')
    await customerContext.setOffline(false)
    await expect(customer.locator('.messages')).toContainText('This reply was sent while your browser was offline.')

    await agent.screenshot({ path: '.local/agent-chat-desktop.png', fullPage: true })
    await customer.setViewportSize({ width: 390, height: 844 })
    await expect.poll(() => customer.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await customer.screenshot({ path: '.local/customer-chat-mobile.png', fullPage: true })
    await agent.setViewportSize({ width: 390, height: 844 })
    await expect.poll(() => agent.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await agent.screenshot({ path: '.local/agent-chat-mobile.png', fullPage: true })

    await agent.getByLabel('Search tickets').fill('no-matching-ticket-12345')
    await expect(agent.getByRole('heading', { name: 'No matching tickets' })).toBeVisible()
    await agent.getByRole('button', { name: 'Reset', exact: true }).click()
    await expect(agent.getByRole('button').filter({ hasText: subject })).toBeVisible()

    await customer.getByRole('button', { name: /Leave this ticket/ }).click()
    await customer.getByRole('button', { name: /Return to a ticket/ }).click()
    await customer.getByLabel('Ticket number').fill(created.ticket.number)
    await customer.getByLabel('Private access code', { exact: true }).fill(created.access_code)
    await customer.getByRole('button', { name: 'Open conversation' }).click()
    await expect(customer.locator('.messages')).toContainText('This reply was sent while your browser was offline.')
    await customer.reload()
    await expect(customer.locator('.messages')).toContainText('Please enable data roaming')

    await agent.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(agent.getByRole('heading', { name: 'Agent sign-in' })).toBeVisible()
    expect((await agent.request.get('/api/tickets')).status()).toBe(401)
    expect(runtimeErrors).toEqual([])
  } finally {
    // Keep test cases distinguishable and closed; never clear unrelated data.
    if (ticketId) {
      await agent.request.post('/api/auth/login', { timeout: 5000, data: { email, password }, headers: { Origin: 'http://127.0.0.1:5173' } })
      await agent.request.patch(`/api/tickets/${ticketId}`, { timeout: 5000, data: { status: 'CLOSED' }, headers: { Origin: 'http://127.0.0.1:5173' } })
      await agent.request.patch('/api/agents/me/availability', { timeout: 5000, data: { is_available: false, max_active_chats: originalCapacity }, headers: { Origin: 'http://127.0.0.1:5173' } })
      await agent.request.post('/api/auth/logout', { headers: { Origin: 'http://127.0.0.1:5173' } })
    }
    await customerContext.close()
    await agentContext.close()
  }
})

test('the background queue worker assigns a waiting case when capacity is freed', async ({ browser }) => {
  const password = readFileSync('.local/agent-credentials.txt', 'utf8').match(/Password: (.+)/)![1].trim()
  const context = await browser.newContext()
  const page = await context.newPage()
  const headers = { Origin: 'http://127.0.0.1:5173' }
  const ownedTickets: number[] = []
  let originalCapacity = 5

  try {
    const login = await context.request.post('/api/auth/login', { data: { email: 'mia@example.com', password }, headers })
    expect(login.status()).toBe(200)
    const profile = await login.json()
    originalCapacity = profile.max_active_chats
    const pool = await (await context.request.get('/api/routing')).json()
    const self = pool.agents.find((person: { id: number }) => person.id === profile.id)
    expect(self.active_chats).toBeLessThan(20)
    await context.request.patch('/api/agents/me/availability', { data: { is_available: true, max_active_chats: self.active_chats + 1 }, headers })

    async function arrive(description: string) {
      const response = await context.request.post('/api/customer/tickets', { data: { customer_email: 'browser-test@example.com', category: 'CONNECTIVITY', description }, headers })
      expect(response.status()).toBe(201)
      const ticket = (await response.json()).ticket
      ownedTickets.push(ticket.id)
      return ticket
    }
    const first = await arrive(`[Browser test] Queue capacity occupied ${Date.now()}. The connection needs help.`)
    expect(first.routing_state).toBe('ASSIGNED')
    const second = await arrive(`[Browser test] Waiting for capacity ${Date.now()}. The connection needs help.`)
    expect(second.routing_state).toBe('WAITING')

    await page.goto('http://127.0.0.1:5173/#/support')
    await expect(page.locator('.routing-banner')).toContainText('Waiting for an agent')
    // PATCH frees capacity but does not call dispatch itself. The lifespan
    // worker must find this SQL waiting row on its next two-second sweep.
    await context.request.patch(`/api/tickets/${first.id}`, { data: { status: 'CLOSED' }, headers })
    await expect(page.locator('.routing-banner')).toContainText('Assigned to Mia Support')
    const detail = await (await context.request.get(`/api/tickets/${second.id}`)).json()
    expect(detail.assigned_agent_id).toBe(profile.id)
    expect(detail.events.some((event: { actor: string }) => event.actor === 'T1 queue router')).toBe(true)
    await page.screenshot({ path: '.local/routed-customer-chat.png', fullPage: true })
  } finally {
    for (const id of ownedTickets) await context.request.patch(`/api/tickets/${id}`, { data: { status: 'CLOSED' }, headers })
    await context.request.patch('/api/agents/me/availability', { data: { is_available: false, max_active_chats: originalCapacity }, headers })
    await context.request.post('/api/auth/logout', { headers })
    await context.close()
  }
})

test('localhost chat supports typed answers and inline quick replies without a step header', async ({ page }) => {
  await page.goto('http://localhost:5173/#/support')
  await page.getByRole('button', { name: /Start a chat/ }).click()
  await expect(page.getByRole('heading', { name: 'Chat with an Agent', exact: true })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Chat setup steps' })).toHaveCount(0)
  await expect(page.locator('.intake-bot')).toHaveCount(0)
  await page.getByLabel('Your email').fill('browser-test@example.com')
  await page.getByRole('button', { name: 'Send answer' }).click()
  await expect(page.locator('.assistant-turn').getByRole('group', { name: 'Pick a category' })).toBeVisible()
  await page.screenshot({ path: '.local/chat-inline-options-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  await page.screenshot({ path: '.local/chat-inline-options-mobile.png', fullPage: true })

  // Manual category aliases and clicked issue suggestions use the same flow.
  await page.getByLabel('Category', { exact: true }).fill('internet')
  await page.getByRole('button', { name: 'Send answer' }).click()
  await page.getByRole('button', { name: 'My eSIM is installed but I have no internet.', exact: true }).click()
  await expect(page.getByLabel('Order ID (optional)')).toBeVisible()
  await page.getByRole('button', { name: 'Skip for now' }).click()
  await expect(page.locator('.intake-review h3')).toHaveText('My eSIM is installed but I have no internet.')
  await page.getByLabel('Your reply', { exact: true }).fill('edit')
  await page.getByRole('button', { name: 'Send answer' }).click()
  await expect(page.getByLabel('Your email')).toHaveValue('browser-test@example.com')
  await page.getByRole('button', { name: 'Cancel chat setup' }).click()
  await expect(page.getByRole('button', { name: /Start a chat/ })).toBeVisible()
})

