import hashlib
import threading
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .database import get_db
from .models import Agent, AgentSession


password_hasher = PasswordHash.recommended()
password_slots = threading.BoundedSemaphore(4)
# Use a real hash even for an unknown email, avoiding a fast early return.
dummy_hash = password_hasher.hash("not-a-real-account-password")
Db = Annotated[Session, Depends(get_db)]
COOKIE_NAME = "badi_agent_session"


def verify_password(password, encoded):
    # Bound concurrent Argon2 work so unauthenticated requests cannot allocate
    # the memory cost of dozens of verifications at once.
    if not password_slots.acquire(blocking=False):
        raise HTTPException(429, 'Sign-in is busy. Please retry shortly.', headers={'Retry-After': '2'})
    try:
        return password_hasher.verify(password, encoded)
    finally:
        password_slots.release()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_agent(db: Db, badi_agent_session: Annotated[str | None, Cookie()] = None) -> Agent:
    return agent_from_token(db, badi_agent_session)


def agent_from_token(db: Session, token: str | None) -> Agent:
    # Every protected endpoint checks the server-side session, regardless of UI.
    session = db.get(AgentSession, token_digest(token)) if token else None
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Please sign in to the staff workspace.")

    agent = db.get(Agent, session.agent_id)
    if agent is None or not agent.is_active:
        raise HTTPException(status_code=401, detail="Agent account is unavailable.")
    return agent


def require_operator(staff: Annotated[Agent, Depends(require_agent)]) -> Agent:
    if staff.role != 'AGENT':
        raise HTTPException(403, 'Your monitoring role cannot send messages or manage normal agent actions.')
    return staff


def require_leader(staff: Annotated[Agent, Depends(require_agent)]) -> Agent:
    if staff.role != 'TEAM_LEAD':
        raise HTTPException(403, 'Team leader access is required.')
    return staff


CurrentStaff = Annotated[Agent, Depends(require_agent)]
CurrentOperator = Annotated[Agent, Depends(require_operator)]
CurrentLeader = Annotated[Agent, Depends(require_leader)]


def require_support(staff: Annotated[Agent, Depends(require_agent)]) -> Agent:
    return support_staff(staff)


def support_staff(staff: Agent) -> Agent:
    if staff.role not in ('AGENT', 'TEAM_LEAD'):
        raise HTTPException(403, 'Support workspace access is required.')
    return staff


def require_admin(staff: Annotated[Agent, Depends(require_agent)]) -> Agent:
    if staff.role != 'ADMIN':
        raise HTTPException(403, 'Administrator access is required.')
    return staff


CurrentSupport = Annotated[Agent, Depends(require_support)]
CurrentAdmin = Annotated[Agent, Depends(require_admin)]
