"""Persist a per-conversation return-to-queue cooldown."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tickets', sa.Column('requeue_agent_id', sa.Integer(), nullable=True))
    op.add_column('tickets', sa.Column('requeue_until', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key('fk_tickets_requeue_agent', 'tickets', 'agents', ['requeue_agent_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_tickets_requeue_agent', 'tickets', type_='foreignkey')
    op.drop_column('tickets', 'requeue_until')
    op.drop_column('tickets', 'requeue_agent_id')
