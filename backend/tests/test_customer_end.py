from app.database import get_db
from app.main import app
from app.models import Ticket
from test_agent_access import client, set_capacity, sign_in
from test_conversations import create_customer


def test_end_closes_persists_disconnect_and_is_idempotent(client):
    sign_in(client)
    created = create_customer(client)
    ticket_id = created['ticket']['id']
    endpoint = f'/customer/tickets/{ticket_id}/end'
    response = client.post(endpoint)
    assert response.status_code == 200
    detail = response.json()
    assert detail['status'] == 'CLOSED' and detail['customer_ended_at']
    assert detail['routing_state'] == 'COMPLETE'
    assert detail['messages'][-1]['body'] == 'You have disconnected. This chat is now closed.'
    assert all(message['kind'] == 'PUBLIC' for message in detail['messages'])
    assert len(client.post(endpoint).json()['messages']) == len(detail['messages'])
    assert client.get('/customer/session').json()['customer_ended_at'] == detail['customer_ended_at']
    staff = client.get(f'/tickets/{ticket_id}').json()
    assert any(event['field'] == 'status' and event['new_value'] == 'CLOSED' and event['actor'] == detail['customer_email'] for event in staff['events'])
    assert any(message['kind'] == 'INTERNAL' and 'Customer ended' in message['body'] for message in staff['messages'])
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'Cannot send after ending'}).status_code == 409
    assert client.patch(f'/tickets/{ticket_id}', json={'status': 'OPEN'}).status_code == 409
    assert client.post('/customer/logout').status_code == 204
    assert client.get('/customer/session').status_code == 401
    assert client.get(f'/tickets/{ticket_id}').status_code == 200


def test_end_authorization_and_freed_capacity(client):
    sign_in(client)
    set_capacity(client, 1)
    first = create_customer(client)
    second = create_customer(client)
    assert second['ticket']['routing_state'] == 'WAITING'
    first_id = first['ticket']['id']
    assert client.post(f'/customer/tickets/{first_id}/end').status_code == 404
    client.post('/customer/access', json={'access_code': first['access_code']})
    assert client.post(f'/customer/tickets/{first_id}/end').status_code == 200
    for db in app.dependency_overrides[get_db]():
        assert db.get(Ticket, second['ticket']['id']).assigned_agent_id is not None
    client.post('/customer/logout')
    assert client.post(f'/customer/tickets/{first_id}/end').status_code == 401
