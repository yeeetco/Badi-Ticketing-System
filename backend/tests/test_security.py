from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image, PngImagePlugin
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from app import stream_limits
from app.config import Settings
from app.database import get_db
from app.file_validation import sanitize_file
from app.main import app
from app.models import Attachment
from test_agent_access import client, sign_in
from test_attachments import image_bytes
from test_conversations import create_customer


def test_login_throttles_failed_accounts_and_rotates_existing_session(client):
    for _ in range(10):
        assert client.post('/auth/login', json={'email': 'agent@example.com', 'password': 'wrong'}).status_code == 401
    blocked = client.post('/auth/login', json={'email': 'agent@example.com', 'password': 'wrong'})
    assert blocked.status_code == 429 and blocked.headers.get('retry-after')


def test_session_rotation_headers_host_and_body_limits(client):
    sign_in(client)
    old = client.cookies.get('badi_agent_session')
    sign_in(client)
    current = client.cookies.get('badi_agent_session')
    assert old != current
    client.cookies.set('badi_agent_session', old)
    assert client.get('/auth/me').status_code == 401
    client.cookies.set('badi_agent_session', current)
    response = client.get('/auth/me')
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert client.get('/health', headers={'Host': 'untrusted.example'}).status_code == 400
    assert client.post('/auth/login', content=b'x' * 70000).status_code == 413
    assert client.post('/customer/tickets', json={}, headers={'Origin': 'https://untrusted.example'}).status_code == 403


def test_production_settings_fail_closed():
    with pytest.raises(ValueError):
        Settings(_env_file=None, database_url='postgresql://unused', environment='production')
    valid = Settings(_env_file=None, database_url='postgresql://unused', environment='production', cookie_secure=True,
                     allowed_origins='https://support.example.com', allowed_hosts='support.example.com')
    assert valid.cookie_secure


def test_image_sanitization_removes_metadata_trailing_payload_and_unsafe_names():
    image = Image.new('RGB', (8, 8), 'green')
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('private-location', 'REMOVE_ME')
    data = BytesIO()
    image.save(data, format='PNG', pnginfo=metadata)
    name, mime, canonical = sanitize_file('screen.png', 'image/png', data.getvalue() + b'<script>UNTRUSTED_TRAILER</script>')
    assert name == 'screen.png' and mime == 'image/png'
    assert b'REMOVE_ME' not in canonical and b'UNTRUSTED_TRAILER' not in canonical
    assert Image.open(BytesIO(canonical)).getpixel((0, 0)) == (0, 128, 0)
    with pytest.raises(ValueError):
        sanitize_file('file:stream.png', 'image/png', data.getvalue())


def test_active_pdf_is_rejected_instead_of_distributed():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.root_object[NameObject('/OpenAction')] = DictionaryObject({
        NameObject('/S'): NameObject('/JavaScript'), NameObject('/JS'): TextStringObject('void(0)'),
    })
    data = BytesIO()
    writer.write(data)
    with pytest.raises(ValueError, match='not supported'):
        sanitize_file('active.pdf', 'application/pdf', data.getvalue())


def test_quarantined_attachment_is_never_downloaded(client):
    created = create_customer(client)['ticket']
    endpoint = f"/customer/tickets/{created['id']}/attachments"
    uploaded = client.post(endpoint, files={'file': ('screen.png', image_bytes(), 'image/png')})
    assert uploaded.status_code == 201
    attachment_id = uploaded.json()['attachments'][0]['id']
    for db in app.dependency_overrides[get_db]():
        db.get(Attachment, attachment_id).blocked = True
        db.commit()
    assert client.get(f'{endpoint}/{attachment_id}').status_code == 410
    view = client.get('/customer/session').json()
    assert view['messages'][-1]['attachments'][0]['available'] is False
    sign_in(client)
    assert client.get(f"/tickets/{created['id']}/attachments/{attachment_id}").status_code == 410


def test_stream_connection_budget_releases_leases():
    leases = [stream_limits.acquire('unit-test-principal') for _ in range(8)]
    try:
        with pytest.raises(HTTPException) as error:
            stream_limits.acquire('unit-test-principal')
        assert error.value.status_code == 429
    finally:
        for lease in leases:
            stream_limits.release(lease)
    lease = stream_limits.acquire('unit-test-principal')
    stream_limits.release(lease)


def test_attachment_storage_budget_is_enforced(client):
    ticket = create_customer(client)['ticket']
    message_id = ticket['messages'][0]['id']
    for db in app.dependency_overrides[get_db]():
        for _ in range(10):
            db.add(Attachment(message_id=message_id, filename='fixture.png', content_type='image/png', size=1, payload=b'x'))
        db.commit()
    response = client.post(f"/customer/tickets/{ticket['id']}/attachments", files={'file': ('screen.png', image_bytes(), 'image/png')})
    assert response.status_code == 413 and '10 attachments' in response.json()['detail']


def test_password_reset_during_login_cannot_issue_a_stale_session(client, monkeypatch):
    import app.main as main_module
    from app.models import Agent
    from app.security import password_hasher
    from sqlalchemy import select
    from test_agent_access import PASSWORD
    original = main_module.lock_routing
    replacement = password_hasher.hash('replacement-password-123')

    def reset_before_lock(db):
        account = db.scalar(select(Agent).where(Agent.email == 'agent@example.com'))
        account.password_hash = replacement
        db.commit()
        original(db)

    monkeypatch.setattr(main_module, 'lock_routing', reset_before_lock)
    response = client.post('/auth/login', json={'email': 'agent@example.com', 'password': PASSWORD})
    assert response.status_code == 401
    assert client.get('/auth/me').status_code == 401
