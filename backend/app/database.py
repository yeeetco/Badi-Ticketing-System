from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from .config import settings


class Base(DeclarativeBase):
    pass


# pool_pre_ping reconnects cleanly after a local database restart.
engine = create_engine(settings.database_url, pool_pre_ping=True)


def get_db():
    with Session(engine) as session:
        yield session
