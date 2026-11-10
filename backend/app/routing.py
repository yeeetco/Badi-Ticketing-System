"""Durable T1 queue: oldest waiting case -> eligible least-loaded agent.

PostgreSQL is the queue; no customer is held only in API memory. One shared
transaction lock serializes dispatch and assignment/capacity changes across
workers. A crash rolls the whole dispatch back, including its audit entries.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from .models import Agent, AgentSession, Ticket, TicketEvent

ACTIVE_STATUSES = ('OPEN', 'IN_PROGRESS', 'WAITING_FOR_CUSTOMER', 'WAITING_FOR_PROVIDER')
ROUTING_LOCK = 2026111001
HEARTBEAT_GRACE_SECONDS = 90


def lock_routing(db: Session):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': ROUTING_LOCK})


def signed_in_agent_ids(db: Session):
    return set(db.scalars(select(AgentSession.agent_id).where(
        AgentSession.expires_at > datetime.now(timezone.utc),
        AgentSession.last_seen_at > datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_GRACE_SECONDS),
    )).all())


def active_loads(db: Session):
    return dict(db.execute(select(Ticket.assigned_agent_id, func.count(Ticket.id)).where(
        Ticket.status.in_(ACTIVE_STATUSES), Ticket.assigned_agent_id.is_not(None)
    ).group_by(Ticket.assigned_agent_id)).all())


def return_to_pool(db: Session, agent_id: int, reason: str):
    for ticket in db.scalars(select(Ticket).where(
        Ticket.assigned_agent_id == agent_id, Ticket.status.in_(ACTIVE_STATUSES)
    ).with_for_update()).all():
        ticket.assigned_agent_id = None
        ticket.updated_at = datetime.now(timezone.utc)
        db.add(TicketEvent(ticket_id=ticket.id, actor='Availability router', field='assigned_agent_id',
                           old_value=str(agent_id), new_value=None, reason=reason))
    db.flush()


def dispatch_waiting(db: Session):
    lock_routing(db)
    now = datetime.now(timezone.utc)
    signed_in = signed_in_agent_ids(db)
    # Offline/expired agents must never strand customers. Break is different:
    # existing handles stay parked, while new allocations pause.
    for staff in db.scalars(select(Agent)).all():
        if staff.id not in signed_in and staff.availability != 'OFFLINE':
            staff.availability = 'OFFLINE'
            staff.is_available = False
        if staff.availability == 'OFFLINE' or staff.role != 'AGENT' or not staff.is_active:
            return_to_pool(db, staff.id, 'Agent offline, session stale, or no longer an operator.')
    db.flush()
    eligible = db.scalars(select(Agent).where(
        Agent.tier == 'T1', Agent.role == 'AGENT', Agent.is_active.is_(True), Agent.availability == 'ONLINE', Agent.is_available.is_(True),
        exists(select(AgentSession.token_hash).where(
            AgentSession.agent_id == Agent.id, AgentSession.expires_at > now,
            AgentSession.last_seen_at > now - timedelta(seconds=HEARTBEAT_GRACE_SECONDS),
        )),
    )).all()
    if not eligible:
        return
    loads = active_loads(db)
    waiting = db.scalars(select(Ticket).where(
        Ticket.assigned_agent_id.is_(None), Ticket.status.in_(ACTIVE_STATUSES)
    ).order_by(Ticket.created_at, Ticket.id).with_for_update()).all()

    for ticket in waiting:
        available = [agent for agent in eligible
                     if agent.area == ticket.area and loads.get(agent.id, 0) < agent.max_active_chats
                     and not (ticket.requeue_agent_id == agent.id and ticket.requeue_until and ticket.requeue_until > now)]
        if not available:
            continue
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


def routing_view(db: Session, area='BADI_SUPPORT'):
    loads = active_loads(db)
    signed_in = signed_in_agent_ids(db)
    waiting = db.scalar(select(func.count(Ticket.id)).where(
        Ticket.assigned_agent_id.is_(None), Ticket.status.in_(ACTIVE_STATUSES), Ticket.area == area,
    ))
    return {
        'waiting_count': waiting,
        'agents': [dict(id=agent.id, name=agent.name, tier=agent.tier,
                       is_available=agent.is_available, signed_in=agent.id in signed_in,
                       availability=agent.availability, area=agent.area,
                       active_chats=loads.get(agent.id, 0), capacity=agent.max_active_chats)
                   for agent in db.scalars(select(Agent).where(Agent.area == area, Agent.role == 'AGENT').order_by(Agent.id)).all()],
    }
