from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY = 32 * 1024 * 1024


class RequestGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/api/")
        headers = Headers(scope=scope)
        if is_api and scope["method"] in WRITE_METHODS:
            if headers.get("x-forma-action") != "1" or headers.get("sec-fetch-site") == "cross-site":
                await JSONResponse({"detail": "请求缺少同源操作标记"}, 403)(scope, receive, send)
                return
            length = headers.get("content-length", "0")
            if not length.isdecimal() or len(length) > 9 or int(length) > MAX_BODY:
                await JSONResponse({"detail": "请求体过大"}, 413)(scope, receive, send)
                return

        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if is_api and consumed > MAX_BODY:
                raise HTTPException(413, "请求体过大")
            return message

        async def secure_send(message):
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers.setdefault("X-Content-Type-Options", "nosniff")
                response_headers.setdefault("X-Frame-Options", "DENY")
                response_headers.setdefault("Referrer-Policy", "no-referrer")
                if is_api:
                    response_headers.setdefault("Cache-Control", "no-store")
                if not is_api:
                    response_headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
                    )
            await send(message)

        await self.app(scope, bounded_receive, secure_send)
