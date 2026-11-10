import asyncio
import json

from sqlalchemy import select

from app.conversations import customer_ticket, customer_view
from app.database import get_db
from app.live import snapshot_events
from app.main import app
from app.models import Agent
from app.security import password_hasher
from test_agent_access import client, sign_in, TICKET  # reusable isolated PostgreSQL fixture


def create_customer(client):
    response = client.post('/customer/tickets', json={key: TICKET[key] for key in ('customer_email', 'category', 'description')})
    assert response.status_code == 201
    return response.json()


def test_customer_create_and_private_return(client):
    created = create_customer(client)
    ticket = created['ticket']
    assert ticket['status'] == 'OPEN'
    assert ticket['messages'][0]['body'] == TICKET['description']
    assert client.get('/tickets').status_code == 401
    assert client.post('/customer/logout').status_code == 204
    assert client.get(f"/customer/tickets/{ticket['id']}").status_code == 401
    assert client.post('/customer/access', json={'ticket_number': ticket['number'], 'access_code': 'incorrect-code-123456789'}).status_code == 401
    returned = client.post('/customer/access', json={'ticket_number': ticket['number'], 'access_code': created['access_code']})
    assert returned.status_code == 200
    assert returned.json()['id'] == ticket['id']


def test_ticket_ownership_blocks_another_ticket_and_its_stream(client):
    first = create_customer(client)
    second = create_customer(client)
    ticket_id = first['ticket']['id']
    assert client.get(f'/customer/tickets/{ticket_id}').status_code == 404
    assert client.get(f'/customer/tickets/{ticket_id}/live').status_code == 404
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'Cannot send here'}).status_code == 404
    assert client.get(f"/customer/tickets/{second['ticket']['id']}").status_code == 200


def test_both_roles_can_reply_but_notes_never_reach_customer(client):
    created = create_customer(client)
    ticket_id = created['ticket']['id']
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'Customer follow-up'}).status_code == 201
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'forged note', 'kind': 'INTERNAL'}).status_code == 422
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'forged agent reply'}).status_code == 401

    sign_in(client)
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Public answer'}).status_code == 201
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'PRIVATE_PROVIDER_DETAILS', 'kind': 'INTERNAL'}).status_code == 201
    agent = client.get(f'/tickets/{ticket_id}').json()
    assert len(agent['messages']) == 4
    customer = client.get(f'/customer/tickets/{ticket_id}')
    assert 'PRIVATE_PROVIDER_DETAILS' not in customer.text
    assert 'events' not in customer.json()
    assert 'assigned_agent_id' not in customer.json()
    assert 'customer_access_hash' not in customer.text
    assert all(message['kind'] == 'PUBLIC' for message in customer.json()['messages'])
    assert len(customer.json()['messages']) == 3


def test_management_and_audit_are_atomic_and_validate_agent(client):
    ticket_id = create_customer(client)['ticket']['id']
    sign_in(client)
    agent_id = client.get('/auth/me').json()['id']
    changed = client.patch(f'/tickets/{ticket_id}', json={'status': 'IN_PROGRESS', 'priority': 'URGENT'})
    assert changed.status_code == 200
    events = changed.json()['events']
    assert any(event['field'] == 'status' and event['old_value'] == 'OPEN' and event['new_value'] == 'IN_PROGRESS' for event in events)
    assert any(event['field'] == 'assigned_agent_id' and event['new_value'] == str(agent_id) for event in events)
    count = len(events)
    # No-op saves must not invent audit entries.
    assert len(client.patch(f'/tickets/{ticket_id}', json={'status': 'IN_PROGRESS'}).json()['events']) == count
    assert client.patch(f'/tickets/{ticket_id}', json={'assigned_agent_id': 99999}).status_code == 422
    assert client.patch(f'/tickets/{ticket_id}', json={'status': None}).status_code == 422
    unassigned = client.post(f'/tickets/{ticket_id}/return-to-queue', json={}).json()
    assert unassigned['assigned_agent_id'] is None
    assert any(event['field'] == 'assigned_agent_id' and event['new_value'] is None for event in unassigned['events'])


def test_reassignment_and_queue_filters(client):
    ticket_id = create_customer(client)['ticket']['id']
    sign_in(client)
    for db in app.dependency_overrides[get_db]():
        db.add(Agent(name='Second Agent', email='second@example.com', password_hash=password_hasher.hash('another-long-password')))
        db.commit()
        second_id = db.scalar(select(Agent.id).where(Agent.email == 'second@example.com'))
    client.post('/auth/login', json={'email': 'second@example.com', 'password': 'another-long-password'})
    sign_in(client)
    assert client.post(f'/tickets/{ticket_id}/transfer', json={'agent_id': second_id}).status_code == 200
    assert len(client.get(f'/tickets?assigned_agent_id={second_id}&category=CONNECTIVITY&priority=MEDIUM&status=OPEN').json()) == 1
    assert client.get('/tickets?unassigned=true').json() == []
    assert len(client.get('/tickets?q=BD-1001').json()) == 1
    assert client.get('/tickets?q=unmatched-text').json() == []


def test_closed_ticket_blocks_public_messages_and_can_be_reopened(client):
    ticket_id = create_customer(client)['ticket']['id']
    sign_in(client)
    client.patch(f'/tickets/{ticket_id}', json={'status': 'CLOSED'})
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'Customer message'}).status_code == 409
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Agent message'}).status_code == 409
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Private wrap-up', 'kind': 'INTERNAL'}).status_code == 201
    client.patch(f'/tickets/{ticket_id}', json={'status': 'RESOLVED'})
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'It is still not working.'}).status_code == 409
    assert client.get(f'/tickets/{ticket_id}').json()['status'] == 'RESOLVED'
    client.patch(f'/tickets/{ticket_id}', json={'status': 'WAITING_FOR_CUSTOMER'})
    client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'Here are the requested details.'})
    assert client.get(f'/tickets/{ticket_id}').json()['status'] == 'WAITING_FOR_CUSTOMER'


def test_blank_messages_and_public_management_rejected(client):
    ticket_id = create_customer(client)['ticket']['id']
    assert client.patch(f'/tickets/{ticket_id}', json={'status': 'CLOSED'}).status_code == 401
    assert client.get(f'/tickets/{ticket_id}').status_code == 401
    assert client.get('/tickets/live').status_code == 401
    assert client.get(f'/tickets/{ticket_id}/live').status_code == 401
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': '  \n  '}).status_code == 422


def test_customer_sse_uses_filtered_snapshots_and_recovers_current_history(client):
    created = create_customer(client)
    ticket_id = created['ticket']['id']
    sign_in(client)
    client.post(f'/tickets/{ticket_id}/messages', json={'body': 'STREAM_PRIVATE_NOTE', 'kind': 'INTERNAL'})

    def load():
        for db in app.dependency_overrides[get_db]():
            return customer_view(db, customer_ticket(db, created['access_code'], ticket_id))

    class ConnectedRequest:
        async def is_disconnected(self):
            return False

    async def scenario():
        stream = snapshot_events(ConnectedRequest(), load, load(), interval=0)
        first = await anext(stream)
        assert first.startswith('event: snapshot\n')
        assert 'STREAM_PRIVATE_NOTE' not in first
        client.post(f'/tickets/{ticket_id}/messages', json={'body': 'A new public reply'})
        next_frame = await anext(stream)
        payload = json.loads(next_frame.split('data: ', 1)[1])
        assert payload['messages'][-1]['body'] == 'A new public reply'
        assert 'STREAM_PRIVATE_NOTE' not in next_frame
        await stream.aclose()
        # Reconnecting sends complete history, including replies missed offline.
        restarted = snapshot_events(ConnectedRequest(), load, load(), interval=0)
        assert 'A new public reply' in await anext(restarted)
        await restarted.aclose()

    asyncio.run(scenario())
