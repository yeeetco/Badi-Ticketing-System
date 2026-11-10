"""Persistent conversations, customer access, and management audit events."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tickets", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("tickets", sa.Column("customer_access_hash", sa.String(64)))
    op.create_unique_constraint("uq_tickets_customer_access_hash", "tickets", ["customer_access_hash"])
    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_role", sa.String(10), nullable=False),
        sa.Column("sender_name", sa.String(254), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('PUBLIC','INTERNAL')", name="valid_message_kind"),
        sa.CheckConstraint("sender_role IN ('CUSTOMER','AGENT')", name="valid_sender_role"),
        sa.CheckConstraint("kind != 'INTERNAL' OR sender_role = 'AGENT'", name="internal_agent_only"),
    )
    op.create_index("ix_ticket_messages_ticket_id", "ticket_messages", ["ticket_id"])
    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor", sa.String(254), nullable=False),
        sa.Column("field", sa.String(30), nullable=False),
        sa.Column("old_value", sa.String(100)),
        sa.Column("new_value", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"])
    # Existing descriptions become the first message; no old ticket is erased.
    op.execute("""INSERT INTO ticket_messages (ticket_id, sender_role, sender_name, kind, body, created_at)
                  SELECT id, 'CUSTOMER', customer_email, 'PUBLIC', description, created_at FROM tickets""")


def downgrade():
    op.drop_table("ticket_events")
    op.drop_table("ticket_messages")
    op.drop_constraint("uq_tickets_customer_access_hash", "tickets", type_="unique")
    op.drop_column("tickets", "customer_access_hash")
    op.drop_column("tickets", "updated_at")
