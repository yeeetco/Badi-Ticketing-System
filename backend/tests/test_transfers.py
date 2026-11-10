from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.main import app
from app.models import Ticket
from app.routing import dispatch_waiting
from test_agent_access import client, sign_in
from test_conversations import create_customer
from test_staff_roles import login, staff_account


def test_queue_return_excludes_previous_handler_until_expiry(client):
    sign_in(client)
    agent_id = client.get('/auth/me').json()['id']
    ticket_id = create_customer(client)['ticket']['id']
    response = client.post(f'/tickets/{ticket_id}/return-to-queue', json={})
    assert response.status_code == 200
    assert response.json()['assigned_agent_id'] is None
    # An availability toggle and the recurring dispatcher cannot bypass it.
    client.patch('/agents/me/availability', json={'availability': 'ONLINE'})
    assert client.get(f'/tickets/{ticket_id}').json()['assigned_agent_id'] is None
    assert client.patch(f'/tickets/{ticket_id}', json={'assigned_agent_id': agent_id}).status_code == 422
    for db in app.dependency_overrides[get_db]():
        ticket = db.get(Ticket, ticket_id)
        assert ticket.requeue_agent_id == agent_id
        assert ticket.requeue_until > datetime.now(timezone.utc)
        ticket.requeue_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.flush()
        dispatch_waiting(db)
        db.commit()
    assert client.get(f'/tickets/{ticket_id}').json()['assigned_agent_id'] == agent_id


def test_return_can_route_immediately_to_another_agent(client):
    sign_in(client)
    ticket_id = create_customer(client)['ticket']['id']
    other = staff_account('other@example.com')
    login(client, 'other@example.com')
    sign_in(client)
    response = client.post(f'/tickets/{ticket_id}/return-to-queue', json={})
    assert response.status_code == 200
    assert response.json()['assigned_agent_id'] == other
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Former handler cannot reply'}).status_code == 409


def test_transfer_checks_ownership_area_availability_capacity_and_role(client):
    sign_in(client)
    ticket_id = create_customer(client)['ticket']['id']
    other = staff_account('other@example.com')
    remote = staff_account('remote@example.com', area='OTHER')
    lead = staff_account('lead@example.com', role='TEAM_LEAD')
    endpoint = f'/tickets/{ticket_id}/transfer'
    for target in (remote, lead, 999999):
        assert client.post(endpoint, json={'agent_id': target}).status_code == 422
    assert client.post(endpoint, json={'agent_id': other}).status_code == 409
    login(client, 'other@example.com')
    client.patch('/agents/me/availability', json={'max_active_chats': 1})
    # Existing case consumes the receiving agent's only slot.
    occupied = create_customer(client)['ticket']['id']
    sign_in(client)
    assert client.post(endpoint, json={'agent_id': other}).status_code == 409
    login(client, 'other@example.com')
    client.patch(f'/tickets/{occupied}', json={'status': 'CLOSED'})
    sign_in(client)
    transferred = client.post(endpoint, json={'agent_id': other})
    assert transferred.status_code == 200
    assert transferred.json()['assigned_agent_id'] == other
    assert any('transferred' in (event['reason'] or '') for event in transferred.json()['events'])
    assert client.post(f'/tickets/{ticket_id}/return-to-queue', json={}).status_code == 409
    assert client.post(endpoint, json={'agent_id': other}).status_code == 409
    login(client, 'lead@example.com')
    assert client.post(endpoint, json={'agent_id': other}).status_code == 403
    assert client.post(f'/tickets/{ticket_id}/return-to-queue', json={}).status_code == 403


def test_status_notes_are_dated_atomic_private_and_not_duplicated(client):
    ticket_id = create_customer(client)['ticket']['id']
    sign_in(client)
    endpoint = f'/tickets/{ticket_id}'
    response = client.patch(endpoint, json={'status': 'IN_PROGRESS'})
    notes = [m for m in response.json()['messages'] if m['kind'] == 'INTERNAL']
    assert len(notes) == 1
    assert notes[0]['sender_name'] == 'System update'
    assert 'Open to In progress' in notes[0]['body']
    assert datetime.fromisoformat(notes[0]['created_at'])
    repeated = client.patch(endpoint, json={'status': 'IN_PROGRESS'}).json()
    assert len([m for m in repeated['messages'] if m['kind'] == 'INTERNAL']) == 1
    public = client.get(f'/customer/tickets/{ticket_id}').json()
    assert public['status'] == 'IN_PROGRESS'
    assert all(m['kind'] == 'PUBLIC' for m in public['messages'])
    assert 'System update' not in str(public)
