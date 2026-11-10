from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import Agent, Ticket
from test_agent_access import client, sign_in, PASSWORD
from test_conversations import create_customer
from test_staff_roles import login, staff_account


USER = dict(name='New Operator', email='new@example.com', password=PASSWORD, role='AGENT',
            area='BADI_SUPPORT', tier='T1', max_active_chats=5, is_active=True)


def administrator(client):
    admin = staff_account('admin@example.com', role='ADMIN')
    login(client, 'admin@example.com')
    return admin


def update_body(user, **changes):
    body = {key: user[key] for key in ('name', 'email', 'role', 'area', 'tier', 'max_active_chats', 'is_active')}
    return {**body, **changes}


def test_user_management_is_admin_only_and_admin_is_not_an_operator(client):
    assert client.get('/admin/users').status_code == 401
    sign_in(client)
    assert client.get('/admin/users').status_code == 403
    assert client.post('/admin/users', json=USER).status_code == 403
    staff_account('lead@example.com', role='TEAM_LEAD')
    login(client, 'lead@example.com')
    assert client.get('/admin/users').status_code == 403
    administrator(client)
    for path in ('/tickets', '/tickets/live', '/agents', '/agents/live', '/routing'):
        assert client.get(path).status_code == 403
    assert client.patch('/agents/me/availability', json={'availability': 'ONLINE'}).status_code == 403
    ticket_id = create_customer(client)['ticket']['id']
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Forbidden'}).status_code == 403
    assert client.post(f'/tickets/{ticket_id}/emergency-close', json={'reason': 'Administrators are not supervisors'}).status_code == 403


def test_admin_full_crud_validates_profiles_passwords_duplicates_and_last_admin(client):
    admin = administrator(client)
    created = client.post('/admin/users', json=USER)
    assert created.status_code == 201
    user = created.json()
    assert 'password_hash' not in created.text and PASSWORD not in created.text
    assert client.get(f"/admin/users/{user['id']}").json()['email'] == USER['email']
    assert client.post('/admin/users', json=USER).status_code == 409
    assert client.post('/admin/users', json={**USER, 'email': 'weak@example.com', 'password': 'weak'}).status_code == 422
    edited = client.put(f"/admin/users/{user['id']}", json=update_body(user, name='Updated Name', role='TEAM_LEAD'))
    assert edited.status_code == 200 and edited.json()['role'] == 'TEAM_LEAD'
    assert edited.json()['name'] == 'Updated Name'
    own = client.get(f'/admin/users/{admin}').json()
    assert client.put(f'/admin/users/{admin}', json=update_body(own, role='AGENT')).status_code == 409
    assert client.put(f'/admin/users/{admin}', json=update_body(own, is_active=False)).status_code == 409
    assert client.delete(f'/admin/users/{admin}').status_code == 409
    assert client.delete(f"/admin/users/{user['id']}").status_code == 204
    assert client.get(f"/admin/users/{user['id']}").status_code == 404


def test_role_change_revokes_sessions_requeues_handles_and_disable_blocks_login(client):
    sign_in(client)
    operator = client.get('/auth/me').json()
    token = client.cookies.get('badi_agent_session')
    ticket_id = create_customer(client)['ticket']['id']
    administrator(client)
    changed = client.put(f"/admin/users/{operator['id']}", json=update_body(operator, role='TEAM_LEAD'))
    assert changed.status_code == 200
    for db in app.dependency_overrides[get_db]():
        assert db.get(Ticket, ticket_id).assigned_agent_id is None
    admin_cookie = client.cookies.get('badi_agent_session')
    client.cookies.set('badi_agent_session', token)
    assert client.get('/auth/me').status_code == 401
    client.cookies.set('badi_agent_session', admin_cookie)
    assert client.put(f"/admin/users/{operator['id']}", json=update_body(changed.json(), is_active=False)).status_code == 200
    assert client.post('/auth/login', json={'email': operator['email'], 'password': PASSWORD}).status_code == 401


def test_delete_handler_preserves_case_and_messages(client):
    sign_in(client)
    operator = client.get('/auth/me').json()
    ticket_id = create_customer(client)['ticket']['id']
    administrator(client)
    assert client.delete(f"/admin/users/{operator['id']}").status_code == 204
    for db in app.dependency_overrides[get_db]():
        assert db.get(Agent, operator['id']) is None
        ticket = db.get(Ticket, ticket_id)
        assert ticket and ticket.assigned_agent_id is None
    assert len(client.get(f'/customer/tickets/{ticket_id}').json()['messages']) == 1
