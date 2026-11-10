"""Clear local test conversations and consolidate the two sample operator logins.

Run explicitly: python -m app.reset_test_data
Staff passwords, the leader account, and FAQ revisions are preserved. Ticket
numbers continue increasing so an old case reference cannot name a new case.
"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .database import engine
from .models import Agent, AgentSession, Ticket, TicketEvent, TicketMessage
from .routing import lock_routing


def main():
    if engine.url.host not in ('localhost', '127.0.0.1') or engine.url.database != 'badi':
        raise SystemExit('Refusing to reset anything except the local badi development database.')
    with Session(engine) as db:
        lock_routing(db)
        primary = db.scalar(select(Agent).where(Agent.email == 'agent@example.com'))
        mia = db.scalar(select(Agent).where(Agent.email == 'mia@example.com'))
        if not primary or primary.name != 'Badi Support' or (mia and mia.name != 'Mia Support'):
            raise SystemExit('Expected sample accounts were changed; refusing to merge unrelated accounts.')

        # Delete children explicitly; preserve the ticket sequence and accounts.
        db.execute(delete(TicketMessage))
        db.execute(delete(TicketEvent))
        count = db.execute(delete(Ticket)).rowcount
        if mia:
            db.execute(delete(AgentSession).where(AgentSession.agent_id == mia.id))
            db.delete(mia)
        db.commit()
    print(f'Cleared {count} local conversations and their history. Badi Support and the team leader remain; Mia was merged into Badi Support. Passwords unchanged.')


if __name__ == '__main__':
    main()
