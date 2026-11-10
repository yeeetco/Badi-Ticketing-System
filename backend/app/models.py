from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)


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

    @property
    def number(self) -> str:
        return f"BD-{self.id}"
