"""Create the first local administrator without changing existing passwords."""
from pathlib import Path
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import engine
from .models import Agent
from .security import password_hasher


def main():
    if settings.environment != 'development' or engine.url.host not in ('localhost', '127.0.0.1') or engine.url.database != 'badi':
        raise SystemExit('This helper is restricted to the local badi development database.')
    if engine.url.host not in ('localhost', '127.0.0.1') or engine.url.database != 'badi':
        raise SystemExit('This bootstrap is only for the local badi development database.')
    with Session(engine) as db:
        if db.scalar(select(Agent.id).where(Agent.role == 'ADMIN', Agent.is_active.is_(True))):
            print('An active administrator already exists. No credentials were changed.')
            return
        if db.scalar(select(Agent.id).where(Agent.email == 'admin@example.com')):
            raise SystemExit('That email already exists; use an existing administrator to review access.')
        password = secrets.token_urlsafe(18)
        db.add(Agent(email='admin@example.com', name='Badi Administrator', role='ADMIN',
                     password_hash=password_hasher.hash(password)))
        db.commit()
    path = Path(__file__).resolve().parents[2] / '.local' / 'admin-credentials.txt'
    path.parent.mkdir(exist_ok=True)
    path.write_text(f'Email: admin@example.com\nPassword: {password}\n', encoding='utf-8')
    print('Created local administrator. Login details are in .local/admin-credentials.txt (ignored by Git).')


if __name__ == '__main__':
    main()
