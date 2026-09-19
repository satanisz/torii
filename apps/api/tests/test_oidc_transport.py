"""SPEC-0001 B2a3 A3-01/02: fake HTTP streaming, not TLS/IdP/network E2E."""

import asyncio
import json
import traceback
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import FrozenInstanceError
from typing import cast

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from torii_api.domain.errors import DomainError
from torii_api.security import oidc_transport
from torii_api.security.oidc_transport import OidcMetadataTransport, RealmEndpoints

ISSUER = "https://localhost:9443/identity/realms/torii-dev"
BACKCHANNEL = "http://identity:8080/identity/realms/torii-dev"
MARKER = "SYNTHETIC_PRIVATE_TRANSPORT_MARKER"


def metadata(**changes: object) -> bytes:
    return json.dumps(
        {
            "issuer": ISSUER,
            "authorization_endpoint": ISSUER + "/protocol/openid-connect/auth",
            "token_endpoint": ISSUER + "/protocol/openid-connect/token",
            "jwks_uri": ISSUER + "/protocol/openid-connect/certs",
            "revocation_endpoint": ISSUER + "/protocol/openid-connect/revoke",
        }
        | changes
    ).encode()


def assert_safe(error: DomainError, *, ambient: BaseException | None = None) -> None:
    assert (error.status, error.code, error.pointers) == (503, "identity_unavailable", ())
    assert error.__cause__ is None
    assert error.__context__ is None or (ambient is not None and error.__context__ is ambient)
    if ambient is not None:
        assert error.__suppress_context__ is True
    rendered = "".join(traceback.format_exception(error))
    assert MARKER not in rendered
    assert ISSUER not in str(error)
    assert BACKCHANNEL not in repr(error)


class Body(httpx.AsyncByteStream):
    def __init__(
        self,
        chunks: list[bytes],
        *,
        error: Exception | None = None,
        wait: asyncio.Event | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.chunks = chunks
        self.error = error
        self.wait = wait
        self.close_error = close_error
        self.started = asyncio.Event()
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

    async def aclose(self) -> None:
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


def response(
    body: Body, *, status: int = 200, headers: list[tuple[str, str]] | None = None
) -> httpx.Response:
    return httpx.Response(
        status, headers=headers or [("Content-Type", "application/json")], stream=body
    )


@pytest.mark.parametrize(
    "issuer,backchannel",
    [
        (ISSUER, BACKCHANNEL),
        ("https://localhost/identity/realms/a", "https://idp.internal/identity/realms/a"),
        ("https://127.0.0.1/identity/realms/a", "http://identity/identity/realms/a"),
        ("https://xn--a.example/identity/realms/a", "https://a-b.example:65535/identity/realms/a"),
    ],
)
def test_endpoints_accept_only_trusted_profile_and_are_immutable(
    issuer: str, backchannel: str
) -> None:
    endpoints = RealmEndpoints(issuer, backchannel)
    assert endpoints.discovery_url == backchannel + "/.well-known/openid-configuration"
    assert endpoints.jwks_url == backchannel + "/protocol/openid-connect/certs"
    assert repr(endpoints) == "RealmEndpoints()"
    with pytest.raises(FrozenInstanceError):
        endpoints.issuer = "other"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        True,
        b"https://localhost",
        "",
        "a" * 2049,
        ISSUER.replace("https", "http"),
        ISSUER.replace("https", "HTTPS"),
        ISSUER.replace("localhost", "LOCALHOST"),
        ISSUER.replace("localhost", "user@localhost"),
        ISSUER.replace("localhost", "user:pass@localhost"),
        ISSUER + "?",
        ISSUER + "#",
        ISSUER + "?a=b",
        ISSUER + "/",
        ISSUER.replace("torii-dev", "a/b"),
        ISSUER.replace("torii-dev", "."),
        ISSUER.replace("torii-dev", ".."),
        ISSUER.replace("torii-dev", "%2e%2e"),
        ISSUER.replace("torii-dev", "a\\b"),
        ISSUER.replace("torii-dev", "a b"),
        ISSUER.replace("torii-dev", "ą"),
        ISSUER.replace("torii-dev", "a" * 129),
        ISSUER.replace("localhost", "[::1]"),
        ISSUER.replace("localhost", "-host"),
        ISSUER.replace("localhost", "host-"),
        ISSUER.replace("localhost", "host..name"),
        ISSUER.replace("localhost", "host."),
        ISSUER.replace("localhost", "a" * 64),
        ISSUER.replace(":9443", ":0"),
        ISSUER.replace(":9443", ":09443"),
        ISSUER.replace(":9443", ":65536"),
        ISSUER.replace(":9443", ":+443"),
        ISSUER + "\n",
    ],
    ids=lambda value: type(value).__name__ if not isinstance(value, str) else None,
)
def test_rejects_unsafe_or_noncanonical_issuer(bad: object) -> None:
    with pytest.raises(DomainError) as caught:
        RealmEndpoints(cast(str, bad), BACKCHANNEL)
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "bad",
    [
        BACKCHANNEL.replace("identity:8080", "localhost:8080"),
        BACKCHANNEL.replace("identity:8080", "identity.evil:8080"),
        BACKCHANNEL.replace("torii-dev", "other-realm"),
        BACKCHANNEL.replace("identity:8080", "Identity:8080"),
        BACKCHANNEL + "?",
        BACKCHANNEL + "#",
        BACKCHANNEL.replace("http", "ftp"),
    ],
)
def test_backchannel_http_host_and_realm_are_exact(bad: str) -> None:
    with pytest.raises(DomainError) as caught:
        RealmEndpoints(ISSUER, bad)
    assert_safe(caught.value)


def test_discovery_validates_exact_public_or_internal_endpoints() -> None:
    endpoints = RealmEndpoints(ISSUER, BACKCHANNEL)
    endpoints.validate_discovery(metadata())
    endpoints.validate_discovery(
        metadata(
            token_endpoint=BACKCHANNEL + "/protocol/openid-connect/token",
            jwks_uri=BACKCHANNEL + "/protocol/openid-connect/certs",
            revocation_endpoint=BACKCHANNEL + "/protocol/openid-connect/revoke",
            jku="https://never-fetch.invalid/ignored",
        )
    )


@pytest.mark.parametrize(
    "field",
    ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "revocation_endpoint"],
)
@pytest.mark.parametrize("replacement", [None, True, [], "https://evil.invalid/" + MARKER])
def test_discovery_rejects_wrong_endpoints_and_types(field: str, replacement: object) -> None:
    with pytest.raises(DomainError) as caught:
        RealmEndpoints(ISSUER, BACKCHANNEL).validate_discovery(metadata(**{field: replacement}))
    assert_safe(caught.value)


def test_discovery_rejects_duplicate_keys_missing_fields_and_internal_auth() -> None:
    endpoints = RealmEndpoints(ISSUER, BACKCHANNEL)
    cases = [
        b"{}",
        metadata()[:-1] + b',"issuer":"other"}',
        metadata(authorization_endpoint=BACKCHANNEL + "/protocol/openid-connect/auth"),
    ]
    for data in cases:
        with pytest.raises(DomainError) as caught:
            endpoints.validate_discovery(data)
        assert_safe(caught.value)


def test_get_targets_headers_timeouts_and_idempotent_close() -> None:
    async def scenario() -> None:
        body = Body([metadata()])
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return response(body)

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(handler)
        )
        try:
            assert (
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 10) is None
            )
            assert body.closed == 1
            assert len(seen) == 1
            request = seen[0]
            assert request.method == "GET"
            assert str(request.url) == BACKCHANNEL + "/.well-known/openid-configuration"
            assert request.headers["accept-encoding"] == "identity"
            assert "authorization" not in request.headers and "cookie" not in request.headers
            assert request.extensions["timeout"] == {
                "connect": 2.0,
                "pool": 2.0,
                "read": 5.0,
                "write": 5.0,
            }
            assert ISSUER not in repr(transport) and BACKCHANNEL not in repr(transport)
        finally:
            await transport.aclose()
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status", [201, 204, 301, 302, 303, 304, 307, 308, 400, 401, 404, 429, 500, 503]
)
def test_non200_never_follows_redirect_or_reads_body(status: int) -> None:
    async def scenario() -> None:
        body = Body([MARKER.encode()])
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return response(
                body,
                status=status,
                headers=[
                    ("Content-Type", "application/json"),
                    ("Location", "https://never-fetch.invalid"),
                ],
            )

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(handler)
        )
        try:
            with pytest.raises(DomainError) as caught:
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            assert_safe(caught.value)
            assert len(seen) == 1 and body.reads == 0 and body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/jwk-set+json",
        'Application/JSON ; Charset = "UTF-8"',
        "application/json;charset=utf-8",
    ],
)
def test_content_type_allowed_forms(content_type: str) -> None:
    async def scenario() -> None:
        body = Body([metadata()])
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(
                lambda request: response(
                    body, headers=[("content-type", content_type), ("content-encoding", "identity")]
                )
            ),
        )
        try:
            await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            assert body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "headers",
    [
        [("x-no-type", "missing")],
        [("content-type", "text/html")],
        [("content-type", "application/json"), ("Content-Type", "application/json")],
        [("content-type", "application/json, application/json")],
        [("content-type", "application/json;charset=utf-16")],
        [("content-type", "application/json;charset=utf-8;charset=utf-8")],
        [("content-type", "application/json;boundary=other")],
        [("content-type", "application/json; charset='utf-8'")],
        [("content-type", "application/json;")],
        *[
            [("content-type", "application/json"), ("content-encoding", encoding)]
            for encoding in ["gzip", "deflate", "br", "identity, identity", ""]
        ],
        [
            ("content-type", "application/json"),
            ("content-encoding", "identity"),
            ("Content-Encoding", "identity"),
        ],
        *[
            [("content-type", "application/json"), ("content-length", length)]
            for length in ["-1", "+1", " 1", "1 ", "65537", "1, 1", "", "abc", "1.0", "9" * 5000]
        ],
        [("content-type", "application/json"), ("content-length", "1"), ("Content-Length", "1")],
    ],
)
def test_bad_headers_rejected_before_body_or_decompression(headers: list[tuple[str, str]]) -> None:
    async def scenario() -> None:
        body = Body([b"not-even-valid-gzip"])
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(lambda request: response(body, headers=headers)),
        )
        try:
            with pytest.raises(DomainError) as caught:
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            assert_safe(caught.value)
            assert body.reads == 0 and body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("oversized", [False, True])
def test_streaming_limit_is_actual_bytes_not_content_length(oversized: bool) -> None:
    async def scenario() -> None:
        value = json.loads(metadata()) | {"padding": ""}
        remaining = 65536 - len(json.dumps(value).encode())
        value["padding"] = "a" * (remaining + int(oversized))
        raw = json.dumps(value).encode()
        body = Body([raw[:32000], raw[32000:64000], raw[64000:]])
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(
                lambda request: response(
                    body, headers=[("content-type", "application/json"), ("content-length", "1")]
                )
            ),
        )
        try:
            if oversized:
                with pytest.raises(DomainError) as caught:
                    await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
                assert_safe(caught.value)
            else:
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            assert body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "deadline",
    [None, True, "100", float("nan"), float("inf"), -1, 0, 2**53, 10**500],
    ids=["null", "bool", "str", "nan", "inf", "negative", "expired", "range", "large-int"],
)
def test_invalid_or_expired_deadline_refuses_before_io(deadline: object) -> None:
    async def scenario() -> None:
        calls = []
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(lambda request: calls.append(request)),
        )
        try:
            with pytest.raises(DomainError) as caught:
                await transport.discovery(deadline=deadline)
            assert_safe(caught.value)
            assert not calls
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure",
    [
        httpx.PoolTimeout,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        OSError,
        ValueError,
    ],
)
def test_headers_io_faults_are_safe_and_not_retried(failure: type[Exception]) -> None:
    async def scenario() -> None:
        calls = []

        def fail(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            raise failure(MARKER)

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(fail)
        )
        try:
            with pytest.raises(DomainError) as caught:
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            assert_safe(caught.value)
            assert len(calls) == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_body_timeout_and_read_error_close_response() -> None:
    async def scenario() -> None:
        for body in [Body([], wait=asyncio.Event()), Body([], error=httpx.ReadError(MARKER))]:
            transport = OidcMetadataTransport(
                RealmEndpoints(ISSUER, BACKCHANNEL),
                transport=httpx.MockTransport(lambda request, current=body: response(current)),
            )
            try:
                with pytest.raises(DomainError) as caught:
                    await transport.discovery(deadline=asyncio.get_running_loop().time() + 0.02)
                assert_safe(caught.value)
                assert body.closed == 1
            finally:
                await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("close_failure", [None, OSError(MARKER)])
def test_external_cancellation_survives_close_error(close_failure: Exception | None) -> None:
    async def scenario() -> None:
        body = Body([], wait=asyncio.Event(), close_error=close_failure)
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(lambda request: response(body)),
        )
        try:
            task = asyncio.create_task(
                transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            )
            await body.started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert body.closed == 1
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_provider_cookies_never_accumulate_or_go_on_wire() -> None:
    async def scenario() -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return response(
                Body([metadata()]),
                headers=[
                    ("content-type", "application/json"),
                    ("set-cookie", f"provider-{len(seen)}={MARKER}; Path=/"),
                ],
            )

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(handler)
        )
        try:
            for _ in range(2):
                await asyncio.gather(
                    *(
                        transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
                        for _ in range(12)
                    )
                )
            assert len(seen) == 24
            assert all("cookie" not in request.headers for request in seen)
            assert len(transport._client.cookies) == 0
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_trust_env_false_configures_verified_tls_without_ambient_proxy_or_ca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://never-connect.invalid:1")
    monkeypatch.setenv("SSL_CERT_FILE", "missing-synthetic-ca-path")
    monkeypatch.setenv("SSL_CERT_DIR", "missing-synthetic-ca-directory")

    async def scenario() -> None:
        # Creating/closing the default transport opens no connections.
        transport = OidcMetadataTransport(RealmEndpoints(ISSUER, BACKCHANNEL))
        assert transport._client.trust_env is False
        pool = transport._client._transport._pool
        assert pool._max_connections == 4 and pool._max_keepalive_connections == 2
        assert pool._ssl_context.check_hostname is True
        assert not transport._client._mounts
        await transport.aclose()

    asyncio.run(scenario())


def test_jwks_returns_issuer_bound_library_keys() -> None:
    import jwt

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())) | {"kid": "key"}

    async def scenario() -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return response(Body([json.dumps({"keys": [jwk]}).encode()]))

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(handler)
        )
        try:
            keys = await transport.jwks(deadline=asyncio.get_running_loop().time() + 10)
            assert (
                keys.issuer == ISSUER
                and keys.key_for("key").public_numbers() == private.public_key().public_numbers()
            )
            assert seen == [BACKCHANNEL + "/protocol/openid-connect/certs"]
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_operation_deadline_is_earlier_of_caller_and_five_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        real_timeout_at = asyncio.timeout_at
        cutoffs: list[float] = []

        def record_timeout(deadline: float):
            cutoffs.append(deadline)
            return real_timeout_at(deadline)

        monkeypatch.setattr(oidc_transport.asyncio, "timeout_at", record_timeout)
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(lambda request: response(Body([metadata()]))),
        )
        try:
            now = asyncio.get_running_loop().time()
            await transport.discovery(deadline=now + 10)
            assert now + 5 <= cutoffs[0] <= now + 5.1
            deadline = asyncio.get_running_loop().time() + 1
            await transport.discovery(deadline=deadline)
            assert cutoffs[1] == deadline
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_budget_is_checked_after_synchronous_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        real_clock = loop.time
        real_validate = RealmEndpoints.validate_discovery
        offset = 0.0

        def validate_after_budget(self: RealmEndpoints, data: bytes) -> None:
            nonlocal offset
            real_validate(self, data)
            offset = 6.0

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(lambda request: response(Body([metadata()]))),
        )
        try:
            with monkeypatch.context() as patch:
                patch.setattr(loop, "time", lambda: real_clock() + offset)
                patch.setattr(RealmEndpoints, "validate_discovery", validate_after_budget)
                with pytest.raises(DomainError) as caught:
                    await transport.discovery(deadline=real_clock() + 10)
                assert_safe(caught.value)
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_headers_deadline_is_active_not_only_checked_after_return() -> None:
    async def scenario() -> None:
        started = asyncio.Event()

        async def blocked_headers(request: httpx.Request) -> httpx.Response:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(blocked_headers)
        )
        try:
            with pytest.raises(DomainError) as caught:
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 0.02)
            assert_safe(caught.value)
            assert started.is_set()
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_lifecycle_errors_are_safe_and_closed_client_never_sends() -> None:
    class FailingClose(httpx.MockTransport):
        async def aclose(self) -> None:
            raise OSError(MARKER)

    async def scenario() -> None:
        seen = []
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=FailingClose(lambda request: seen.append(request)),
        )
        with pytest.raises(DomainError) as caught:
            await transport.aclose()
        assert_safe(caught.value)
        await transport.aclose()
        with pytest.raises(DomainError) as caught:
            await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
        assert_safe(caught.value)
        assert not seen

    asyncio.run(scenario())


class HangingCloseBody(Body):
    def __init__(self, chunks: list[bytes], *, wait: asyncio.Event | None = None) -> None:
        super().__init__(chunks, wait=wait)
        self.close_entered = asyncio.Event()
        self.close_release = asyncio.Event()
        self.close_completed = False

    async def aclose(self) -> None:
        self.closed += 1
        self.close_entered.set()
        await self.close_release.wait()
        self.close_completed = True


@pytest.mark.parametrize("mode", ["success", "body-timeout", "external-cancel", "second-cancel"])
def test_hanging_response_close_is_bounded_and_never_claims_success(mode: str) -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        body = HangingCloseBody(
            [metadata()] if mode == "success" else [],
            wait=None if mode == "success" else asyncio.Event(),
        )
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(lambda request: response(body)),
        )
        deadline = loop.time() + (0.02 if mode == "body-timeout" else 10)
        task = asyncio.create_task(transport.discovery(deadline=deadline))
        try:
            if "cancel" in mode:
                await body.started.wait()
                task.cancel()
            await body.close_entered.wait()
            started = loop.time()
            if mode == "second-cancel":
                task.cancel()
            if "cancel" in mode:
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=1.6)
            else:
                with pytest.raises(DomainError) as caught:
                    await asyncio.wait_for(task, timeout=1.6)
                assert_safe(caught.value)
            assert loop.time() - started < 1.5
            assert body.closed == 1 and body.close_completed is False
            assert task.done()
            assert asyncio.all_tasks() == {asyncio.current_task()}
        finally:
            body.close_release.set()
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await transport.aclose()

    asyncio.run(scenario())


def test_hanging_client_close_is_bounded_and_logically_closed() -> None:
    class HangingClose(httpx.MockTransport):
        def __init__(self) -> None:
            self.seen: list[httpx.Request] = []
            self.closed = 0
            self.close_release = asyncio.Event()
            super().__init__(lambda request: self.seen.append(request))

        async def aclose(self) -> None:
            self.closed += 1
            await self.close_release.wait()

    async def scenario() -> None:
        wire = HangingClose()
        transport = OidcMetadataTransport(RealmEndpoints(ISSUER, BACKCHANNEL), transport=wire)
        started = asyncio.get_running_loop().time()
        try:
            with pytest.raises(DomainError) as caught:
                await asyncio.wait_for(transport.aclose(), timeout=1.6)
        finally:
            wire.close_release.set()
        assert_safe(caught.value)
        assert asyncio.get_running_loop().time() - started < 1.5
        await transport.aclose()
        assert wire.closed == 1
        with pytest.raises(DomainError) as caught:
            await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
        assert_safe(caught.value)
        assert not wire.seen
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(scenario())


def test_invalid_ipv4_request_is_safe_before_transport_io() -> None:
    async def scenario() -> None:
        seen = []
        endpoints = RealmEndpoints(ISSUER, "https://999.1.1.1/identity/realms/torii-dev")
        transport = OidcMetadataTransport(
            endpoints, transport=httpx.MockTransport(lambda request: seen.append(request))
        )
        try:
            with pytest.raises(DomainError) as caught:
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            assert_safe(caught.value)
            assert not seen
        finally:
            await transport.aclose()

    asyncio.run(scenario())


def test_injected_invalid_url_exception_is_sanitized() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.InvalidURL(MARKER)

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(handler)
        )
        try:
            with pytest.raises(DomainError) as caught:
                await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
            assert_safe(caught.value)
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_malformed_location_internal_httpx_close_is_also_bounded(cancel: bool) -> None:
    async def scenario() -> None:
        body = HangingCloseBody([])
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return response(
                body,
                status=302,
                headers=[
                    ("content-type", "application/json"),
                    ("location", "https://999.1.1.1/" + MARKER),
                ],
            )

        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL), transport=httpx.MockTransport(handler)
        )
        task = asyncio.create_task(
            transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
        )
        try:
            await body.close_entered.wait()
            started = asyncio.get_running_loop().time()
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=1.6)
            else:
                with pytest.raises(DomainError) as caught:
                    await asyncio.wait_for(task, timeout=1.6)
                assert_safe(caught.value)
            assert asyncio.get_running_loop().time() - started < 1.5
            assert body.closed == 1 and not body.close_completed
            assert len(seen) == 1 and body.reads == 0
            assert asyncio.all_tasks() == {asyncio.current_task()}
        finally:
            body.close_release.set()
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("hanging", [False, True])
def test_ambient_handled_cancellation_never_hides_new_close_failure(hanging: bool) -> None:
    async def scenario() -> None:
        body = (
            HangingCloseBody([metadata()])
            if hanging
            else Body([metadata()], close_error=OSError(MARKER))
        )
        transport = OidcMetadataTransport(
            RealmEndpoints(ISSUER, BACKCHANNEL),
            transport=httpx.MockTransport(lambda request: response(body)),
        )
        try:
            try:
                raise asyncio.CancelledError(MARKER)
            except asyncio.CancelledError as ambient:
                # No pending cancellation: this is a new, valid operation in a handler.
                assert asyncio.current_task().cancelling() == 0
                with pytest.raises(DomainError) as caught:
                    await transport.discovery(deadline=asyncio.get_running_loop().time() + 10)
                assert_safe(caught.value, ambient=ambient)
            assert body.closed == 1
        finally:
            if isinstance(body, HangingCloseBody):
                body.close_release.set()
            await transport.aclose()

    asyncio.run(scenario())
