"""Bound request bodies even without Content-Length; private responses never cache."""
from fastapi import HTTPException
from starlette.responses import JSONResponse

from app.config import get_settings


class RequestSafety:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        private = path.startswith(("/api/v1/auth", "/api/v1/cases", "/api/v1/admin", "/api/v1/workspace"))
        upload = scope["method"] == "POST" and path.startswith("/api/v1/cases/") and path.endswith("/evidence")
        limit = get_settings().max_file_bytes if upload else 65536
        headers = dict(scope["headers"])
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError()
        except ValueError:
            return await JSONResponse({"detail": "Invalid content length"}, 400)(scope, receive, send)
        if length > limit:
            return await JSONResponse({"detail": "Request body exceeds configured limit"}, 413)(scope, receive, send)
        seen = 0

        async def bounded_receive():
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > limit:
                raise HTTPException(413, "Request body exceeds configured limit")
            return message

        async def safe_send(message):
            if message["type"] == "http.response.start":
                values = list(message.get("headers", []))
                values.append((b"x-content-type-options", b"nosniff"))
                if private:
                    values = [(k, v) for k, v in values if k.lower() != b"cache-control"]
                    values.append((b"cache-control", b"no-store"))
                message["headers"] = values
            await send(message)

        await self.app(scope, bounded_receive, safe_send)
