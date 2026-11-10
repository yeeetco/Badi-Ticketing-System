export type Availability = 'ONLINE' | 'BREAK' | 'OFFLINE'
export type Agent = { id: number; name: string; email: string; tier: string; is_available: boolean; max_active_chats: number; role: 'AGENT' | 'TEAM_LEAD' | 'ADMIN'; is_active: boolean; area: string; availability: Availability }
export type RoutingState = {
  waiting_count: number
  agents: { id: number; name: string; tier: string; is_available: boolean; signed_in: boolean; active_chats: number; capacity: number; area: string; availability: Availability }[]
}

export type Ticket = {
  id: number
  number: string
  customer_email: string
  subject: string
  category: string
  status: string
  priority: string
  assigned_agent_id: number | null
  created_at: string
  updated_at: string
  order_id: string | null
  area: string
  emergency_closed: boolean
  unread_count: number
  awaiting_reply_since: string | null
}

export type Attachment = { id: number; filename: string; content_type: string; size: number; available: boolean }

export type Message = {
  id: number
  attachments: Attachment[]
  sender_role: 'CUSTOMER' | 'AGENT'
  sender_name: string
  kind: 'PUBLIC' | 'INTERNAL'
  body: string
  created_at: string
  seen_at: string | null
}

export type AuditEvent = {
  id: number
  actor: string
  field: string
  old_value: string | null
  new_value: string | null
  created_at: string
  reason: string | null
}

export type TicketDetail = Ticket & { description: string; messages: Message[]; events: AuditEvent[] }
export type CustomerTicket = Pick<Ticket, 'id' | 'number' | 'subject' | 'status' | 'category' | 'priority' | 'created_at' | 'customer_email' | 'order_id'> & {
  messages: Message[]
  routing_state: 'WAITING' | 'ASSIGNED' | 'COMPLETE'
  queue_position: number | null
  customer_ended_at: string | null
  agent_is_typing: boolean
  assigned_agent_name: string | null
}
export type CreatedTicket = { ticket: CustomerTicket; access_code: string }
export type FaqRevision = {
  revision: string; reviewed_on: string; source_url: string;
  items: { id: string; category: string; question: string; answer: string }[]
}

export const statuses = ['OPEN', 'IN_PROGRESS', 'WAITING_FOR_CUSTOMER', 'WAITING_FOR_PROVIDER', 'RESOLVED', 'CLOSED']
export const priorities = ['LOW', 'MEDIUM', 'HIGH', 'URGENT']
export const categories = ['INSTALLATION', 'ACTIVATION', 'CONNECTIVITY', 'ORDER', 'TOPUP', 'REFUND', 'OTHER']

export const label = (value: string) => value.toLowerCase().replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
export const timestamp = (value: string) => new Date(value).toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// API connection lives here. React never connects directly to PostgreSQL.
// The browser sends the HttpOnly session cookie automatically on this origin.
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: 'same-origin',
      headers: { ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options?.headers },
    })
  } catch {
    throw new ApiError('Cannot reach the API. Check that Vite and FastAPI are running.', 0)
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const message = typeof body?.detail === 'string' ? body.detail
      : Array.isArray(body?.detail) ? body.detail.map((issue: { msg: string }) => issue.msg).join('. ')
      : 'Request failed. Check that FastAPI and PostgreSQL are running.'
    throw new ApiError(message, response.status)
  }

  return response.status === 204 ? undefined as T : response.json()
}
