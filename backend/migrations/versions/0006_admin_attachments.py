"""Administrator accounts and private chat attachments."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('valid_staff_role', 'agents', type_='check')
    op.create_check_constraint('valid_staff_role', 'agents', "role IN ('AGENT','TEAM_LEAD','ADMIN')")
    op.add_column('agents', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.create_table('attachments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('message_id', sa.Integer(), sa.ForeignKey('ticket_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(200), nullable=False),
        sa.Column('content_type', sa.String(80), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('payload', sa.LargeBinary(), nullable=False),
        sa.CheckConstraint('size > 0 AND size <= 2097152', name='valid_attachment_size'))
    op.create_index('ix_attachments_message_id', 'attachments', ['message_id'])


def downgrade():
    op.drop_table('attachments')
    op.drop_column('agents', 'is_active')
    op.execute("UPDATE agents SET role='TEAM_LEAD' WHERE role='ADMIN'")
    op.drop_constraint('valid_staff_role', 'agents', type_='check')
    op.create_check_constraint('valid_staff_role', 'agents', "role IN ('AGENT','TEAM_LEAD')")
