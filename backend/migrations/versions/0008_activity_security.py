"""Durable read receipts, short typing presence, request limits, file quarantine."""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ticket_messages', sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('attachments', sa.Column('blocked', sa.Boolean(), nullable=False, server_default='false'))
    for table in ('ticket_reads', 'typing_presence'):
        columns = [sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id', ondelete='CASCADE'), primary_key=True),
                   sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agents.id', ondelete='CASCADE'), primary_key=True)]
        if table == 'ticket_reads':
            columns += [sa.Column('last_message_id', sa.Integer(), nullable=False), sa.Column('seen_at', sa.DateTime(timezone=True), nullable=False)]
        else:
            columns += [sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False)]
        op.create_table(table, *columns)
    op.create_table('rate_limit_buckets', sa.Column('key', sa.String(64), primary_key=True),
                    sa.Column('count', sa.Integer(), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_rate_limit_buckets_expires_at', 'rate_limit_buckets', ['expires_at'])


def downgrade():
    for table in ('rate_limit_buckets', 'typing_presence', 'ticket_reads'):
        op.drop_table(table)
    op.drop_column('attachments', 'blocked')
    op.drop_column('ticket_messages', 'seen_at')
