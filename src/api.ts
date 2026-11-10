export type Agent = { id: number; name: string; email: string }

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
}

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
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    })
  } catch {
    throw new ApiError('Cannot reach the API. Check that Vite and FastAPI are running.', 0)
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const message = typeof body?.detail === 'string' ? body.detail : 'Request failed. Check that FastAPI and PostgreSQL are running.'
    throw new ApiError(message, response.status)
  }

  return response.status === 204 ? undefined as T : response.json()
}
