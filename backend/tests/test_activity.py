from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.main import app
from app.models import TicketMessage, TypingPresence
from test_agent_access import client, sign_in
from test_conversations import create_customer
from test_staff_roles import staff_account, login


def test_unread_receipts_public_reply_timer_and_internal_note_privacy(client):
    sign_in(client)
    created = create_customer(client)
    ticket_id = created['ticket']['id']
    original = created['ticket']['messages'][0]
    queue = client.get('/tickets').json()[0]
    assert queue['unread_count'] == 1 and queue['awaiting_reply_since']
    assert client.get('/customer/session').json()['messages'][0]['seen_at'] is None
    receipt = client.post(f'/tickets/{ticket_id}/read', json={'message_id': original['id']})
    assert receipt.status_code == 200
    assert client.get('/tickets').json()[0]['unread_count'] == 0
    assert client.get('/customer/session').json()['messages'][0]['seen_at']
    waiting = queue['awaiting_reply_since']
    client.post(f'/tickets/{ticket_id}/messages', json={'body': 'PRIVATE typing context', 'kind': 'INTERNAL'})
    assert client.get('/tickets').json()[0]['awaiting_reply_since'] == waiting
    assert 'PRIVATE' not in client.get('/customer/session').text
    client.patch(f'/tickets/{ticket_id}', json={'status': 'WAITING_FOR_PROVIDER'})
    assert client.get('/tickets').json()[0]['awaiting_reply_since'] == waiting
    client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Please restart mobile data.'})
    assert client.get('/tickets').json()[0]['awaiting_reply_since'] is None
    latest = client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'It still does not connect.'}).json()
    queue = client.get('/tickets').json()[0]
    assert queue['unread_count'] == 1 and queue['awaiting_reply_since'] == latest['created_at']
    client.post(f'/tickets/{ticket_id}/read', json={'message_id': original['id']})
    assert client.get('/tickets').json()[0]['unread_count'] == 1
    client.post(f'/tickets/{ticket_id}/read', json={'message_id': latest['id']})
    assert client.get('/tickets').json()[0]['unread_count'] == 0
    client.post(f'/customer/tickets/{ticket_id}/end')
    queue = client.get('/tickets').json()[0]
    assert queue['unread_count'] == 0 and queue['awaiting_reply_since'] is None


def test_typing_expires_and_internal_notes_offline_and_wrong_roles_do_not_leak(client):
    sign_in(client)
    ticket_id = create_customer(client)['ticket']['id']
    endpoint = f'/tickets/{ticket_id}/typing'
    assert client.post(endpoint, json={'is_typing': True}).status_code == 204
    assert client.get('/customer/session').json()['agent_is_typing']
    client.post(endpoint, json={'is_typing': True, 'visibility': 'INTERNAL'})
    assert not client.get('/customer/session').json()['agent_is_typing']
    client.post(endpoint, json={'is_typing': True})
    for db in app.dependency_overrides[get_db]():
        agent_id = client.get('/auth/me').json()['id']
        db.get(TypingPresence, (ticket_id, agent_id)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert not client.get('/customer/session').json()['agent_is_typing']
    client.post(endpoint, json={'is_typing': True})
    client.patch('/agents/me/availability', json={'availability': 'OFFLINE'})
    assert not client.get('/customer/session').json()['agent_is_typing']
    staff_account('lead@example.com', role='TEAM_LEAD')
    login(client, 'lead@example.com')
    assert client.post(endpoint, json={'is_typing': True}).status_code == 403


def test_receipts_are_handler_only_and_cannot_reference_another_case(client):
    sign_in(client)
    first = create_customer(client)['ticket']
    second = create_customer(client)['ticket']
    assert client.post(f"/tickets/{first['id']}/read", json={'message_id': second['messages'][0]['id']}).status_code == 422
    assert client.post(f"/tickets/{first['id']}/read", json={'message_id': first['messages'][0]['id'], 'agent_id': 9999}).status_code == 422
    other = staff_account('other@example.com')
    login(client, 'other@example.com')
    assert client.post(f"/tickets/{first['id']}/read", json={'message_id': first['messages'][0]['id']}).status_code == 409
    assert client.post(f"/tickets/{first['id']}/typing", json={'is_typing': True}).status_code == 409
    assert other
