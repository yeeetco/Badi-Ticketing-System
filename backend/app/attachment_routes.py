"""Small private uploads. Metadata travels with chat; bytes require case access."""
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select, func
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool

from .file_validation import validate_isolated
from .rate_limits import consume

from .conversations import CUSTOMER_COOKIE, customer_ticket, ticket_or_404
from .models import Attachment, TicketMessage
from .schemas import MessageRead
from .security import COOKIE_NAME, Db, agent_from_token, support_staff

router = APIRouter()
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES_PER_TICKET = 10  # Also bounds stored bytes to 20 MiB per conversation.


def check_attachment_budget(db, ticket_id):
    count = db.scalar(select(func.count(Attachment.id)).join(TicketMessage).where(TicketMessage.ticket_id == ticket_id))
    if count >= MAX_FILES_PER_TICKET:
        raise HTTPException(413, 'This conversation has reached its limit of 10 attachments. Ask your agent how to share additional files.')


@router.post('/customer/tickets/{ticket_id}/attachments', response_model=MessageRead, status_code=201)
async def upload_attachment(ticket_id: int, request: Request, db: Db):
    ticket = customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id)
    if ticket.status in ('CLOSED', 'RESOLVED'):
        raise HTTPException(409, 'This conversation is complete. Attachments cannot be added.')
    consume(db, 'customer-upload', request.cookies.get(CUSTOMER_COOKIE, ''), 10, 60)
    check_attachment_budget(db, ticket_id)
    db.rollback()  # Release the read connection before receiving/decoding bytes.
    # Multipart parsing is bounded to one file and one optional text field.
    async with request.form(max_files=1, max_fields=1, max_part_size=12000) as form:
        file = form.get('file')
        body = form.get('body', '')
        if not isinstance(file, UploadFile) or not isinstance(body, str) or len(body) > 10000:
            raise HTTPException(422, 'Choose one file and a message of at most 10,000 characters.')
        payload = await file.read(MAX_FILE_BYTES + 1)
        name, content_type, payload = await run_in_threadpool(validate_isolated, file.filename or '', file.content_type or '', payload)
    # No ticket lock is held during upload parsing or image/PDF decoding.
    ticket = customer_ticket(db, request.cookies.get(CUSTOMER_COOKIE), ticket_id, lock=True)
    if ticket.status in ('CLOSED', 'RESOLVED'):
        raise HTTPException(409, 'This conversation is complete. Attachments cannot be added.')
    check_attachment_budget(db, ticket_id)  # Recheck under the ticket lock for concurrent uploads.
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
    consume(db, 'attachment-read', request.cookies.get(CUSTOMER_COOKIE, ''), 60, 60)
    return download(db, ticket_id, attachment_id, public_only=True)


@router.get('/tickets/{ticket_id}/attachments/{attachment_id}')
def staff_download(ticket_id: int, attachment_id: int, request: Request, db: Db):
    staff = support_staff(agent_from_token(db, request.cookies.get(COOKIE_NAME)))
    ticket_or_404(db, ticket_id, staff=staff)
    consume(db, 'staff-attachment-read', str(staff.id), 60, 60)
    return download(db, ticket_id, attachment_id)


def download(db, ticket_id, attachment_id, public_only=False):
    query = select(Attachment).join(TicketMessage).where(Attachment.id == attachment_id, TicketMessage.ticket_id == ticket_id)
    if public_only:
        query = query.where(TicketMessage.kind == 'PUBLIC')
    attachment = db.scalar(query)
    if not attachment:
        raise HTTPException(404, 'Attachment not found.')
    if attachment.blocked:
        raise HTTPException(410, 'This attachment did not pass file security checks and is unavailable.')
    return Response(attachment.payload, media_type=attachment.content_type, headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(attachment.filename, safe='')}",
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
    })
