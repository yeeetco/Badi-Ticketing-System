from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.conversations import new_ticket
from app.database import engine, get_db
from app.intake import summarize_issue
from app.main import app
from app.models import Agent, AgentSession, Ticket
from app.routing import dispatch_waiting
from app.schemas import TicketCreate
from app.security import password_hasher
from test_agent_access import client, sign_in, TICKET, PASSWORD

INTAKE = {'customer_email': 'queue@example.com', 'category': 'CONNECTIVITY',
          'description': 'My eSIM is installed but there is no internet. I restarted the phone.'}


def new_customer(client, **changes):
    response = client.post('/customer/tickets', json={**INTAKE, **changes})
    assert response.status_code == 201
    return response.json()['ticket']


def test_customer_metadata_is_generated_and_workflow_fields_rejected(client):
    result = new_customer(client, order_id='ORD-10293')
    assert result['subject'] == 'My eSIM is installed but there is no internet.'
    assert result['status'] == 'OPEN' and result['priority'] == 'MEDIUM'
    assert result['routing_state'] == 'WAITING' and result['queue_position'] == 1
    assert result['order_id'] == 'ORD-10293'
    for extra in ({'priority': 'URGENT'}, {'status': 'CLOSED'}, {'assigned_agent_id': 1}, {'subject': 'Forged'}):
        assert client.post('/customer/tickets', json={**INTAKE, **extra}).status_code == 422
    preview = client.post('/customer/intake/summary', json={'category': INTAKE['category'], 'description': INTAKE['description']})
    assert preview.json()['subject'] == result['subject']


def test_summary_is_local_bounded_and_preserves_original_description(client):
    long_description = 'Hello team, ' + 'My internet connection drops repeatedly while travelling ' * 10
    assert len(summarize_issue(long_description, 'CONNECTIVITY')) <= 100
    assert summarize_issue(long_description, 'CONNECTIVITY').startswith('My internet')
    created = new_customer(client, description=long_description)
    assert created['messages'][0]['body'] == long_description.strip()


def test_waiting_pool_dispatches_on_login_and_records_assignment(client):
    first = new_customer(client)
    second = new_customer(client)
    assert first['queue_position'] == 1 and second['queue_position'] == 2
    sign_in(client)
    me = client.get('/auth/me').json()
    assert me['tier'] == 'T1' and me['is_available']
    detail = client.get(f"/tickets/{first['id']}").json()
    assert detail['assigned_agent_id'] == me['id']
    assert any(event['actor'] == 'T1 queue router' and event['field'] == 'assigned_agent_id' for event in detail['events'])
    customer = client.get(f"/customer/tickets/{second['id']}").json()
    assert customer['routing_state'] == 'ASSIGNED' and customer['assigned_agent_name'] == 'Test Agent'


def test_capacity_fifo_pause_resume_and_worker_retry(client):
    sign_in(client)
    assert client.patch('/agents/me/availability', json={'is_available': True, 'max_active_chats': 1}).status_code == 200
    first = new_customer(client)
    second = new_customer(client)
    third = new_customer(client)
    assert first['routing_state'] == 'ASSIGNED'
    assert second['queue_position'] == 1 and third['queue_position'] == 2

    client.patch('/agents/me/availability', json={'is_available': False, 'max_active_chats': 1})
    client.patch(f"/tickets/{first['id']}", json={'status': 'RESOLVED'})
    # Exercise the same dispatcher the background worker calls.
    for db in app.dependency_overrides[get_db]():
        dispatch_waiting(db)
        db.commit()
    assert client.get(f"/tickets/{second['id']}").json()['assigned_agent_id'] is None
    client.patch('/agents/me/availability', json={'is_available': True, 'max_active_chats': 1})
    assert client.get(f"/tickets/{second['id']}").json()['assigned_agent_id'] is not None
    assert client.get(f"/tickets/{third['id']}").json()['assigned_agent_id'] is None
    client.patch(f"/tickets/{second['id']}", json={'status': 'CLOSED'})
    for db in app.dependency_overrides[get_db]():
        dispatch_waiting(db)
        db.commit()
    assert client.get(f"/tickets/{third['id']}").json()['assigned_agent_id'] is not None


def test_t2_and_expired_sessions_are_not_eligible(client):
    sign_in(client)
    agent_id = client.get('/auth/me').json()['id']
    for db in app.dependency_overrides[get_db]():
        db.get(Agent, agent_id).tier = 'T2'
        db.commit()
    ticket = new_customer(client)
    assert ticket['routing_state'] == 'WAITING'
    for db in app.dependency_overrides[get_db]():
        db.get(Agent, agent_id).tier = 'T1'
        for session in db.scalars(select(AgentSession)).all():
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        dispatch_waiting(db)
        db.commit()
        assert db.get(Ticket, ticket['id']).assigned_agent_id is None
    assert client.get('/routing').status_code == 401


def test_least_load_and_equal_load_fairness(client):
    sign_in(client)
    for db in app.dependency_overrides[get_db]():
        other = Agent(name='Second T1', email='second@example.com', password_hash=password_hasher.hash(PASSWORD))
        db.add(other)
        db.commit()
    assert client.post('/auth/login', json={'email': 'second@example.com', 'password': PASSWORD}).status_code == 200
    ids = [new_customer(client)['id'] for _ in range(4)]
    assignees = [client.get(f'/tickets/{ticket_id}').json()['assigned_agent_id'] for ticket_id in ids]
    assert len(set(assignees)) == 2
    assert assignees[0] != assignees[1] and assignees[2] != assignees[3]
    assert assignees.count(assignees[0]) == 2


def test_public_cannot_change_availability_and_logout_stops_new_work(client):
    assert client.patch('/agents/me/availability', json={'is_available': True, 'max_active_chats': 20}).status_code == 401
    assert client.get('/routing').status_code == 401
    assert client.get('/routing/live').status_code == 401
    sign_in(client)
    assert client.patch('/agents/me/availability', json={'is_available': True, 'max_active_chats': 0}).status_code == 422
    client.post('/auth/logout')
    assert new_customer(client)['routing_state'] == 'WAITING'


def test_concurrent_arrivals_cannot_exceed_agent_capacity(client):
    sign_in(client)
    client.patch('/agents/me/availability', json={'is_available': True, 'max_active_chats': 1})
    for db in app.dependency_overrides[get_db]():
        schema = db.scalar(text('SELECT current_schema()'))

    def arrive():
        with engine.connect() as connection:
            # Schema is the UUID test schema created by our fixture, never input.
            assert schema.startswith('badi_test_') and schema.replace('_', '').isalnum()
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.commit()
            try:
                with Session(connection) as db:
                    ticket, _ = new_ticket(db, TicketCreate(**TICKET))
                    return ticket.assigned_agent_id
            finally:
                connection.rollback()
                connection.execute(text('SET search_path TO public'))
                connection.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: arrive(), range(2)))
    assert sum(assignee is not None for assignee in results) == 1
