"""Persist explicit customer disconnection and closure."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tickets', sa.Column('customer_ended_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('tickets', 'customer_ended_at')
