"""Read receipts and queue metrics. Private notes never count as a public reply."""
from datetime import datetime, timezone

from sqlalchemy import case, func, select

from .models import TicketMessage, TicketRead, TypingPresence
from .routing import ACTIVE_STATUSES, signed_in_agent_ids


def queue_metrics(db, tickets, viewer_id=None):
    ids = [ticket.id for ticket in tickets]
    if not ids:
        return {}
    customer = (TicketMessage.kind == 'PUBLIC') & (TicketMessage.sender_role == 'CUSTOMER')
    human_reply = (TicketMessage.kind == 'PUBLIC') & (TicketMessage.sender_role == 'AGENT') & (TicketMessage.sender_name != 'System update')
    last_reply = dict(db.execute(select(TicketMessage.ticket_id, func.max(TicketMessage.id)).where(
        TicketMessage.ticket_id.in_(ids), human_reply).group_by(TicketMessage.ticket_id)).all())
    cursors = dict(db.execute(select(TicketRead.ticket_id, TicketRead.last_message_id).where(
        TicketRead.ticket_id.in_(ids), TicketRead.agent_id == viewer_id)).all()) if viewer_id else {}
    # One grouped pass over public customer messages; no per-ticket query loop.
    replies = case(last_reply, value=TicketMessage.ticket_id, else_=0) if last_reply else 0
    seen = case(cursors, value=TicketMessage.ticket_id, else_=0) if cursors else 0
    rows = db.execute(select(TicketMessage.ticket_id,
        func.count().filter(TicketMessage.id > seen),
        func.min(TicketMessage.created_at).filter(TicketMessage.id > replies),
    ).where(TicketMessage.ticket_id.in_(ids), customer).group_by(TicketMessage.ticket_id)).all()
    values = {row[0]: {'unread_count': row[1] if viewer_id else 0, 'awaiting_reply_since': row[2]} for row in rows}
    return {ticket.id: values.get(ticket.id, {'unread_count': 0, 'awaiting_reply_since': None})
            if ticket.status in ACTIVE_STATUSES else {'unread_count': 0, 'awaiting_reply_since': None} for ticket in tickets}


def agent_typing(db, ticket, assigned):
    if not assigned or ticket.status not in ACTIVE_STATUSES or assigned.availability == 'OFFLINE' or not assigned.is_active:
        return False
    presence = db.get(TypingPresence, (ticket.id, assigned.id))
    return bool(presence and presence.expires_at > datetime.now(timezone.utc) and assigned.id in signed_in_agent_ids(db))
