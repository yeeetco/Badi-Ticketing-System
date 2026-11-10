from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select

from .config import settings
from .conversations import (CUSTOMER_COOKIE, add_message, agent_view, customer_ticket,
                            customer_view, new_ticket, queue_view, record_event, ticket_or_404)
from .live import live_response
from .models import Agent, Ticket
from .schemas import (AgentCreated, AgentRead, AvailabilityUpdate, Category, CustomerAccess, CustomerCreated, CustomerIntake,
                      CustomerMessageCreate, CustomerTicket, MessageCreate, MessageRead,
                      Priority, Status, SummaryRequest, TicketCreate, TicketDetail, TicketPatch, TicketRead)
from .security import COOKIE_NAME, CurrentAgent, Db, agent_from_token, token_digest
from .intake import summarize_issue
from .routing import dispatch_waiting, lock_routing, routing_view

router = APIRouter()


def queue_filters(status: Status | None = None, priority: Priority | None = None,
                  category: Category | None = None, assigned_agent_id: int | None = Query(default=None, gt=0),
                  unassigned: bool = False, q: str = Query(default='', max_length=200),
                  limit: int = Query(default=100, ge=1, le=100)):
    return dict(status=status, priority=priority, category=category,
                assigned_agent_id=assigned_agent_id, unassigned=unassigned, q=q.strip(), limit=limit)


Filters = Annotated[dict, Depends(queue_filters)]


@router.get('/agents', response_model=list[AgentRead])
def agents(db: Db, agent: CurrentAgent):
    return db.scalars(select(Agent).order_by(Agent.name)).all()


@router.patch('/agents/me/availability', response_model=AgentRead)
def update_availability(body: AvailabilityUpdate, db: Db, agent: CurrentAgent):
    lock_routing(db)
    agent.is_available = body.is_available
    agent.max_active_chats = body.max_active_chats
    db.flush()
    dispatch_waiting(db)
    db.commit()
    return agent


@router.get('/routing')
def get_routing(db: Db, agent: CurrentAgent):
    return routing_view(db)


@router.get('/routing/live')
def live_routing(request: Request, db: Db):
    def load():
        agent_from_token(db, request.cookies.get(COOKIE_NAME))
        return routing_view(db)
    return live_response(request, db, load)


@router.get('/tickets', response_model=list[TicketRead])
def tickets(db: Db, agent: CurrentAgent, filters: Filters):
    return queue_view(db, **filters)


@router.get('/tickets/live')
def live_queue(request: Request, db: Db, filters: Filters):
    def load():
        agent_from_token(db, request.cookies.get(COOKIE_NAME))
        return queue_view(db, **filters)
    return live_response(request, db, load)


@router.post('/tickets', response_model=AgentCreated, status_code=201)
def create_agent_ticket(body: TicketCreate, db: Db, agent: CurrentAgent):
    ticket, code = new_ticket(db, body, agent)
    return AgentCreated(**TicketRead.model_validate(ticket).model_dump(), access_code=code)


@router.get('/tickets/{ticket_id}', response_model=TicketDetail)
def get_ticket(ticket_id: int, db: Db, agent: CurrentAgent):
    return agent_view(db, ticket_or_404(db, ticket_id))


@router.get('/tickets/{ticket_id}/live')
def live_agent_ticket(ticket_id: int, request: Request, db: Db):
    def load():
        agent_from_token(db, request.cookies.get(COOKIE_NAME))
        return agent_view(db, ticket_or_404(db, ticket_id))
    return live_response(request, db, load)


@router.patch('/tickets/{ticket_id}', response_model=TicketDetail)
def update_ticket(ticket_id: int, body: TicketPatch, db: Db, agent: CurrentAgent):
    lock_routing(db)
    changes = body.model_dump(exclude_unset=True)
    if any(changes.get(key) is None for key in ('status', 'priority') if key in changes):
        raise HTTPException(422, 'Status and priority cannot be null.')
    if 'assigned_agent_id' in changes and changes['assigned_agent_id'] is not None:
        if db.get(Agent, changes['assigned_agent_id']) is None:
            raise HTTPException(422, 'Choose an existing support agent.')

    # Lock before comparing fields, so concurrent changes get an accurate audit.
    ticket = ticket_or_404(db, ticket_id, lock=True)
    for field, value in changes.items():
        before = getattr(ticket, field)
        if before != value:
            record_event(db, ticket, agent.name, field, before, value)
            setattr(ticket, field, value)
            ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    return agent_view(db, ticket)


@router.post('/tickets/{ticket_id}/messages', response_model=MessageRead, status_code=201)
def agent_message(ticket_id: int, body: MessageCreate, db: Db, agent: CurrentAgent):
    return add_message(db, ticket_or_404(db, ticket_id, lock=True), body.body, body.kind, agent.name, 'AGENT')


def set_customer_cookie(response: Response, token: str):
    response.set_cookie(CUSTOMER_COOKIE, token, httponly=True, secure=settings.cookie_secure,
                        samesite='strict', max_age=30 * 24 * 60 * 60)


@router.post('/customer/tickets', response_model=CustomerCreated, status_code=201)
def create_customer_ticket(body: CustomerIntake, response: Response, db: Db):
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
def access_ticket(body: CustomerAccess, response: Response, db: Db):
    ticket = db.scalar(select(Ticket).where(Ticket.customer_access_hash == token_digest(body.access_code)))
    if ticket is None or ticket.number != body.ticket_number:
        raise HTTPException(401, 'Ticket number or private access code is incorrect.')
    set_customer_cookie(response, body.access_code)
    return customer_view(db, ticket)


@router.get('/customer/session', response_model=CustomerTicket)
def customer_session(request: Request, db: Db):
    return customer_view(db, customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE)))


@router.post('/customer/logout', status_code=204)
def close_customer_session(response: Response):
    response.delete_cookie(CUSTOMER_COOKIE, httponly=True, secure=settings.cookie_secure, samesite='strict')


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
    ticket = customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id, lock=True)
    return add_message(db, ticket, body.body, 'PUBLIC', ticket.customer_email, 'CUSTOMER')
