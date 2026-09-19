"""SPEC-0002 HTTP framing and cancellation at the ASGI boundary."""

import asyncio
import json

import pytest
from starlette.types import Message, Scope

from torii_api.http.middleware import EnvelopeMiddleware


def test_timeout_cancels_handler_before_response_and_returns_safe_problem() -> None:
    cancelled = False
    sent: list[Message] = []

    async def app(scope, receive, send):
        nonlocal cancelled
        try:
            await asyncio.sleep(5)
        finally:
            cancelled = True

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "headers": [(b"host", b"localhost:9443")]}
    asyncio.run(EnvelopeMiddleware(app, "localhost:9443", timeout=0.01)(scope, receive, send))
    assert cancelled
    assert sent[0]["status"] == 503
    assert json.loads(sent[1]["body"])["code"] == "request_timeout"


@pytest.mark.parametrize(
    "headers,body,status",
    [
        ([(b"host", b"localhost:9443"), (b"host", b"localhost:9443")], b"", 400),
        ([(b"content-length", b"-1")], b"", 400),
        ([(b"content-length", b"2"), (b"content-length", b"2")], b"{}", 400),
        ([(b"content-length", b"3")], b"{}", 400),
        ([(b"content-length", b"99999999999999999999999")], b"", 413),
    ],
)
def test_malformed_framing_does_not_dispatch(
    headers: list[tuple[bytes, bytes]], body: bytes, status: int
) -> None:
    sent: list[Message] = []

    async def app(scope, receive, send):
        pytest.fail("Malformed HTTP must not dispatch")

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    if not any(name == b"host" for name, _ in headers):
        headers = [(b"host", b"localhost:9443"), *headers]
    scope: Scope = {"type": "http", "method": "GET", "headers": headers}
    asyncio.run(EnvelopeMiddleware(app, "localhost:9443")(scope, receive, send))
    assert sent[0]["status"] == status
