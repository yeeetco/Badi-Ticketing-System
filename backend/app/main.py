import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text
from sqlalchemy.exc import OperationalError

from .config import settings
from .models import Agent, AgentSession, Ticket
from .schemas import AgentRead, LoginRequest, TicketCreate, TicketRead
from .security import COOKIE_NAME, CurrentAgent, Db, dummy_hash, password_hasher, token_digest


app = FastAPI(title="Badi eSIM Support API", version="0.1.0")
logger = logging.getLogger(__name__)


@app.middleware("http")
async def protect_browser_requests(request: Request, call_next):
    # Cookies authenticate requests; verify Origin on writes to prevent CSRF.
    # Vite proxies /api to this service, so the browser stays on one origin.
    allowed = {value.strip() for value in settings.allowed_origins.split(",")}
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.headers.get("origin") not in allowed:
        return JSONResponse(status_code=403, content={"detail": "Request origin is not allowed."})

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

    # The opaque token is HttpOnly, not JavaScript-readable or in localStorage.
    token = secrets.token_urlsafe(32)
    db.execute(delete(AgentSession).where(AgentSession.expires_at <= datetime.now(timezone.utc)))
    db.add(AgentSession(
        token_hash=token_digest(token), agent_id=agent.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
    ))
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
        db.execute(delete(AgentSession).where(AgentSession.token_hash == token_digest(token)))
        db.commit()
    response.delete_cookie(COOKIE_NAME, secure=settings.cookie_secure, httponly=True, samesite="strict")


@app.get("/tickets", response_model=list[TicketRead])
def list_tickets(db: Db, agent: CurrentAgent, limit: int = Query(default=50, ge=1, le=100)):
    # This queue is agent-only. A customer endpoint will use ticket ownership.
    return db.scalars(select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(limit)).all()


@app.post("/tickets", response_model=TicketRead, status_code=201)
def create_ticket(body: TicketCreate, db: Db, agent: CurrentAgent):
    # Start with agent-created tickets; customer access is a separate next step.
    ticket = Ticket(**body.model_dump(), status="OPEN")
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket
