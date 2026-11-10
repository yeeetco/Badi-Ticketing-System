"""Ticket operations shared by REST responses and the live streams.

Customer reads always use a dedicated response builder. Hiding notes in React
would be insufficient: INTERNAL rows never enter the customer's payload.
"""
from datetime import datetime, timezone
import secrets

from fastapi import HTTPException
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from .models import Agent, Ticket, TicketEvent, TicketMessage
from .schemas import CustomerTicket, EventRead, MessageRead, TicketCreate, TicketDetail, TicketRead
from .security import token_digest
from .routing import ACTIVE_STATUSES, dispatch_waiting, lock_routing

CUSTOMER_COOKIE = 'badi_customer_ticket'


def status_note(db: Session, ticket: Ticket, actor: str, before: str, after: str, reason: str | None = None):
    """Automatic workflow entries are private messages, committed with the change."""
    readable = lambda value: value.replace('_', ' ').capitalize()
    body = f'{actor} changed the status from {readable(before)} to {readable(after)}.'
    if reason:
        body += f' Reason: {reason}'
    db.add(TicketMessage(ticket_id=ticket.id, sender_role='AGENT', sender_name='System update',
                         kind='INTERNAL', body=body, created_at=datetime.now(timezone.utc)))


def ticket_or_404(db: Session, ticket_id: int, lock=False, staff: Agent | None = None) -> Ticket:
    query = select(Ticket).where(Ticket.id == ticket_id)
    if staff:
        query = query.where(Ticket.area == staff.area)
    ticket = db.scalar(query.with_for_update() if lock else query)
    if ticket is None:
        raise HTTPException(404, 'Ticket not found.')
    return ticket


def customer_ticket(db: Session, token: str | None, ticket_id: int | None = None, lock=False) -> Ticket:
    if not token:
        raise HTTPException(401, 'Open your ticket with its number and private access code.')
    query = select(Ticket).where(Ticket.customer_access_hash == token_digest(token))
    if ticket_id is not None:
        query = query.where(Ticket.id == ticket_id)
    ticket = db.scalar(query.with_for_update() if lock else query)
    if ticket is None:
        raise HTTPException(404, 'Ticket access is unavailable. Check your number and access code.')
    return ticket


def customer_view(db: Session, ticket: Ticket) -> CustomerTicket:
    public_messages = db.scalars(select(TicketMessage).where(
        TicketMessage.ticket_id == ticket.id, TicketMessage.kind == 'PUBLIC'
    ).order_by(TicketMessage.id)).all()
    complete = ticket.status in ('RESOLVED', 'CLOSED')
    position = None
    if ticket.assigned_agent_id is None and not complete:
        position = db.scalar(select(func.count(Ticket.id)).where(
            Ticket.assigned_agent_id.is_(None), Ticket.status.in_(ACTIVE_STATUSES), Ticket.area == ticket.area,
            or_(Ticket.created_at < ticket.created_at,
                (Ticket.created_at == ticket.created_at) & (Ticket.id <= ticket.id)),
        ))
    assigned = db.get(Agent, ticket.assigned_agent_id) if ticket.assigned_agent_id else None
    return CustomerTicket(
        id=ticket.id, number=ticket.number, subject=ticket.subject, category=ticket.category,
        priority=ticket.priority, status=ticket.status, created_at=ticket.created_at,
        messages=[MessageRead.model_validate(message) for message in public_messages],
        customer_email=ticket.customer_email, order_id=ticket.order_id,
        routing_state='COMPLETE' if complete else 'ASSIGNED' if assigned else 'WAITING',
        queue_position=position, assigned_agent_name=assigned.name if assigned else None,
    )


def agent_view(db: Session, ticket: Ticket) -> TicketDetail:
    messages = db.scalars(select(TicketMessage).where(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.id)).all()
    events = db.scalars(select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id.desc())).all()
    return TicketDetail(
        **TicketRead.model_validate(ticket).model_dump(), description=ticket.description,
        messages=[MessageRead.model_validate(message) for message in messages],
        events=[EventRead.model_validate(event) for event in events],
    )


def record_event(db: Session, ticket: Ticket, actor: str, field: str, before, after, reason=None):
    db.add(TicketEvent(ticket_id=ticket.id, actor=actor, field=field,
                       old_value=str(before) if before is not None else None,
                       new_value=str(after) if after is not None else None, reason=reason))


def new_ticket(db: Session, body: TicketCreate, agent: Agent | None = None):
    lock_routing(db)
    code = secrets.token_urlsafe(32)
    ticket = Ticket(**body.model_dump(), status='OPEN', customer_access_hash=token_digest(code), area=agent.area if agent else 'BADI_SUPPORT')
    db.add(ticket)
    db.flush()
    sender = agent.name if agent else ticket.customer_email
    db.add(TicketMessage(ticket_id=ticket.id, sender_role='AGENT' if agent else 'CUSTOMER',
                         sender_name=sender, kind='PUBLIC', body=ticket.description))
    record_event(db, ticket, sender, 'created', None, 'OPEN')
    # Add the ticket to the durable client pool and try dispatch in the same
    # transaction. If everyone is busy, it stays unassigned for the worker.
    dispatch_waiting(db)
    db.commit()
    db.refresh(ticket)
    return ticket, code


def add_message(db: Session, ticket: Ticket, body: str, kind: str, sender_name: str, sender_role: str):
    if ticket.status == 'CLOSED' and kind == 'PUBLIC':
        raise HTTPException(409, 'This ticket is closed. An agent must reopen it before public replies can be sent.')
    # A customer reply never changes status or priority. Agents own workflow.

    message = TicketMessage(ticket_id=ticket.id, body=body, kind=kind,
                            sender_name=sender_name, sender_role=sender_role)
    db.add(message)
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    return MessageRead.model_validate(message)


def queue_view(db: Session, status=None, priority=None, category=None, assigned_agent_id=None, unassigned=False, q='', limit=100, area=None):
    query = select(Ticket)
    if area:
        query = query.where(Ticket.area == area)
    for field, value in [('status', status), ('priority', priority), ('category', category), ('assigned_agent_id', assigned_agent_id)]:
        if value is not None:
            query = query.where(getattr(Ticket, field) == value)
    if unassigned:
        query = query.where(Ticket.assigned_agent_id.is_(None))
    if q:
        query = query.where(or_(Ticket.subject.icontains(q, autoescape=True),
                                Ticket.customer_email.icontains(q, autoescape=True),
                                cast(Ticket.id, String).contains(q.upper().removeprefix('BD-'), autoescape=True)))
    rows = db.scalars(query.order_by(Ticket.updated_at.desc(), Ticket.id.desc()).limit(limit)).all()
    return [TicketRead.model_validate(row) for row in rows]
