"""Reset only the local sample accounts; preserve tickets and real accounts.

Run from backend: python -m app.demo_accounts
The password is prompted, or supplied through DEMO_AGENT_PASSWORD. It is never
stored in source code or in plaintext SQL. This is a local development helper.
"""
import getpass
import os
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .database import engine
from .models import Agent, AgentSession
from .security import password_hasher


def main():
    if settings.environment != 'development' or engine.url.host not in ('localhost', '127.0.0.1') or engine.url.database != 'badi':
        raise SystemExit('This helper is restricted to the local badi development database.')
    if engine.url.host not in ('127.0.0.1', 'localhost'):
        raise SystemExit('This helper only resets demo accounts in a local database.')
    password = os.environ.get('DEMO_AGENT_PASSWORD') or getpass.getpass('New local demo password (12+ characters): ')
    if len(password) < 12:
        raise SystemExit('Use at least 12 characters.')
    with Session(engine) as db:
        for email, name, role in [('agent@example.com', 'Badi Support', 'AGENT'), ('lead@example.com', 'Badi Team Lead', 'TEAM_LEAD')]:
            agent = db.scalar(select(Agent).where(Agent.email == email))
            if agent and agent.name != name:
                raise SystemExit(f'{email} is not the expected sample account; refusing to replace it.')
            if not agent:
                agent = Agent(email=email, name=name)
                db.add(agent)
            agent.password_hash = password_hasher.hash(password)
            agent.tier = 'T1'
            agent.is_available = False
            agent.availability = 'OFFLINE'
            agent.role = role
            agent.max_active_chats = 5
            db.flush()
            db.execute(delete(AgentSession).where(AgentSession.agent_id == agent.id))
        db.commit()

    local = Path(__file__).resolve().parents[2] / '.local'
    local.mkdir(exist_ok=True)
    (local / 'agent-credentials.txt').write_text(f'Email: agent@example.com\nPassword: {password}\n', encoding='utf-8')
    print('Local sample accounts reset: agent@example.com, lead@example.com.')
    print('Previous sample-account sessions revoked. Updated login is in .local/agent-credentials.txt.')


if __name__ == '__main__':
    main()
