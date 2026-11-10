from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("tier IN ('T1','T2')", name='valid_agent_tier'),
        CheckConstraint('max_active_chats BETWEEN 1 AND 20', name='valid_agent_capacity'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(String(2), default='T1', server_default='T1')
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    max_active_chats: Mapped[int] = mapped_column(Integer, default=5, server_default='5')
    last_routed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    # Only the SHA-256 digest is stored. The browser holds the random original.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','IN_PROGRESS','WAITING_FOR_CUSTOMER','WAITING_FOR_PROVIDER','RESOLVED','CLOSED')", name="valid_ticket_status"),
        CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')", name="valid_ticket_priority"),
        CheckConstraint("category IN ('INSTALLATION','ACTIVATION','CONNECTIVITY','ORDER','TOPUP','REFUND','OTHER')", name="valid_ticket_category"),
    )

    # PostgreSQL assigns numbers safely, including simultaneous inserts.
    # Gaps are normal after rollback; ticket numbers must never be reused.
    id: Mapped[int] = mapped_column(Identity(start=1001), primary_key=True)
    customer_email: Mapped[str] = mapped_column(String(254))
    order_id: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30))
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer_access_hash: Mapped[str | None] = mapped_column(String(64), unique=True)

    @property
    def number(self) -> str:
        return f"BD-{self.id}"


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        CheckConstraint("kind IN ('PUBLIC','INTERNAL')", name="valid_message_kind"),
        CheckConstraint("sender_role IN ('CUSTOMER','AGENT')", name="valid_sender_role"),
        CheckConstraint("kind != 'INTERNAL' OR sender_role = 'AGENT'", name="internal_agent_only"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    sender_role: Mapped[str] = mapped_column(String(10))
    sender_name: Mapped[str] = mapped_column(String(254))
    kind: Mapped[str] = mapped_column(String(10), default="PUBLIC")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(254))
    field: Mapped[str] = mapped_column(String(30))
    old_value: Mapped[str | None] = mapped_column(String(100))
    new_value: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
