"""Bound multipart uploads before parsing, including chunked requests."""
from fastapi import HTTPException
from starlette.responses import JSONResponse

# One 2 MiB file plus text fields and multipart headers.
MAX_UPLOAD_REQUEST = 2 * 1024 * 1024 + 32 * 1024


class UploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') != 'POST' or not scope.get('path', '').endswith('/attachments'):
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            size = MAX_UPLOAD_REQUEST + 1
        if size > MAX_UPLOAD_REQUEST:
            return await JSONResponse({'detail': 'Attachments must be 2 MB or smaller.'}, status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            if received > MAX_UPLOAD_REQUEST:
                raise HTTPException(413, 'Attachments must be 2 MB or smaller.')
            return message

        await self.app(scope, bounded_receive, send)
