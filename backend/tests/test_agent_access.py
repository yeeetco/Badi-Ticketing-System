"""Integration tests use real PostgreSQL, with a fresh schema per test.

The migrated demo tables and data in the default schema are never cleared.
Only schemas generated here (badi_test_<random UUID>) are dropped afterwards.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import Agent, AgentSession
from app.security import COOKIE_NAME, password_hasher, token_digest


ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "test-agent-password-123"
TICKET = {
    "customer_email": "customer@example.com",
    "category": "CONNECTIVITY",
    "subject": "No internet after activation",
    "description": "The eSIM is installed but mobile data does not work.",
    "priority": "HIGH",
}


@pytest.fixture
def client():
    schema = f"badi_test_{uuid4().hex}"
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()

        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection

        try:
            command.upgrade(config, "head")
            connection.commit()

            with Session(connection) as db:
                db.add(Agent(email="agent@example.com", name="Test Agent", password_hash=password_hasher.hash(PASSWORD)))
                db.commit()

            def override_db():
                with Session(connection) as db:
                    yield db

            app.dependency_overrides[get_db] = override_db
            with TestClient(app, headers=ORIGIN) as test_client:
                yield test_client
        finally:
            app.dependency_overrides.clear()
            connection.rollback()
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            connection.commit()


def sign_in(client):
    response = client.post("/auth/login", json={"email": "agent@example.com", "password": PASSWORD})
    assert response.status_code == 200
    return response


def set_capacity(client, value):
    """Configure a routing fixture directly; operators cannot edit capacity."""
    agent_id = client.get('/auth/me').json()['id']
    for db in app.dependency_overrides[get_db]():
        db.get(Agent, agent_id).max_active_chats = value
        db.commit()


def test_public_cannot_read_or_create_tickets(client):
    assert client.get("/tickets").status_code == 401
    assert client.post("/tickets", json=TICKET).status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_wrong_password_does_not_issue_session(client):
    response = client.post("/auth/login", json={"email": "agent@example.com", "password": "incorrect"})
    assert response.status_code == 401
    assert COOKIE_NAME not in client.cookies


def test_login_queue_and_logout_revoke_session(client):
    response = sign_in(client)
    assert "password_hash" not in response.json()
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    token = client.cookies.get(COOKIE_NAME)
    assert client.get("/tickets").json() == []
    assert client.get("/auth/me").json()["name"] == "Test Agent"

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/tickets").status_code == 401
    # Replaying a copied cookie must fail after server-side revocation.
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/tickets").status_code == 401


def test_creation_uses_postgres_number_and_open_status(client):
    sign_in(client)
    assert client.post("/tickets", json=TICKET).status_code == 403
    intake = {key: TICKET[key] for key in ("customer_email", "category", "description")}
    first = client.post("/customer/tickets", json=intake)
    assert first.status_code == 201
    assert first.json()["ticket"]["number"] == "BD-1001"
    assert first.json()["ticket"]["status"] == "OPEN"
    second = client.post("/customer/tickets", json=intake)
    assert second.json()["ticket"]["number"] == "BD-1002"
    assert len(client.get("/tickets").json()) == 2


def test_validation_rejects_blank_subject_and_unknown_priority(client):
    sign_in(client)
    assert client.post("/customer/tickets", json={"customer_email":"customer@example.com", "category":"CONNECTIVITY", "description":"   "}).status_code == 422
    assert client.post("/customer/tickets", json={**TICKET, "priority": "CRITICAL"}).status_code == 422
    # The caller cannot bypass the OPEN workflow by supplying their own status.
    assert client.post("/customer/tickets", json={**TICKET, "status": "CLOSED"}).status_code == 422


def test_cross_origin_and_missing_origin_writes_are_rejected(client):
    sign_in(client)
    assert client.post("/tickets", json=TICKET, headers={"Origin": "https://untrusted.example"}).status_code == 403
    client.headers.pop("origin")
    assert client.post("/auth/logout").status_code == 403


def test_expired_session_is_rejected(client):
    sign_in(client)
    token = client.cookies.get(COOKIE_NAME)
    override = app.dependency_overrides[get_db]
    for db in override():
        session = db.scalar(select(AgentSession).where(AgentSession.token_hash == token_digest(token)))
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/tickets").status_code == 401


def test_frontend_origins_use_port_5173_and_reject_other_ports(client):
    body = {'category': 'CONNECTIVITY', 'description': 'My eSIM has no internet connection.'}
    for origin in ('http://localhost:5173', 'http://127.0.0.1:5173'):
        assert client.post('/customer/intake/summary', json=body, headers={'Origin': origin}).status_code == 200
    for origin in ('http://localhost:5174', 'http://127.0.0.1:5174', 'https://untrusted.example', 'null'):
        response = client.post('/customer/intake/summary', json=body, headers={'Origin': origin})
        assert response.status_code == 403
        assert response.json()['code'] == 'ORIGIN_NOT_ALLOWED'
