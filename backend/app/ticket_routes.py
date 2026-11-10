from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, update

from .config import settings
from .conversations import (CUSTOMER_COOKIE, add_message, agent_view, customer_ticket,
                            customer_view, new_ticket, queue_view, record_event, ticket_or_404, status_note)
from .live import live_response
from .models import Agent, Ticket, TicketMessage, TicketRead as ReadState, TypingPresence
from .schemas import (AgentRead, AvailabilityUpdate, Category, CustomerAccess, CustomerCreated, CustomerIntake,
                      CustomerMessageCreate, CustomerTicket, MessageCreate, MessageRead,
                      Priority, Status, SummaryRequest, TicketCreate, TicketDetail, TicketPatch, TicketRead, EmergencyClose,
                      TransferRequest, ReturnToQueueRequest, ReadReceipt, TypingUpdate)
from .security import COOKIE_NAME, CurrentSupport, CurrentOperator, CurrentLeader, Db, agent_from_token, support_staff, token_digest
from .intake import summarize_issue
from .routing import (ACTIVE_STATUSES, active_loads, dispatch_waiting, lock_routing, routing_view,
                      return_to_pool, signed_in_agent_ids)
from .rate_limits import consume, client_key

router = APIRouter()


def queue_filters(status: Status | None = None, priority: Priority | None = None,
                  category: Category | None = None, assigned_agent_id: int | None = Query(default=None, gt=0),
                  unassigned: bool = False, q: str = Query(default='', max_length=200),
                  limit: int = Query(default=100, ge=1, le=100)):
    return dict(status=status, priority=priority, category=category,
                assigned_agent_id=assigned_agent_id, unassigned=unassigned, q=q.strip(), limit=limit)


Filters = Annotated[dict, Depends(queue_filters)]


@router.get('/agents', response_model=list[AgentRead])
def agents(db: Db, agent: CurrentSupport):
    return db.scalars(select(Agent).where(Agent.area == agent.area, Agent.role == 'AGENT').order_by(Agent.name)).all()


@router.get('/agents/live')
def live_agents(request: Request, db: Db):
    def load():
        staff = support_staff(agent_from_token(db, request.cookies.get(COOKIE_NAME)))
        # Explicit public staff fields: never serialize password hashes/sessions.
        return [AgentRead.model_validate(person) for person in agents(db, staff)]
    return live_response(request, db, load)


@router.patch('/agents/me/availability', response_model=AgentRead)
def update_availability(body: AvailabilityUpdate, db: Db, agent: CurrentOperator):
    if body.max_active_chats is not None:
        raise HTTPException(403, 'Chat capacity is managed by an administrator from the staff profile.')
    lock_routing(db)
    state = body.availability
    if state is None and body.is_available is not None:
        state = 'ONLINE' if body.is_available else 'BREAK'
    if state:
        agent.availability = state
        agent.is_available = state == 'ONLINE'
    if agent.availability == 'OFFLINE':
        return_to_pool(db, agent.id, 'Agent selected Offline.')
    db.flush()
    dispatch_waiting(db)
    db.commit()
    return agent


@router.get('/routing')
def get_routing(db: Db, agent: CurrentSupport):
    return routing_view(db, agent.area)


@router.get('/routing/live')
def live_routing(request: Request, db: Db):
    def load():
        staff = support_staff(agent_from_token(db, request.cookies.get(COOKIE_NAME)))
        return routing_view(db, staff.area)
    return live_response(request, db, load)


@router.get('/tickets', response_model=list[TicketRead])
def tickets(db: Db, agent: CurrentSupport, filters: Filters):
    return queue_view(db, **filters, area=agent.area, viewer_id=agent.id if agent.role == 'AGENT' else None)


@router.get('/tickets/live')
def live_queue(request: Request, db: Db, filters: Filters):
    def load():
        staff = support_staff(agent_from_token(db, request.cookies.get(COOKIE_NAME)))
        return queue_view(db, **filters, area=staff.area, viewer_id=staff.id if staff.role == 'AGENT' else None)
    return live_response(request, db, load)


@router.post('/tickets', deprecated=True)
def create_agent_ticket(agent: CurrentOperator):
    # Removing a button does not remove permission. Retire the old write path.
    raise HTTPException(403, 'Support requests must be opened by the customer through the support assistant.')


@router.get('/tickets/{ticket_id}', response_model=TicketDetail)
def get_ticket(ticket_id: int, db: Db, agent: CurrentSupport):
    return agent_view(db, ticket_or_404(db, ticket_id, staff=agent))


@router.get('/tickets/{ticket_id}/live')
def live_agent_ticket(ticket_id: int, request: Request, db: Db):
    def load():
        staff = support_staff(agent_from_token(db, request.cookies.get(COOKIE_NAME)))
        return agent_view(db, ticket_or_404(db, ticket_id, staff=staff))
    return live_response(request, db, load)


@router.patch('/tickets/{ticket_id}', response_model=TicketDetail)
def update_ticket(ticket_id: int, body: TicketPatch, db: Db, agent: CurrentOperator):
    lock_routing(db)
    changes = body.model_dump(exclude_unset=True)
    if any(changes.get(key) is None for key in ('status', 'priority') if key in changes):
        raise HTTPException(422, 'Status and priority cannot be null.')
    # Lock before comparing fields, so concurrent changes get an accurate audit.
    ticket = ticket_or_404(db, ticket_id, lock=True, staff=agent)
    if 'assigned_agent_id' in changes:
        raise HTTPException(422, 'Use Transfer conversation or Return to queue to change the handler.')
    if ticket.assigned_agent_id not in (None, agent.id):
        raise HTTPException(409, 'Only the handling agent can change this case. Team leaders can monitor or use emergency closure.')
    if ticket.assigned_agent_id is None and any(key != 'assigned_agent_id' for key in changes):
        raise HTTPException(409, 'This case is waiting in the pool. It must be assigned before workflow changes.')
    if ticket.emergency_closed and changes.get('status', 'CLOSED') != 'CLOSED':
        raise HTTPException(409, 'This case was emergency-closed by a team leader and cannot be reopened here.')
    if ticket.customer_ended_at and changes.get('status', 'CLOSED') != 'CLOSED':
        raise HTTPException(409, 'The customer ended this chat. A new conversation must be started for further help.')
    for field, value in changes.items():
        before = getattr(ticket, field)
        if before != value:
            record_event(db, ticket, agent.name, field, before, value)
            if field == 'status':
                status_note(db, ticket, agent.name, before, value)
            setattr(ticket, field, value)
            ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    return agent_view(db, ticket)


@router.post('/tickets/{ticket_id}/transfer', response_model=TicketDetail)
def transfer_ticket(ticket_id: int, body: TransferRequest, db: Db, agent: CurrentOperator):
    lock_routing(db)
    ticket = ticket_or_404(db, ticket_id, lock=True, staff=agent)
    require_active_handler(ticket, agent)
    target = db.get(Agent, body.agent_id)
    if not target or target.id == agent.id or target.role != 'AGENT' or target.area != agent.area:
        raise HTTPException(422, 'Choose another support agent in your area.')
    if target.availability != 'ONLINE' or not target.is_available or target.id not in signed_in_agent_ids(db):
        raise HTTPException(409, 'The receiving agent must be online.')
    if active_loads(db).get(target.id, 0) >= target.max_active_chats:
        raise HTTPException(409, 'The receiving agent is at capacity.')
    record_event(db, ticket, agent.name, 'assigned_agent_id', agent.id, target.id, reason='Conversation transferred by its handler.')
    ticket.assigned_agent_id = target.id
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()
    dispatch_waiting(db)
    db.commit()
    return agent_view(db, ticket)


def require_active_handler(ticket: Ticket, agent: Agent):
    if ticket.assigned_agent_id != agent.id:
        raise HTTPException(409, 'Only the current handler can route this conversation.')
    if ticket.status not in ACTIVE_STATUSES or ticket.emergency_closed:
        raise HTTPException(409, 'Only active conversations can be transferred or returned.')


@router.post('/tickets/{ticket_id}/return-to-queue', response_model=TicketDetail)
def return_ticket(ticket_id: int, body: ReturnToQueueRequest, db: Db, agent: CurrentOperator):
    lock_routing(db)
    ticket = ticket_or_404(db, ticket_id, lock=True, staff=agent)
    require_active_handler(ticket, agent)
    now = datetime.now(timezone.utc)
    ticket.assigned_agent_id = None
    ticket.requeue_agent_id = agent.id
    ticket.requeue_until = now + timedelta(minutes=5)
    ticket.updated_at = now
    record_event(db, ticket, agent.name, 'assigned_agent_id', agent.id, None,
                 reason=f'Returned to queue. Previous handler excluded until {ticket.requeue_until.isoformat()}.')
    db.flush()
    dispatch_waiting(db)
    db.commit()
    return agent_view(db, ticket)


@router.post('/tickets/{ticket_id}/messages', response_model=MessageRead, status_code=201)
def agent_message(ticket_id: int, body: MessageCreate, db: Db, agent: CurrentOperator):
    consume(db, 'agent-message', str(agent.id), 120, 60)
    ticket = ticket_or_404(db, ticket_id, lock=True, staff=agent)
    if ticket.assigned_agent_id != agent.id:
        raise HTTPException(409, 'This case is parked with another agent or in the pool. It must be assigned to you before you reply.')
    if ticket.emergency_closed:
        raise HTTPException(409, 'This conversation was emergency-closed and is read-only.')
    return add_message(db, ticket, body.body, body.kind, agent.name, 'AGENT')


@router.post('/tickets/{ticket_id}/read')
def mark_read(ticket_id: int, body: ReadReceipt, db: Db, agent: CurrentOperator):
    consume(db, 'agent-activity', str(agent.id), 180, 60)
    ticket = ticket_or_404(db, ticket_id, lock=True, staff=agent)
    if ticket.assigned_agent_id != agent.id:
        raise HTTPException(409, 'Only the current handler can acknowledge customer messages.')
    message = db.get(TicketMessage, body.message_id)
    if not message or message.ticket_id != ticket.id or message.sender_role != 'CUSTOMER' or message.kind != 'PUBLIC':
        raise HTTPException(422, 'Choose a public customer message in this conversation.')
    now = datetime.now(timezone.utc)
    state = db.get(ReadState, (ticket.id, agent.id))
    if state is None:
        state = ReadState(ticket_id=ticket.id, agent_id=agent.id, last_message_id=0, seen_at=now)
        db.add(state)
    state.last_message_id = max(state.last_message_id, message.id)
    state.seen_at = now
    db.execute(update(TicketMessage).where(TicketMessage.ticket_id == ticket.id,
        TicketMessage.id <= message.id, TicketMessage.sender_role == 'CUSTOMER',
        TicketMessage.kind == 'PUBLIC', TicketMessage.seen_at.is_(None)).values(seen_at=now))
    db.commit()
    return {'last_message_id': state.last_message_id}


@router.post('/tickets/{ticket_id}/typing', status_code=204)
def update_typing(ticket_id: int, body: TypingUpdate, db: Db, agent: CurrentOperator):
    consume(db, 'agent-activity', str(agent.id), 180, 60)
    ticket = ticket_or_404(db, ticket_id, lock=True, staff=agent)
    require_active_handler(ticket, agent)
    now = datetime.now(timezone.utc)
    presence = db.get(TypingPresence, (ticket.id, agent.id))
    if presence is None:
        presence = TypingPresence(ticket_id=ticket.id, agent_id=agent.id, expires_at=now)
        db.add(presence)
    presence.expires_at = now + timedelta(seconds=6) if body.is_typing and body.visibility == 'PUBLIC' else now
    db.commit()


@router.post('/tickets/{ticket_id}/emergency-close', response_model=TicketDetail)
def emergency_close(ticket_id: int, body: EmergencyClose, db: Db, leader: CurrentLeader):
    lock_routing(db)
    ticket = ticket_or_404(db, ticket_id, lock=True, staff=leader)
    if ticket.status == 'CLOSED':
        raise HTTPException(409, 'This case is already closed.')
    record_event(db, ticket, leader.name, 'status', ticket.status, 'CLOSED', reason=f'Emergency closure: {body.reason}')
    status_note(db, ticket, leader.name, ticket.status, 'CLOSED', reason=f'Emergency closure: {body.reason}')
    ticket.status = 'CLOSED'
    ticket.emergency_closed = True
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    return agent_view(db, ticket)


def set_customer_cookie(response: Response, token: str):
    response.set_cookie(CUSTOMER_COOKIE, token, httponly=True, secure=settings.cookie_secure,
                        samesite='strict', max_age=30 * 24 * 60 * 60)


@router.post('/customer/tickets', response_model=CustomerCreated, status_code=201)
def create_customer_ticket(body: CustomerIntake, request: Request, response: Response, db: Db):
    consume(db, 'customer-create', client_key(request), 15 if settings.environment == 'production' else 60, 600)
    # Generate authoritative metadata here; the browser cannot set workflow
    # fields or override the summary, even by sending a forged HTTP request.
    creation = TicketCreate(**body.model_dump(), subject=summarize_issue(body.description, body.category), priority='MEDIUM')
    ticket, code = new_ticket(db, creation)
    set_customer_cookie(response, code)
    return CustomerCreated(ticket=customer_view(db, ticket), access_code=code)


@router.post('/customer/intake/summary')
def preview_summary(body: SummaryRequest):
    return {'subject': summarize_issue(body.description, body.category)}


@router.post('/customer/access', response_model=CustomerTicket)
def access_ticket(body: CustomerAccess, request: Request, response: Response, db: Db):
    consume(db, 'customer-recovery', client_key(request), 30, 300)
    ticket = db.scalar(select(Ticket).where(Ticket.customer_access_hash == token_digest(body.access_code)))
    if ticket is None or (body.ticket_number is not None and ticket.number != body.ticket_number):
        raise HTTPException(401, 'Ticket number or private access code is incorrect.')
    set_customer_cookie(response, body.access_code)
    return customer_view(db, ticket)


@router.get('/customer/session', response_model=CustomerTicket)
def customer_session(request: Request, db: Db):
    return customer_view(db, customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE)))


@router.post('/customer/logout', status_code=204)
def close_customer_session(response: Response):
    response.delete_cookie(CUSTOMER_COOKIE, httponly=True, secure=settings.cookie_secure, samesite='strict')


@router.post('/customer/tickets/{ticket_id}/end', response_model=CustomerTicket)
def end_customer_chat(ticket_id: int, request: Request, db: Db):
    # Explicit End Chat is a deliberate exception to agent-managed workflow.
    # The cookie remains for read-only history until the customer starts over.
    lock_routing(db)
    ticket = customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id, lock=True)
    if ticket.customer_ended_at is None:
        now = datetime.now(timezone.utc)
        if ticket.status != 'CLOSED':
            record_event(db, ticket, ticket.customer_email, 'status', ticket.status, 'CLOSED', reason='Customer ended the chat.')
            status_note(db, ticket, ticket.customer_email, ticket.status, 'CLOSED', reason='Customer ended the chat.')
        ticket.status = 'CLOSED'
        ticket.customer_ended_at = now
        ticket.updated_at = now
        db.add(TicketMessage(ticket_id=ticket.id, sender_role='AGENT', sender_name='System update',
                             kind='PUBLIC', body='You have disconnected. This chat is now closed.', created_at=now))
        db.flush()
        dispatch_waiting(db)
        db.commit()
    return customer_view(db, ticket)


@router.get('/customer/tickets/{ticket_id}', response_model=CustomerTicket)
def customer_detail(ticket_id: int, request: Request, db: Db):
    return customer_view(db, customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id))


@router.get('/customer/tickets/{ticket_id}/live')
def live_customer_ticket(ticket_id: int, request: Request, db: Db):
    def load():
        return customer_view(db, customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id))
    return live_response(request, db, load)


@router.post('/customer/tickets/{ticket_id}/messages', response_model=MessageRead, status_code=201)
def customer_message(ticket_id: int, body: CustomerMessageCreate, request: Request, db: Db):
    customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id)
    consume(db, 'customer-message', request.cookies.get(CUSTOMER_COOKIE, ''), 60, 60)
    ticket = customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id, lock=True)
    if ticket.status in ('RESOLVED', 'CLOSED'):
        raise HTTPException(409, 'This conversation is complete. You can view its history or start a new chat for more help.')
    return add_message(db, ticket, body.body, 'PUBLIC', ticket.customer_email, 'CUSTOMER')
