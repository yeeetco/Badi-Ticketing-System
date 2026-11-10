import hashlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .database import get_db
from .models import Agent, AgentSession


password_hasher = PasswordHash.recommended()
# Use a real hash even for an unknown email, avoiding a fast early return.
dummy_hash = password_hasher.hash("not-a-real-account-password")
Db = Annotated[Session, Depends(get_db)]
COOKIE_NAME = "badi_agent_session"


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_agent(db: Db, badi_agent_session: Annotated[str | None, Cookie()] = None) -> Agent:
    return agent_from_token(db, badi_agent_session)


def agent_from_token(db: Session, token: str | None) -> Agent:
    # Every protected endpoint checks the server-side session, regardless of UI.
    session = db.get(AgentSession, token_digest(token)) if token else None
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Please sign in as a support agent.")

    agent = db.get(Agent, session.agent_id)
    if agent is None:
        raise HTTPException(status_code=401, detail="Agent account is unavailable.")
    return agent


CurrentAgent = Annotated[Agent, Depends(require_agent)]
