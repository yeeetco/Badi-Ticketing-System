"""SSE snapshots: reconnecting clients receive the complete current state.

For this small assignment, the server checks PostgreSQL once per second and
pushes only changed snapshots. This works across API workers without a local
in-memory message bus. Each read releases its database connection immediately.
At higher scale, replace the checks with PostgreSQL LISTEN/NOTIFY or a broker.
"""
import asyncio
import json

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from . import stream_limits
from .security import token_digest, COOKIE_NAME


def encode_snapshot(value):
    return json.dumps(jsonable_encoder(value), separators=(',', ':'))


async def snapshot_events(request, load, initial, interval=1):
    previous = encode_snapshot(initial)
    yield f'event: snapshot\ndata: {previous}\n\n'
    ticks = 0
    while not await request.is_disconnected():
        await asyncio.sleep(interval)
        try:
            current = encode_snapshot(await run_in_threadpool(load))
        except HTTPException:
            yield 'event: denied\ndata: {"detail":"Your access has ended. Please sign in or reopen your ticket."}\n\n'
            return
        except OperationalError:
            # Closing makes the client reconnect and recheck its REST access.
            return
        if current != previous:
            yield f'event: snapshot\ndata: {current}\n\n'
            previous = current
        ticks += 1
        if ticks % 15 == 0:
            yield ': keep-alive\n\n'


def live_response(request: Request, db, loader):
    def load():
        try:
            return loader()
        finally:
            # End the read transaction and release the pooled connection even
            # while the HTTP stream stays open. No writes happen in this path.
            db.rollback()

    initial = load()  # Return a normal 401/404 before starting an invalid stream.
    cookie = 'badi_customer_ticket' if request.url.path.startswith('/customer/') else COOKIE_NAME
    lease = stream_limits.acquire(token_digest(request.cookies.get(cookie, '')))

    async def events():
        try:
            async for event in snapshot_events(request, load, initial):
                stream_limits.touch(lease)
                yield event
        finally:
            stream_limits.release(lease)
    return StreamingResponse(events(), media_type='text/event-stream',
                             background=BackgroundTask(stream_limits.release, lease),
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
