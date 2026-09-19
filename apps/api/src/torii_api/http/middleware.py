"""Bounded ASGI envelope. Logs intentionally omit arbitrary URLs and input values."""

import asyncio
import json
import logging
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from torii_api.domain.errors import DomainError
from torii_api.http.json import MAX_BODY
from torii_api.http.problems import problem

_logger = logging.getLogger("torii.access")


class EnvelopeMiddleware:
    def __init__(self, app: ASGIApp, allowed_host: str, timeout: float = 15.0) -> None:
        self.app = app
        self.allowed_host = allowed_host
        self.timeout = timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started_at = perf_counter()
        started = False
        status = 500

        async def send_response(message: Message) -> None:
            nonlocal started, status
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        async def respond(error: DomainError) -> None:
            await problem(error, request_id)(scope, receive, send_response)

        try:
            async with asyncio.timeout(self.timeout):
                headers = Headers(scope=scope)
                if headers.getlist("host") != [self.allowed_host]:
                    raise DomainError(400, "invalid_host")
                lengths = headers.getlist("content-length")
                if lengths and (
                    len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
                ):
                    raise DomainError(400, "invalid_content_length")
                if lengths and (len(lengths[0]) > 10 or int(lengths[0]) > MAX_BODY):
                    raise DomainError(413, "payload_too_large")
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        status = 499
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > MAX_BODY:
                        raise DomainError(413, "payload_too_large")
                    if not message.get("more_body", False):
                        break
                if lengths and int(lengths[0]) != len(body):
                    raise DomainError(400, "invalid_content_length")
                delivered = False

                async def replay() -> Message:
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()

                await self.app(scope, replay, send_response)
        except DomainError as exc:
            if started:
                raise
            await respond(exc)
        except TimeoutError:
            if started:
                raise
            await respond(DomainError(503, "request_timeout"))
        except Exception:
            if started:
                raise
            await respond(DomainError(500, "internal_error"))
        finally:
            _logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": scope["method"]
                        if scope["method"]
                        in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                        else "OTHER",
                        "status": status,
                        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                    }
                )
            )
