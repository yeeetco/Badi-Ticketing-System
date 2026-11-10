"""T1 eligibility, workload capacity, and fair routing metadata."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agents', sa.Column('tier', sa.String(2), nullable=False, server_default='T1'))
    op.add_column('agents', sa.Column('is_available', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('agents', sa.Column('max_active_chats', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('agents', sa.Column('last_routed_at', sa.DateTime(timezone=True)))
    op.create_check_constraint('valid_agent_tier', 'agents', "tier IN ('T1','T2')")
    op.create_check_constraint('valid_agent_capacity', 'agents', 'max_active_chats BETWEEN 1 AND 20')


def downgrade():
    op.drop_constraint('valid_agent_capacity', 'agents', type_='check')
    op.drop_constraint('valid_agent_tier', 'agents', type_='check')
    for column in ('last_routed_at', 'max_active_chats', 'is_available', 'tier'):
        op.drop_column('agents', column)
