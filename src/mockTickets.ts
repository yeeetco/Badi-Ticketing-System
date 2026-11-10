type Ticket = {
  id: string
  subject: string
  status: 'Open' | 'In progress' | 'Resolved'
  priority: 'Low' | 'Medium' | 'High'
}

export const mockTickets: Ticket[] = [
  {
    id: 'BAD-101',
    subject: 'eSIM QR code will not scan',
    status: 'Open',
    priority: 'High',
  },
  {
    id: 'BAD-102',
    subject: 'Mobile data stopped working after arrival',
    status: 'In progress',
    priority: 'High',
  },
  {
    id: 'BAD-103',
    subject: 'Question about remaining data balance',
    status: 'Resolved',
    priority: 'Low',
  },
]