"""Small private uploads. Metadata travels with chat; bytes require case access."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import quote
import warnings

from fastapi import APIRouter, HTTPException, Request, Response
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select
from starlette.datastructures import UploadFile

from .conversations import CUSTOMER_COOKIE, customer_ticket, ticket_or_404
from .models import Attachment, TicketMessage
from .schemas import MessageRead
from .security import COOKIE_NAME, Db, agent_from_token, support_staff

router = APIRouter()
MAX_FILE_BYTES = 2 * 1024 * 1024
IMAGE_TYPES = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'GIF': 'image/gif', 'WEBP': 'image/webp'}
EXTENSIONS = {'application/pdf': {'.pdf'}, 'image/png': {'.png'}, 'image/jpeg': {'.jpg', '.jpeg'},
              'image/gif': {'.gif'}, 'image/webp': {'.webp'}}


def validated_file(filename: str, declared_type: str, payload: bytes):
    # Filename and Content-Type alone cannot prove that a file is an image/PDF.
    name = PurePosixPath(filename.replace('\\', '/')).name
    name = ''.join(c for c in name if c.isprintable())[:200]
    if not name or not payload:
        raise HTTPException(422, 'Choose a nonempty PDF or image file.')
    if len(payload) > MAX_FILE_BYTES:
        raise HTTPException(413, 'Attachments must be 2 MB or smaller.')
    try:
        if payload.startswith(b'%PDF-'):
            pdf = PdfReader(BytesIO(payload), strict=True)
            if pdf.is_encrypted:
                raise ValueError('Encrypted PDF')
            # Force the page tree to be read, rather than just checking a header.
            if len(pdf.pages) < 1:
                raise ValueError('Empty PDF')
            content_type = 'application/pdf'
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(payload)) as image:
                    content_type = IMAGE_TYPES.get(image.format)
                    if not content_type:
                        raise ValueError('Unsupported image')
                    image.verify()
        if declared_type != content_type or PurePosixPath(name).suffix.lower() not in EXTENSIONS[content_type]:
            raise ValueError('Type mismatch')
    except Exception as failure:
        # Decoder errors are intentionally not returned with file internals.
        raise HTTPException(422, 'Use a valid PDF, PNG, JPEG, GIF, or WebP file with a matching extension.') from failure
    return name, content_type


@router.post('/customer/tickets/{ticket_id}/attachments', response_model=MessageRead, status_code=201)
async def upload_attachment(ticket_id: int, request: Request, db: Db):
    ticket = customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id, lock=True)
    if ticket.status in ('CLOSED', 'RESOLVED'):
        raise HTTPException(409, 'This conversation is complete. Attachments cannot be added.')
    # Multipart parsing is bounded to one file and one optional text field.
    async with request.form(max_files=1, max_fields=1, max_part_size=12000) as form:
        file = form.get('file')
        body = form.get('body', '')
        if not isinstance(file, UploadFile) or not isinstance(body, str) or len(body) > 10000:
            raise HTTPException(422, 'Choose one file and a message of at most 10,000 characters.')
        payload = await file.read(MAX_FILE_BYTES + 1)
        name, content_type = validated_file(file.filename or '', file.content_type or '', payload)
    message = TicketMessage(ticket_id=ticket.id, body=body.strip(), kind='PUBLIC',
                            sender_name=ticket.customer_email, sender_role='CUSTOMER')
    db.add(message)
    db.flush()
    db.add(Attachment(message_id=message.id, filename=name, content_type=content_type, size=len(payload), payload=payload))
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    return MessageRead.model_validate(message)


@router.get('/customer/tickets/{ticket_id}/attachments/{attachment_id}')
def customer_download(ticket_id: int, attachment_id: int, request: Request, db: Db):
    customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id)
    return download(db, ticket_id, attachment_id, public_only=True)


@router.get('/tickets/{ticket_id}/attachments/{attachment_id}')
def staff_download(ticket_id: int, attachment_id: int, request: Request, db: Db):
    staff = support_staff(agent_from_token(db, request.cookies.get(COOKIE_NAME)))
    ticket_or_404(db, ticket_id, staff=staff)
    return download(db, ticket_id, attachment_id)


def download(db, ticket_id, attachment_id, public_only=False):
    query = select(Attachment).join(TicketMessage).where(Attachment.id == attachment_id, TicketMessage.ticket_id == ticket_id)
    if public_only:
        query = query.where(TicketMessage.kind == 'PUBLIC')
    attachment = db.scalar(query)
    if not attachment:
        raise HTTPException(404, 'Attachment not found.')
    return Response(attachment.payload, media_type=attachment.content_type, headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(attachment.filename, safe='')}",
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
    })
