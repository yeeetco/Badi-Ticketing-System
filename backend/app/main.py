import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text
from sqlalchemy.exc import OperationalError

from .config import settings
from .models import Agent, AgentSession
from .schemas import AgentRead, LoginRequest
from .ticket_routes import router as ticket_router
from .security import COOKIE_NAME, CurrentAgent, Db, dummy_hash, password_hasher, token_digest
from .routing import dispatch_waiting, lock_routing
from .queue_worker import lifespan


app = FastAPI(title="Badi eSIM Support API", version="0.2.0", lifespan=lifespan)
logger = logging.getLogger(__name__)


@app.middleware("http")
async def protect_browser_requests(request: Request, call_next):
    # Cookies authenticate requests; verify Origin on writes to prevent CSRF.
    # Vite proxies /api to this service, so the browser stays on one origin.
    allowed = {value.strip() for value in settings.allowed_origins.split(",")}
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.headers.get("origin") not in allowed:
        # Log only address/method/path, never credentials or customer messages.
        logger.warning('Rejected write origin=%r method=%s path=%s', request.headers.get('origin'), request.method, request.url.path)
        return JSONResponse(status_code=403, content={
            "detail": "This page address is not enabled for support requests. Open support from the configured site address.",
            "code": "ORIGIN_NOT_ALLOWED",
        })

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(OperationalError)
async def database_unavailable(_request: Request, error: OperationalError):
    logger.error("Database operation failed: %s", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable. Check PostgreSQL and apply migrations."})


@app.get("/health")
def health(db: Db):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "postgresql"}


@app.post("/auth/login", response_model=AgentRead)
def login(body: LoginRequest, response: Response, db: Db):
    agent = db.scalar(select(Agent).where(Agent.email == str(body.email).lower()))
    valid = password_hasher.verify(body.password, agent.password_hash if agent else dummy_hash)
    if not valid or agent is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    lock_routing(db)
    agent.is_available = True

    # The opaque token is HttpOnly, not JavaScript-readable or in localStorage.
    token = secrets.token_urlsafe(32)
    db.execute(delete(AgentSession).where(AgentSession.expires_at <= datetime.now(timezone.utc)))
    db.add(AgentSession(
        token_hash=token_digest(token), agent_id=agent.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
    ))
    db.flush()
    dispatch_waiting(db)
    db.commit()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=settings.cookie_secure, samesite="strict", max_age=8 * 60 * 60)
    return agent


@app.get("/auth/me", response_model=AgentRead)
def me(agent: CurrentAgent):
    return agent


@app.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Db):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        lock_routing(db)
        session = db.get(AgentSession, token_digest(token))
        agent_id = session.agent_id if session else None
        db.execute(delete(AgentSession).where(AgentSession.token_hash == token_digest(token)))
        if agent_id:
            other_session = db.scalar(select(AgentSession.token_hash).where(
                AgentSession.agent_id == agent_id, AgentSession.expires_at > datetime.now(timezone.utc)
            ).limit(1))
            if not other_session:
                db.get(Agent, agent_id).is_available = False
        db.commit()
    response.delete_cookie(COOKIE_NAME, secure=settings.cookie_secure, httponly=True, samesite="strict")


app.include_router(ticket_router)
