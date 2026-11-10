"""Area-scoped supervisors, staff states, session heartbeats and emergency audit."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agents', sa.Column('role', sa.String(20), server_default='AGENT', nullable=False))
    op.add_column('agents', sa.Column('area', sa.String(80), server_default='BADI_SUPPORT', nullable=False))
    op.add_column('agents', sa.Column('availability', sa.String(10), server_default='OFFLINE', nullable=False))
    op.execute("UPDATE agents SET availability = CASE WHEN is_available THEN 'ONLINE' ELSE 'OFFLINE' END")
    op.create_check_constraint('valid_staff_role', 'agents', "role IN ('AGENT','TEAM_LEAD')")
    op.create_check_constraint('valid_availability', 'agents', "availability IN ('ONLINE','BREAK','OFFLINE')")
    op.add_column('agent_sessions', sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column('tickets', sa.Column('area', sa.String(80), server_default='BADI_SUPPORT', nullable=False))
    op.add_column('tickets', sa.Column('emergency_closed', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('ticket_events', sa.Column('reason', sa.Text()))


def downgrade():
    op.drop_column('ticket_events', 'reason')
    op.drop_column('tickets', 'emergency_closed')
    op.drop_column('tickets', 'area')
    op.drop_column('agent_sessions', 'last_seen_at')
    op.drop_constraint('valid_availability', 'agents', type_='check')
    op.drop_constraint('valid_staff_role', 'agents', type_='check')
    for name in ('availability', 'area', 'role'):
        op.drop_column('agents', name)
