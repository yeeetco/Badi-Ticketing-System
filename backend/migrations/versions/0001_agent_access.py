"""Agent accounts, revocable sessions, and the initial ticket queue.

This migration is intentionally explicit: future edits to models.py must not
silently alter the schema created by an older migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
    )
    op.create_table(
        "agent_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_sessions_expires_at", "agent_sessions", ["expires_at"])
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), sa.Identity(start=1001), primary_key=True),
        sa.Column("customer_email", sa.String(254), nullable=False),
        sa.Column("order_id", sa.String(100)),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("assigned_agent_id", sa.Integer(), sa.ForeignKey("agents.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('OPEN','IN_PROGRESS','WAITING_FOR_CUSTOMER','WAITING_FOR_PROVIDER','RESOLVED','CLOSED')", name="valid_ticket_status"),
        sa.CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')", name="valid_ticket_priority"),
        sa.CheckConstraint("category IN ('INSTALLATION','ACTIVATION','CONNECTIVITY','ORDER','TOPUP','REFUND','OTHER')", name="valid_ticket_category"),
    )


def downgrade():
    op.drop_table("tickets")
    op.drop_index("ix_agent_sessions_expires_at", table_name="agent_sessions")
    op.drop_table("agent_sessions")
    op.drop_table("agents")
