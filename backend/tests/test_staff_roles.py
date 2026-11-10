from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import Agent, AgentSession, Ticket
from app.routing import dispatch_waiting
from app.security import password_hasher
from test_agent_access import client, sign_in, PASSWORD, TICKET
from test_conversations import create_customer


def staff_account(email, role='AGENT', area='BADI_SUPPORT'):
    for db in app.dependency_overrides[get_db]():
        staff = Agent(email=email, name=email.split('@')[0], role=role, area=area,
                      password_hash=password_hasher.hash(PASSWORD))
        db.add(staff)
        db.commit()
        return staff.id


def login(client, email):
    response = client.post('/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 200
    return response.json()


def test_supervisor_can_monitor_but_cannot_reply_note_or_use_operator_actions(client):
    ticket_id = create_customer(client)['ticket']['id']
    staff_account('lead@example.com', 'TEAM_LEAD')
    profile = login(client, 'lead@example.com')
    assert profile['role'] == 'TEAM_LEAD'
    assert client.get(f'/tickets/{ticket_id}').status_code == 200
    assert client.get('/routing').status_code == 200
    for kind in ('PUBLIC', 'INTERNAL'):
        assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Supervisor must not send this', 'kind': kind}).status_code == 403
    assert client.patch(f'/tickets/{ticket_id}', json={'status': 'CLOSED'}).status_code == 403
    assert client.post('/tickets', json=TICKET).status_code == 403
    assert client.patch('/agents/me/availability', json={'availability': 'ONLINE'}).status_code == 403
    # A team leader is never an eligible T1 handler, even when signed in.
    assert client.get(f'/tickets/{ticket_id}').json()['assigned_agent_id'] is None


def test_area_scope_covers_lists_details_streams_and_emergency_actions(client):
    own = create_customer(client)['ticket']['id']
    remote_id = staff_account('remote@example.com', area='OTHER_AREA')
    for db in app.dependency_overrides[get_db]():
        remote = Ticket(**TICKET, status='OPEN', area='OTHER_AREA')
        db.add(remote)
        db.commit()
        remote_ticket = remote.id
    staff_account('lead@example.com', 'TEAM_LEAD')
    login(client, 'lead@example.com')
    assert [ticket['id'] for ticket in client.get('/tickets').json()] == [own]
    assert remote_id not in [person['id'] for person in client.get('/agents').json()]
    assert remote_id not in [person['id'] for person in client.get('/routing').json()['agents']]
    assert client.get(f'/tickets/{remote_ticket}').status_code == 404
    assert client.get(f'/tickets/{remote_ticket}/live').status_code == 404
    assert client.post(f'/tickets/{remote_ticket}/emergency-close', json={'reason': 'Cross-area closure is forbidden'}).status_code == 404


def test_emergency_close_requires_reason_preserves_history_and_is_audited(client):
    created = create_customer(client)
    ticket_id = created['ticket']['id']
    sign_in(client)
    client.post(f'/tickets/{ticket_id}/messages', json={'body': 'PRIVATE_CASE_CONTEXT', 'kind': 'INTERNAL'})
    assert client.post(f'/tickets/{ticket_id}/emergency-close', json={'reason': 'An operator cannot do this'}).status_code == 403
    staff_account('lead@example.com', 'TEAM_LEAD')
    login(client, 'lead@example.com')
    assert client.post(f'/tickets/{ticket_id}/emergency-close', json={'reason': '   '}).status_code == 422
    reason = 'Emergency handling protocol requires an immediate supervised closure.'
    response = client.post(f'/tickets/{ticket_id}/emergency-close', json={'reason': reason})
    assert response.status_code == 200
    detail = response.json()
    assert detail['status'] == 'CLOSED' and detail['emergency_closed']
    assert len(detail['messages']) == 3
    audit = [event for event in detail['events'] if event['reason'] and reason in event['reason']]
    assert len(audit) == 1 and audit[0]['actor'] == 'lead'
    assert client.post(f'/tickets/{ticket_id}/emergency-close', json={'reason': reason}).status_code == 409
    public = client.get(f'/customer/tickets/{ticket_id}')
    assert 'PRIVATE_CASE_CONTEXT' not in public.text and reason not in public.text
    assert client.post(f'/customer/tickets/{ticket_id}/messages', json={'body': 'This case is now closed'}).status_code == 409
    sign_in(client)
    assert client.patch(f'/tickets/{ticket_id}', json={'status': 'OPEN'}).status_code == 409
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'No post-closure note', 'kind': 'INTERNAL'}).status_code == 409


def test_offline_returns_active_cases_and_balances_to_another_agent(client):
    sign_in(client)
    first_agent = client.get('/auth/me').json()['id']
    ticket = create_customer(client)['ticket']
    assert client.patch('/agents/me/availability', json={'availability': 'BREAK'}).json()['availability'] == 'BREAK'
    assert client.get(f"/tickets/{ticket['id']}").json()['assigned_agent_id'] == first_agent
    queued = create_customer(client)['ticket']
    assert queued['routing_state'] == 'WAITING'
    client.patch('/agents/me/availability', json={'availability': 'OFFLINE'})
    assert client.get(f"/tickets/{ticket['id']}").json()['assigned_agent_id'] is None
    assert client.get('/routing').json()['waiting_count'] == 2
    second_id = staff_account('second@example.com')
    login(client, 'second@example.com')
    for record in (ticket, queued):
        detail = client.get(f"/tickets/{record['id']}").json()
        assert detail['assigned_agent_id'] == second_id
        assert detail['status'] == 'OPEN'
    assert any(event['reason'] == 'Agent selected Offline.' for event in client.get(f"/tickets/{ticket['id']}").json()['events'])


def test_stale_heartbeat_requeues_case_without_deleting_session_or_messages(client):
    sign_in(client)
    ticket = create_customer(client)['ticket']
    for db in app.dependency_overrides[get_db]():
        for session in db.scalars(select(AgentSession)).all():
            session.last_seen_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        db.commit()
        dispatch_waiting(db)
        db.commit()
    assert client.get('/auth/me').json()['availability'] == 'OFFLINE'
    detail = client.get(f"/tickets/{ticket['id']}").json()
    assert detail['assigned_agent_id'] is None and len(detail['messages']) == 1
    assert client.post('/auth/heartbeat').json()['availability'] == 'OFFLINE'
    client.patch('/agents/me/availability', json={'availability': 'ONLINE'})
    assert client.get(f"/tickets/{ticket['id']}").json()['assigned_agent_id'] is not None


def test_role_forgery_and_replying_to_another_agents_parked_case_are_rejected(client):
    assert client.post('/auth/login', json={'email': 'agent@example.com', 'password': PASSWORD, 'role': 'TEAM_LEAD'}).status_code == 422
    sign_in(client)
    ticket_id = create_customer(client)['ticket']['id']
    staff_account('second@example.com')
    login(client, 'second@example.com')
    assert client.post(f'/tickets/{ticket_id}/messages', json={'body': 'Not my case'}).status_code == 409
    assert client.patch(f'/tickets/{ticket_id}', json={'status': 'CLOSED'}).status_code == 409
    assert client.post(f'/tickets/{ticket_id}/emergency-close', json={'reason': 'Still not a leader account'}).status_code == 403


def test_bot_can_restore_with_code_only_and_remembered_session(client):
    created = create_customer(client)
    client.post('/customer/logout')
    response = client.post('/customer/access', json={'access_code': created['access_code']})
    assert response.status_code == 200 and response.json()['status'] == 'OPEN'
    assert client.get('/customer/session').json()['id'] == created['ticket']['id']
    assert client.post('/customer/access', json={'access_code': 'BD-1001'}).status_code == 422
    assert client.post('/customer/access', json={'access_code': 'unknown-private-code-123456'}).status_code == 401


def test_faq_revision_is_local_attributed_and_available_without_auth(client):
    response = client.get('/help/faq')
    assert response.status_code == 200
    data = response.json()
    assert len(data['source_content_sha256']) == 64
    assert data['source_url'] == 'https://badiesim.com/help/faq'
    assert data['revision'] and data['reviewed_on'] and len(data['items']) == 8
