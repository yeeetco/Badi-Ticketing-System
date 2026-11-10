"""Bound multipart uploads before parsing, including chunked requests."""
from fastapi import HTTPException
from starlette.responses import JSONResponse

# One 2 MiB file plus text fields and multipart headers.
MAX_UPLOAD_REQUEST = 2 * 1024 * 1024 + 32 * 1024


class UploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return await self.app(scope, receive, send)
        maximum = MAX_UPLOAD_REQUEST if scope.get('path', '').endswith('/attachments') else 65536
        headers = dict(scope.get('headers', []))
        try:
            size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            size = maximum + 1
        detail = 'Attachments must be 2 MB or smaller.' if maximum == MAX_UPLOAD_REQUEST else 'Request body exceeds the 64 KB limit.'
        if size < 0 or size > maximum:
            return await JSONResponse({'detail': detail}, status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            if received > maximum:
                raise HTTPException(413, detail)
            return message

        await self.app(scope, bounded_receive, send)
