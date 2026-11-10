"""Durable T1 queue: oldest waiting case -> eligible least-loaded agent.

PostgreSQL is the queue; no customer is held only in API memory. One shared
transaction lock serializes dispatch and assignment/capacity changes across
workers. A crash rolls the whole dispatch back, including its audit entries.
"""
from datetime import datetime, timezone

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from .models import Agent, AgentSession, Ticket, TicketEvent

ACTIVE_STATUSES = ('OPEN', 'IN_PROGRESS', 'WAITING_FOR_CUSTOMER', 'WAITING_FOR_PROVIDER')
ROUTING_LOCK = 2026111001


def lock_routing(db: Session):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': ROUTING_LOCK})


def signed_in_agent_ids(db: Session):
    return set(db.scalars(select(AgentSession.agent_id).where(
        AgentSession.expires_at > datetime.now(timezone.utc)
    )).all())


def active_loads(db: Session):
    return dict(db.execute(select(Ticket.assigned_agent_id, func.count(Ticket.id)).where(
        Ticket.status.in_(ACTIVE_STATUSES), Ticket.assigned_agent_id.is_not(None)
    ).group_by(Ticket.assigned_agent_id)).all())


def dispatch_waiting(db: Session):
    lock_routing(db)
    now = datetime.now(timezone.utc)
    eligible = db.scalars(select(Agent).where(
        Agent.tier == 'T1', Agent.is_available.is_(True),
        exists(select(AgentSession.token_hash).where(
            AgentSession.agent_id == Agent.id, AgentSession.expires_at > now
        )),
    )).all()
    if not eligible:
        return
    loads = active_loads(db)
    waiting = db.scalars(select(Ticket).where(
        Ticket.assigned_agent_id.is_(None), Ticket.status.in_(ACTIVE_STATUSES)
    ).order_by(Ticket.created_at, Ticket.id).with_for_update()).all()

    for ticket in waiting:
        available = [agent for agent in eligible if loads.get(agent.id, 0) < agent.max_active_chats]
        if not available:
            break
        # Oldest last assignment breaks equal-load ties, then ID makes it stable.
        agent = min(available, key=lambda person: (
            loads.get(person.id, 0),
            person.last_routed_at.timestamp() if person.last_routed_at else float('-inf'), person.id,
        ))
        ticket.assigned_agent_id = agent.id
        ticket.updated_at = datetime.now(timezone.utc)
        agent.last_routed_at = ticket.updated_at
        loads[agent.id] = loads.get(agent.id, 0) + 1
        db.add(TicketEvent(ticket_id=ticket.id, actor='T1 queue router', field='assigned_agent_id',
                           old_value=None, new_value=str(agent.id)))
    db.flush()


def routing_view(db: Session):
    loads = active_loads(db)
    signed_in = signed_in_agent_ids(db)
    waiting = db.scalar(select(func.count(Ticket.id)).where(
        Ticket.assigned_agent_id.is_(None), Ticket.status.in_(ACTIVE_STATUSES)
    ))
    return {
        'waiting_count': waiting,
        'agents': [dict(id=agent.id, name=agent.name, tier=agent.tier,
                       is_available=agent.is_available, signed_in=agent.id in signed_in,
                       active_chats=loads.get(agent.id, 0), capacity=agent.max_active_chats)
                   for agent in db.scalars(select(Agent).order_by(Agent.id)).all()],
    }
