from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.database import Base
from app import models  # noqa: F401 - register tables with SQLAlchemy metadata


if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    # Tests provide a connection using a new, isolated PostgreSQL schema.
    context.configure(connection=context.config.attributes["connection"], target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
