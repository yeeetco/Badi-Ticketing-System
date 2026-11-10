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
from .security import COOKIE_NAME, CurrentStaff, Db, dummy_hash, verify_password, token_digest
from .routing import dispatch_waiting, lock_routing, return_to_pool
from .queue_worker import lifespan
from .help_content import router as help_router
from .admin_routes import router as admin_router
from .attachment_routes import router as attachment_router
from .upload_limit import UploadLimitMiddleware
from .rate_limits import consume, client_key, check_login_failures, clear_login_failures
from starlette.middleware.trustedhost import TrustedHostMiddleware


app = FastAPI(title="Badi eSIM Support API", version="0.3.0", lifespan=lifespan,
              docs_url='/docs' if settings.environment == 'development' else None,
              redoc_url='/redoc' if settings.environment == 'development' else None,
              openapi_url='/openapi.json' if settings.environment == 'development' else None)
app.add_middleware(UploadLimitMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host.strip() for host in settings.allowed_hosts.split(',')])
logger = logging.getLogger(__name__)


@app.middleware("http")
async def protect_browser_requests(request: Request, call_next):
    # Cookies authenticate requests; verify Origin on writes to prevent CSRF.
    # Vite proxies /api to this service, so the browser stays on one origin.
    allowed = {value.strip() for value in settings.allowed_origins.split(",")}
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.headers.get("origin") not in allowed:
        # Log only address/method/path, never credentials or customer messages.
        logger.warning('Rejected write origin=%r method=%s path=%s', request.headers.get('origin'), request.method, request.url.path)
        response = JSONResponse(status_code=403, content={
            "detail": "This page address is not enabled for support requests. Open support from the configured site address.",
            "code": "ORIGIN_NOT_ALLOWED",
        })

    else:
        response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.url.path not in ('/docs', '/redoc', '/openapi.json'):
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'; sandbox"
    if settings.environment == 'production':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
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
def login(body: LoginRequest, request: Request, response: Response, db: Db):
    consume(db, 'login-peer', client_key(request), 100, 60)
    check_login_failures(db, str(body.email))
    agent = db.scalar(select(Agent).where(Agent.email == str(body.email).lower()))
    verified_hash = agent.password_hash if agent else dummy_hash
    valid = verify_password(body.password, verified_hash)
    if not valid or agent is None or not agent.is_active:
        consume(db, 'login-failure', str(body.email).lower(), 10, 600)
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    lock_routing(db)
    # An administrator may have reset/disabled/deleted the account while the
    # Argon2 verification was running. Recheck under the same lock used by
    # account changes before issuing a new session from stale credentials.
    current = db.scalar(select(Agent).where(Agent.id == agent.id).execution_options(populate_existing=True))
    if not current or not current.is_active or current.password_hash != verified_hash or current.email != str(body.email).lower():
        consume(db, 'login-failure', str(body.email).lower(), 10, 600)
        raise HTTPException(401, 'Email or password is incorrect.')
    agent = current
    # Avoid an unbounded collection of valid sessions after repeated logins.
    old_cookie = request.cookies.get(COOKIE_NAME)
    if old_cookie:
        db.execute(delete(AgentSession).where(AgentSession.token_hash == token_digest(old_cookie), AgentSession.agent_id == agent.id))
    clear_login_failures(db, str(body.email))
    agent.is_available = True
    agent.availability = 'ONLINE'

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
def me(agent: CurrentStaff):
    return agent


@app.post('/auth/heartbeat', response_model=AgentRead)
def heartbeat(request: Request, db: Db, agent: CurrentStaff):
    session = db.get(AgentSession, token_digest(request.cookies[COOKIE_NAME]))
    if session is None:
        raise HTTPException(401, 'Your session ended. Please sign in again.')
    session.last_seen_at = datetime.now(timezone.utc)
    db.commit()
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
                staff = db.get(Agent, agent_id)
                staff.is_available = False
                staff.availability = 'OFFLINE'
                return_to_pool(db, agent_id, 'Last staff session signed out.')
        db.flush()
        dispatch_waiting(db)
        db.commit()
    response.delete_cookie(COOKIE_NAME, secure=settings.cookie_secure, httponly=True, samesite="strict")


app.include_router(ticket_router)
app.include_router(help_router)
app.include_router(admin_router)
app.include_router(attachment_router)
