"""SPEC-0001 B2a4b: controlled streams, no real login or network/TLS claim."""

import asyncio
import json
import logging
import time
import traceback
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import replace
from urllib.parse import parse_qsl

import httpx
import pytest

from torii_api.domain.errors import DomainError
from torii_api.security import credential_logging, oidc_exchange
from torii_api.security.oidc_exchange import OidcCredentialTransport
from torii_api.security.oidc_replies import TokenReply
from torii_api.security.oidc_requests import OAuthRequests
from torii_api.security.oidc_transport import RealmEndpoints
from torii_api.security.session_secrets import new_token

ISSUER = "https://localhost:19443/identity/realms/synthetic"
BACKCHANNEL = "http://identity:8080/identity/realms/synthetic"
ENDPOINTS = RealmEndpoints(ISSUER, BACKCHANNEL)
MARKER = "synthetic-private-exchange-marker-123456"
LOGGERS = (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)


@pytest.fixture(autouse=True)
def logging_policy():
    previous = {name: logging.getLogger(name).disabled for name in LOGGERS}
    configured = credential_logging._configured
    credential_logging.configure_credential_logging()
    yield
    credential_logging._configured = configured
    for name, disabled in previous.items():
        logging.getLogger(name).disabled = disabled


class Body(httpx.AsyncByteStream):
    def __init__(self, chunks=(), *, error=None, wait=None, close_error=None, close_wait=None):
        self.chunks = chunks
        self.error = error
        self.wait = wait
        self.close_error = close_error
        self.close_wait = close_wait
        self.started = asyncio.Event()
        self.close_entered = asyncio.Event()
        self.closed = 0
        self.reads = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.started.set()
        if self.wait is not None:
            await self.wait.wait()
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.error is not None:
            raise self.error

    async def aclose(self):
        self.closed += 1
        self.close_entered.set()
        if self.close_wait is not None:
            await self.close_wait.wait()
        if self.close_error is not None:
            raise self.close_error


def response(body, status=200, headers=None):
    return httpx.Response(
        status,
        headers=[("content-type", "application/json")] if headers is None else headers,
        stream=body,
    )


def success():
    return json.dumps({"access_token": MARKER, "id_token": MARKER, "token_type": "Bearer"}).encode()


def client(handler):
    return OidcCredentialTransport(
        ENDPOINTS, "client :+ż", MARKER, transport=httpx.MockTransport(handler)
    )


def deadline():
    return asyncio.get_running_loop().time() + 10


def safe(error, status=503):
    assert (error.status, error.code, error.pointers) == (
        status,
        "unauthorized" if status == 401 else "identity_unavailable",
        (),
    )
    assert error.__cause__ is None and error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert MARKER not in rendered and BACKCHANNEL not in rendered


def test_exchange_composes_existing_encoder_parser_and_exact_wire():
    async def scenario():
        body = Body([success()])
        seen = []
        transport = client(lambda request: (seen.append(request), response(body))[1])
        verifier = new_token()
        try:
            result = await transport.exchange(MARKER, verifier, deadline=deadline())
            assert type(result) is TokenReply and result.access_token == MARKER
            expected = OAuthRequests(ENDPOINTS, "client :+ż", MARKER).exchange(MARKER, verifier)
            request = seen[0]
            assert len(seen) == 1 and request.method == "POST"
            assert str(request.url) == expected.url
            assert request.content == expected.body
            assert request.headers["authorization"] == expected.authorization
            assert request.headers["content-type"] == "application/x-www-form-urlencoded"
            assert request.headers["accept"] == "application/json"
            assert request.headers["accept-encoding"] == "identity"
            assert set(request.headers) == {
                "host",
                "content-length",
                "authorization",
                "content-type",
                "accept",
                "accept-encoding",
            }
            assert set(request.extensions) == {"timeout"}
            assert request.extensions["timeout"] == {
                "connect": 2.0,
                "pool": 2.0,
                "read": 5.0,
                "write": 5.0,
            }
            assert dict(parse_qsl(request.content.decode()))["code_verifier"] == verifier
            assert all(
                value not in repr(transport) + str(transport) + repr(result)
                for value in (
                    MARKER,
                    ISSUER,
                    BACKCHANNEL,
                    verifier,
                    expected.authorization,
                )
            )
            assert body.closed == 1
        finally:
            await transport.aclose()
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation,status,body,expected",
    [
        (
            "exchange",
            400,
            b'{"error":"invalid_grant","error_description":"' + MARKER.encode() + b'"}',
            401,
        ),
        ("exchange", 400, b'{"error":"invalid_client"}', 503),
        ("exchange", 200, b'{"error":"invalid_grant"}', 503),
        ("exchange", 400, b'{"error":"invalid_grant","error":"invalid_grant"}', 503),
        ("exchange", 200, b"not-json", 503),
        ("revoke", 400, b'{"error":"invalid_grant"}', 503),
    ],
)
def test_only_strict_parser_invalid_grant_is_unauthorized(operation, status, body, expected):
    async def scenario():
        stream = Body([body])
        transport = client(lambda request: response(stream, status))
        try:
            with pytest.raises(DomainError) as caught:
                if operation == "exchange":
                    await transport.exchange("code", new_token(), deadline=deadline())
                else:
                    await transport.revoke("refresh", deadline=deadline())
            safe(caught.value, expected)
            assert stream.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body,headers",
    [
        (b"", []),
        (b"not JSON", []),
        (b"ok", [("content-type", "text/plain")]),
        (b"opaque", [("content-type", "application/octet-stream"), ("content-length", "0006")]),
    ],
)
def test_revoke_allows_empty_nonjson_and_has_exact_form(body, headers):
    async def scenario():
        stream = Body([body])
        seen = []
        transport = client(
            lambda request: (seen.append(request), response(stream, headers=headers))[1]
        )
        try:
            assert await transport.revoke("opaque+/=", deadline=deadline()) is None
            request = seen[0]
            assert str(request.url) == BACKCHANNEL + "/protocol/openid-connect/revoke"
            assert parse_qsl(request.content.decode()) == [
                ("token", "opaque+/="),
                ("token_type_hint", "refresh_token"),
            ]
            assert stream.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "operation,status",
    [
        (op, status)
        for op in ("exchange", "revoke")
        for status in (201, 204, 301, 302, 303, 307, 308, 401, 403, 404, 429, 500, 503)
    ],
)
def test_bad_status_never_reads_or_retries(operation, status):
    async def scenario():
        body = Body([MARKER.encode()])
        seen = []
        transport = client(
            lambda request: (
                seen.append(request),
                response(
                    body,
                    status,
                    [
                        ("location", "https://attacker.invalid/" + MARKER),
                        ("content-type", "garbage"),
                    ],
                ),
            )[1]
        )
        try:
            with pytest.raises(DomainError) as caught:
                if operation == "exchange":
                    await transport.exchange("code", new_token(), deadline=deadline())
                else:
                    await transport.revoke("refresh", deadline=deadline())
            safe(caught.value)
            assert len(seen) == 1 and body.reads == 0 and body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("content-type", "application/jwk-set+json")],
        [("content-type", "text/json")],
        [("content-type", "application/json; boundary=bad")],
        [("content-type", "application/json"), ("content-type", "application/json")],
        [("content-type", "application/json"), ("content-encoding", "gzip")],
        [("content-type", "application/json"), ("content-encoding", "identity, identity")],
        [("content-type", "application/json"), ("content-length", "65537")],
        [("content-type", "application/json"), ("content-length", "1"), ("content-length", "1")],
        [("content-type", "application/json"), ("content-length", "+1")],
        [("content-type", "application/json"), ("content-length", "1.0")],
    ],
)
def test_bad_token_headers_refused_before_body(headers):
    async def scenario():
        body = Body([success()])
        transport = client(lambda request: response(body, headers=headers))
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("code", new_token(), deadline=deadline())
            safe(caught.value)
            assert body.reads == 0 and body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "headers",
    [
        [("content-type", "a" * 257)],
        [("content-type", "a\tb")],
        [("content-type", "a"), ("content-type", "b")],
        [("content-encoding", "gzip")],
    ],
)
def test_revoke_header_limits(headers):
    async def scenario():
        body = Body([b"ok"])
        transport = client(lambda request: response(body, headers=headers))
        try:
            with pytest.raises(DomainError) as caught:
                await transport.revoke("refresh", deadline=deadline())
            safe(caught.value)
            assert body.reads == 0 and body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "size,declared,valid",
    [
        (65536, None, True),
        (65537, None, False),
        (2, "1", False),
        (2, "3", False),
        (2, "0002", True),
    ],
)
def test_stream_limit_and_actual_length(size, declared, valid):
    async def scenario():
        body = Body([b"x" * min(size, 65536), b"x" * max(0, size - 65536)])
        headers = [] if declared is None else [("content-length", declared)]
        transport = client(lambda request: response(body, headers=headers))
        try:
            if valid:
                await transport.revoke("refresh", deadline=deadline())
            else:
                with pytest.raises(DomainError) as caught:
                    await transport.revoke("refresh", deadline=deadline())
                safe(caught.value)
            assert body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value",
    [
        ("url", BACKCHANNEL + "/protocol/openid-connect/token?query"),
        ("url", BACKCHANNEL + "/protocol/openid-connect/token#fragment"),
        ("url", BACKCHANNEL + "/protocol/openid-connect/revoke"),
        ("url", "https://attacker.invalid/token"),
        ("url", None),
        ("authorization", "Basic YTpi\r\nX-Header: marker"),
        ("authorization", "basic YTpi"),
        ("authorization", "Basic YTpi="),
        ("authorization", "Basic YTpiOmM="),
        ("authorization", "Basic YWJj"),
        ("authorization", "Basic /zph"),
        ("authorization", "Basic " + "A" * 65536),
        ("authorization", b"Basic YTpi"),
        ("body", b""),
        ("body", b"a b"),
        ("body", b"a\n"),
        ("body", b"\xff"),
        ("body", b"x" * 65537),
        ("body", "a=b"),
    ],
    ids=lambda value: (
        f"{type(value).__name__}-{len(value)}"
        if isinstance(value, (str, bytes)) and len(value) > 100
        else None
    ),
)
def test_forged_dto_is_rejected_before_io(field, value):
    async def scenario():
        seen = []
        transport = client(lambda request: seen.append(request))
        dto = OAuthRequests(ENDPOINTS, "client", MARKER).exchange("code", new_token())
        try:
            with pytest.raises(DomainError) as caught:
                await transport._post(
                    "exchange", replace(dto, **{field: value}), deadline=deadline()
                )
            safe(caught.value)
            assert seen == []
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("operation,dto", [("GET", None), (None, None), ("exchange", object())])
def test_wrong_private_operation_or_dto(operation, dto):
    async def scenario():
        seen = []
        transport = client(lambda request: seen.append(request))
        try:
            with pytest.raises(DomainError) as caught:
                await transport._post(operation, dto, deadline=deadline())
            safe(caught.value)
            assert not seen
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("value", [None, True, False, -1, 0, float("nan"), float("inf"), 2**53])
def test_invalid_deadline_never_sends(value):
    async def scenario():
        seen = []
        transport = client(lambda request: seen.append(request))
        try:
            with pytest.raises(DomainError) as caught:
                await transport.revoke("refresh", deadline=value)
            safe(caught.value)
            assert not seen
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError,
        httpx.ReadError,
        httpx.WriteError,
        httpx.PoolTimeout,
        httpx.ReadTimeout,
        httpx.RemoteProtocolError,
        httpx.InvalidURL,
        OSError,
        RuntimeError,
    ],
)
def test_header_failure_safe_and_never_retried(failure):
    async def scenario():
        seen = []

        def handler(request):
            seen.append(request)
            raise failure(MARKER)

        transport = client(handler)
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("code", new_token(), deadline=deadline())
            safe(caught.value)
            assert len(seen) == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["headers", "body", "close"])
def test_provider_domain_401_is_never_own_unauthorized(stage):
    async def scenario():
        failure = DomainError(401, MARKER)
        body = Body(
            [success()],
            error=failure if stage == "body" else None,
            close_error=failure if stage == "close" else None,
        )

        def handler(request):
            if stage == "headers":
                raise failure
            return response(body)

        transport = client(handler)
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("code", new_token(), deadline=deadline())
            safe(caught.value)
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_guard_is_checked_before_encoder_and_immediately_before_send(monkeypatch):
    async def scenario():
        order = []

        def guard():
            order.append("guard")

        original = OAuthRequests.exchange

        def encode(self, code, verifier):
            order.append("encode")
            return original(self, code, verifier)

        def handler(request):
            order.append("send")
            return response(Body([success()]))

        monkeypatch.setattr(oidc_exchange, "assert_credential_logging", guard)
        monkeypatch.setattr(OAuthRequests, "exchange", encode)
        transport = client(handler)
        try:
            await transport.exchange("code", new_token(), deadline=deadline())
            assert order == ["guard", "encode", "guard", "send"]
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("at_encoder", [False, True])
def test_broken_guard_prevents_credentials_io_and_close_still_works(monkeypatch, at_encoder):
    async def scenario():
        seen = []
        if at_encoder:
            original = OAuthRequests.exchange

            def encode(self, code, verifier):
                dto = original(self, code, verifier)
                logging.getLogger("httpcore.http11").disabled = False
                return dto

            monkeypatch.setattr(OAuthRequests, "exchange", encode)
        else:
            logging.getLogger("httpx").disabled = False
        transport = client(lambda request: seen.append(request))
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("code", new_token(), deadline=deadline())
            safe(caught.value)
            assert not seen
        finally:
            await transport.aclose()
            await transport.aclose()

    asyncio.run(scenario())


def test_bad_code_401_preserved_and_closed_client_refuses_io():
    async def scenario():
        seen = []
        transport = client(lambda request: seen.append(request))
        with pytest.raises(DomainError) as caught:
            await transport.exchange("", "bad", deadline=deadline())
        safe(caught.value, 401)
        await transport.aclose()
        with pytest.raises(DomainError) as caught:
            await transport.revoke("refresh", deadline=deadline())
        safe(caught.value)
        assert not seen

    asyncio.run(scenario())


def test_missing_initialization_blocks_before_even_invalid_code(monkeypatch):
    async def scenario():
        seen = []
        transport = client(lambda request: seen.append(request))
        monkeypatch.setattr(credential_logging, "_configured", False)
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("", "bad", deadline=deadline())
            safe(caught.value)
            assert not seen
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("budget", [0.5, 100])
def test_work_cutoff_is_shared_caller_deadline_or_five_seconds(monkeypatch, budget):
    async def scenario():
        cutoffs = []
        original = asyncio.timeout_at

        def capture(cutoff):
            cutoffs.append(cutoff)
            return original(cutoff)

        monkeypatch.setattr(asyncio, "timeout_at", capture)
        transport = client(lambda request: response(Body([b""]), headers=[]))
        start = asyncio.get_running_loop().time()
        try:
            await transport.revoke("refresh", deadline=start + budget)
            assert len(cutoffs) == 1
            if budget < 5:
                assert cutoffs[0] == start + budget
            else:
                assert start + 5 <= cutoffs[0] < start + 5.2
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_expired_deadline_during_preparation_never_sends(monkeypatch):
    async def scenario():
        seen = []
        prepared = []
        original = oidc_exchange._validate_request

        def delayed_preparation(*args):
            original(*args)
            # Synchronous preparation cannot be interrupted by asyncio.timeout_at.
            time.sleep(0.15)
            prepared.append(True)

        def handler(request):
            seen.append("send")
            return response(Body([success()]))

        monkeypatch.setattr(oidc_exchange, "_validate_request", delayed_preparation)
        transport = client(handler)
        verifier = new_token()
        cutoff = asyncio.get_running_loop().time() + 0.1
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("code", verifier, deadline=cutoff)
            safe(caught.value)
            assert prepared == [True]
            assert asyncio.get_running_loop().time() >= cutoff
            assert seen == []
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_cookies_do_not_accumulate_in_sequential_or_parallel_requests():
    async def scenario():
        seen = []

        def handler(request):
            seen.append(request)
            return response(Body([b""]), headers=[("set-cookie", "private=" + MARKER + "; Path=/")])

        transport = client(handler)
        try:
            await transport.revoke("one", deadline=deadline())
            await asyncio.gather(*(transport.revoke("next", deadline=deadline()) for _ in range(3)))
            assert len(seen) == 4
            assert all("cookie" not in request.headers for request in seen)
            assert len(transport._client.cookies) == 0
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["headers", "body"])
def test_real_work_deadline_includes_headers_and_body(stage):
    async def scenario():
        seen = []
        waiting = asyncio.Event()
        body = Body([success()], wait=waiting if stage == "body" else None)

        async def handler(request):
            seen.append(request)
            if stage == "headers":
                await waiting.wait()
            return response(body)

        transport = client(handler)
        started = asyncio.get_running_loop().time()
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("code", new_token(), deadline=started + 0.06)
            safe(caught.value)
            assert asyncio.get_running_loop().time() - started < 0.7
            assert len(seen) == 1
            assert body.closed == (0 if stage == "headers" else 1)
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_deadline_checked_after_our_parser(monkeypatch):
    async def scenario():
        original = TokenReply.from_response

        def parse(status, body):
            result = original(status, body)
            monkeypatch.setattr(
                oidc_exchange,
                "_check_time",
                lambda cutoff: (_ for _ in ()).throw(DomainError(503, "identity_unavailable")),
            )
            return result

        monkeypatch.setattr(TokenReply, "from_response", parse)
        transport = client(lambda request: response(Body([success()])))
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange("code", new_token(), deadline=deadline())
            safe(caught.value)
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("close_error", [None, OSError(MARKER), DomainError(401, MARKER)])
def test_external_cancellation_wins_over_cleanup_failure(close_error):
    async def scenario():
        body = Body(wait=asyncio.Event(), close_error=close_error)
        transport = client(lambda request: response(body))
        task = asyncio.create_task(transport.exchange("code", new_token(), deadline=deadline()))
        try:
            await body.started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert body.closed == 1
            assert asyncio.all_tasks() == {asyncio.current_task()}
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_second_cancellation_shortens_cleanup_without_task_leak():
    async def scenario():
        body = Body(wait=asyncio.Event(), close_wait=asyncio.Event())
        transport = client(lambda request: response(body))
        task = asyncio.create_task(transport.exchange("code", new_token(), deadline=deadline()))
        try:
            await body.started.wait()
            task.cancel()
            await body.close_entered.wait()
            start = asyncio.get_running_loop().time()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert asyncio.get_running_loop().time() - start < 0.5
            assert body.closed == 1 and asyncio.all_tasks() == {asyncio.current_task()}
        finally:
            body.close_wait.set()
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", [OSError(MARKER), DomainError(401, MARKER)])
def test_ambient_caller_exception_is_not_mutated_or_rendered(failure):
    async def scenario():
        body = Body([success()], close_error=OSError(MARKER))
        transport = client(lambda request: response(body))
        try:
            try:
                raise failure
            except Exception as ambient:
                with pytest.raises(DomainError) as caught:
                    await transport.exchange("code", new_token(), deadline=deadline())
                error = caught.value
                assert error.status == 503 and error.__cause__ is None
                assert error.__context__ is None or error.__context__ is ambient
                assert error.__suppress_context__ is True
                assert MARKER not in "".join(traceback.format_exception(error))
                assert str(ambient) == MARKER
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["bad_status", "body_timeout", "cancel", "malformed_location"])
def test_hanging_cleanup_is_bounded_without_background_tasks(mode):
    async def scenario():
        body = Body(
            [success()],
            close_wait=asyncio.Event(),
            wait=asyncio.Event() if mode in ("body_timeout", "cancel") else None,
        )
        status = 302 if mode in ("bad_status", "malformed_location") else 200
        headers = [("content-type", "application/json")]
        if mode == "malformed_location":
            headers.append(("location", "https://999.1.1.1/" + MARKER))
        transport = client(lambda request: response(body, status, headers))
        start = asyncio.get_running_loop().time()
        task = asyncio.create_task(
            transport.exchange(
                "code", new_token(), deadline=start + (0.06 if mode == "body_timeout" else 5)
            )
        )
        try:
            if mode == "cancel":
                await body.started.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=1.7)
            else:
                with pytest.raises(DomainError) as caught:
                    await asyncio.wait_for(task, timeout=1.7)
                safe(caught.value)
            assert asyncio.get_running_loop().time() - start < 1.6
            assert body.closed == 1 and asyncio.all_tasks() == {asyncio.current_task()}
        finally:
            body.close_wait.set()
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await transport.aclose()

    asyncio.run(scenario())


def test_explicit_close_is_bounded_and_logically_final():
    class HangingTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.calls = 0

        async def handle_async_request(self, request):
            raise AssertionError("closed client sent")

        async def aclose(self):
            self.calls += 1
            await asyncio.Event().wait()

    async def scenario():
        injected = HangingTransport()
        transport = OidcCredentialTransport(ENDPOINTS, "client", MARKER, transport=injected)
        start = asyncio.get_running_loop().time()
        with pytest.raises(DomainError) as caught:
            await transport.aclose()
        safe(caught.value)
        assert asyncio.get_running_loop().time() - start < 1.6
        await transport.aclose()
        assert injected.calls == 1
        with pytest.raises(DomainError) as caught:
            await transport.revoke("refresh", deadline=deadline())
        safe(caught.value)

    asyncio.run(scenario())


def test_default_client_tls_environment_and_no_retries(monkeypatch):
    captured = {}
    original = httpx.AsyncClient

    def factory(**kwargs):
        captured.update(kwargs)
        kwargs["transport"] = httpx.MockTransport(lambda _: response(Body([b""])))
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    monkeypatch.setenv("HTTPS_PROXY", "http://private.invalid")
    monkeypatch.setenv("SSL_CERT_FILE", "/missing/private.pem")
    monkeypatch.setenv("NETRC", "/missing/netrc")

    async def scenario():
        transport = OidcCredentialTransport(ENDPOINTS, "client", MARKER)
        try:
            assert captured["verify"] is True and captured["trust_env"] is False
            assert captured["auth"] is None and captured["follow_redirects"] is False
            assert captured["transport"] is None
            assert captured["limits"].max_connections == 4
            assert captured["limits"].max_keepalive_connections == 2
            await transport.revoke("refresh", deadline=deadline())
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_provider_markers_absent_from_emitters_and_safe_event_schema(caplog):
    async def scenario():
        events = []

        class Capture(logging.Handler):
            def emit(self, record):
                events.append(record)

        handler = Capture()
        for name in LOGGERS:
            logging.getLogger(name).addHandler(handler)
        caplog.set_level(logging.INFO, logger="torii.identity")

        def provider(request):
            for name in LOGGERS:
                logging.getLogger(name).critical(MARKER, exc_info=ValueError(MARKER))
            return httpx.Response(
                400,
                stream=Body(
                    [b'{"error":"invalid_grant","error_description":"' + MARKER.encode() + b'"}']
                ),
                headers={"content-type": "application/json", "x-private": MARKER},
                extensions={"reason_phrase": MARKER.encode()},
            )

        transport = client(provider)
        try:
            with pytest.raises(DomainError) as caught:
                await transport.exchange(MARKER, new_token(), deadline=deadline())
            safe(caught.value, 401)
            assert not events and MARKER not in caplog.text
            records = [record for record in caplog.records if record.name == "torii.identity"]
            assert len(records) == 1
            record = records[0]
            assert record.event == "oidc_transport" and record.operation == "exchange"
            assert record.outcome == "unauthorized" and type(record.duration_ms) is int
            assert record.duration_ms >= 0 and record.exc_info is None
            assert record.getMessage() == "oidc_transport"
        finally:
            await transport.aclose()
            for name in LOGGERS:
                logging.getLogger(name).removeHandler(handler)

    asyncio.run(scenario())
