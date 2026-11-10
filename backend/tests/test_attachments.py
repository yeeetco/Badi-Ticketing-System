from io import BytesIO

from PIL import Image
from pypdf import PdfWriter

from test_agent_access import client, sign_in
from test_conversations import create_customer
from test_staff_roles import staff_account, login


def image_bytes():
    buffer = BytesIO()
    Image.new('RGB', (8, 8), 'green').save(buffer, format='PNG')
    return buffer.getvalue()


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_attachments_are_atomic_persistent_and_private_to_the_case(client):
    ticket_id = create_customer(client)['ticket']['id']
    endpoint = f'/customer/tickets/{ticket_id}/attachments'
    payload = image_bytes()
    uploaded = client.post(endpoint, files={'file': ('screen.png', payload, 'image/png')}, data={'body': 'My screenshot'})
    assert uploaded.status_code == 201
    message = uploaded.json()
    assert message['body'] == 'My screenshot'
    attachment = message['attachments'][0]
    assert attachment['filename'] == 'screen.png' and 0 < attachment['size'] <= 2097152
    assert 'payload' not in uploaded.text
    downloaded = client.get(f"{endpoint}/{attachment['id']}")
    assert Image.open(BytesIO(downloaded.content)).getpixel((0, 0)) == (0, 128, 0)
    assert 'attachment;' in downloaded.headers['content-disposition']
    assert client.post(endpoint, files={'file': ('order.pdf', pdf_bytes(), 'application/pdf')}).status_code == 201
    sign_in(client)
    assert client.get(f"/tickets/{ticket_id}/attachments/{attachment['id']}").content == downloaded.content
    assert len(client.get(f'/tickets/{ticket_id}').json()['messages'][1]['attachments']) == 1
    # A new customer session cannot read the first customer's attachment.
    create_customer(client)
    assert client.get(f"{endpoint}/{attachment['id']}").status_code == 404
    staff_account('remote@example.com', area='OTHER_AREA')
    login(client, 'remote@example.com')
    assert client.get(f"/tickets/{ticket_id}/attachments/{attachment['id']}").status_code == 404


def test_file_validation_size_mime_content_closed_and_unauthenticated(client):
    ticket_id = create_customer(client)['ticket']['id']
    endpoint = f'/customer/tickets/{ticket_id}/attachments'
    for name, payload, mime, status in [
        ('huge.pdf', b'%PDF-' + b'x' * 2097152, 'application/pdf', 413),
        ('empty.png', b'', 'image/png', 422),
        ('fake.png', b'not an image', 'image/png', 422),
        ('wrong.pdf', image_bytes(), 'application/pdf', 422),
        ('fake.pdf', b'%PDF-1.7\nthis is not a document', 'application/pdf', 422),
        ('script.svg', b'<svg onload="alert(1)"/>', 'image/svg+xml', 422),
    ]:
        assert client.post(endpoint, files={'file': (name, payload, mime)}).status_code == status
    assert len(client.get(f'/customer/tickets/{ticket_id}').json()['messages']) == 1
    sign_in(client)
    client.patch(f'/tickets/{ticket_id}', json={'status': 'CLOSED'})
    assert client.post(endpoint, files={'file': ('screen.png', image_bytes(), 'image/png')}).status_code == 409
    client.post('/customer/logout')
    assert client.post(endpoint, files={'file': ('screen.png', image_bytes(), 'image/png')}).status_code == 401


def test_chunked_oversized_request_is_bounded_before_persisting(client):
    ticket_id = create_customer(client)['ticket']['id']
    boundary = 'test-upload-boundary'
    def chunks():
        yield f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="huge.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
        for _ in range(40):
            yield b'x' * 65536
        yield f'\r\n--{boundary}--\r\n'.encode()
    response = client.post(f'/customer/tickets/{ticket_id}/attachments', content=chunks(),
                           headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    assert response.status_code == 413
    assert len(client.get(f'/customer/tickets/{ticket_id}').json()['messages']) == 1
