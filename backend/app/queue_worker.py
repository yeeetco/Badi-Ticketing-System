"""Retry durable waiting tickets while FastAPI is running."""
import asyncio
from contextlib import asynccontextmanager
import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .database import engine, get_db
from .routing import dispatch_waiting

logger = logging.getLogger(__name__)


def dispatch_once():
    with Session(engine) as db:
        dispatch_waiting(db)
        db.commit()


async def work():
    while True:
        try:
            await run_in_threadpool(dispatch_once)
        except SQLAlchemyError as error:
            # Waiting clients remain in SQL and are retried after recovery.
            logger.warning('T1 queue retry deferred: %s', type(error).__name__)
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app):
    # Integration tests inject an isolated DB session. Never run a worker against
    # the real demo database while testing a separate schema.
    task = None if get_db in app.dependency_overrides else asyncio.create_task(work())
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
