"""SPEC-0001 B2a3 A3-01/02/03/04/05: fake HTTP to real RSA verification.

Only in-memory streams, keys and synthetic documents. This is not a test of
DNS, TLS, real connection pools or Keycloak login.
"""

import asyncio
import json
import traceback

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.api_jws import PyJWS

from torii_api.domain.errors import DomainError
from torii_api.security.oidc_cache import OidcKeyCache
from torii_api.security.oidc_tokens import TokenVerifier, token_key_id
from torii_api.security.oidc_transport import OidcMetadataTransport, RealmEndpoints

ISSUER = "https://metadata.example.invalid/identity/realms/synthetic"
BACKCHANNEL = "http://identity:8080/identity/realms/synthetic"
KID, CLIENT, AUDIENCE = "synthetic-key", "synthetic-client", "synthetic-api"
MARKER = "SYNTHETIC_CONFIDENTIAL_METADATA_MARKER"
EVIL = "https://attacker.invalid/" + MARKER


def encoded(value):
    return json.dumps(value, separators=(",", ":")).encode()


def discovery_document():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/protocol/openid-connect/auth",
        "token_endpoint": BACKCHANNEL + "/protocol/openid-connect/token",
        "jwks_uri": BACKCHANNEL + "/protocol/openid-connect/certs",
        "revocation_endpoint": BACKCHANNEL + "/protocol/openid-connect/revoke",
        "untrusted_ignored_url": EVIL,
    }


def jwks_document(private, kid=KID):
    key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    return {"keys": [key | {"kid": kid, "use": "sig", "alg": "RS256", "x5u": EVIL}]}


def token(private, kid=KID):
    return PyJWS().encode(
        encoded(
            {
                "iss": ISSUER,
                "sub": "synthetic-subject",
                "typ": "Bearer",
                "aud": AUDIENCE,
                "iat": 1000,
                "exp": 1300,
                "name": "Synthetic person",
                "roles": ["admin"],
            }
        ),
        private,
        algorithm="RS256",
        headers={"typ": "JWT", "kid": kid},
    )


@pytest.fixture(scope="module")
def material():
    return tuple(rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))


class TrackedStream(httpx.AsyncByteStream):
    def __init__(self, body, *, entered=None, release=None, close_failure=False):
        self.body = body
        self.entered = entered
        self.release = release
        self.close_failure = close_failure
        self.close_entered = False
        self.closed = False

    async def __aiter__(self):
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        for offset in range(0, len(self.body), 37):
            yield self.body[offset : offset + 37]

    async def aclose(self):
        self.close_entered = True
        await asyncio.sleep(0)
        if self.close_failure:
            raise httpx.ReadError(MARKER)
        self.closed = True


class MetadataProvider:
    """No pre-read Response(content/json): exercise the actual raw iterator."""

    def __init__(self, private):
        self.discovery = discovery_document()
        self.jwks = jwks_document(private)
        self.jwks_status = 200
        self.entered = None
        self.release = None
        self.close_failure = False
        self.requests = []
        self.streams = []

    async def __call__(self, request):
        self.requests.append(request)
        is_discovery = str(request.url) == BACKCHANNEL + "/.well-known/openid-configuration"
        assert is_discovery or str(request.url) == BACKCHANNEL + "/protocol/openid-connect/certs"
        stream = TrackedStream(
            encoded(self.discovery if is_discovery else self.jwks),
            entered=None if is_discovery else self.entered,
            release=None if is_discovery else self.release,
            close_failure=False if is_discovery else self.close_failure,
        )
        self.streams.append(stream)
        return httpx.Response(
            200 if is_discovery else self.jwks_status,
            headers=[
                ("Content-Type", "application/json"),
                ("Set-Cookie", f"synthetic_{len(self.requests)}={MARKER}; Path=/"),
            ],
            stream=stream,
        )


def transport_and_cache(provider):
    endpoints = RealmEndpoints(ISSUER, BACKCHANNEL)
    transport = OidcMetadataTransport(endpoints, transport=httpx.MockTransport(provider))
    return transport, OidcKeyCache(transport)


def assert_safe(error, status):
    assert type(error) is DomainError
    assert (error.status, error.code) == (
        status,
        "unauthorized" if status == 401 else "identity_unavailable",
    )
    assert error.__context__ is error.__cause__ is None
    rendered = "".join(traceback.format_exception(error))
    assert MARKER not in rendered and ISSUER not in rendered and BACKCHANNEL not in rendered


async def rejected(operation, status=503):
    with pytest.raises(DomainError) as caught:
        await operation
    assert_safe(caught.value, status)


def assert_no_cookie_or_external_request(provider):
    assert all("cookie" not in request.headers for request in provider.requests)
    assert all("authorization" not in request.headers for request in provider.requests)
    assert all(
        request.headers.get("accept-encoding") == "identity" for request in provider.requests
    )
    assert all(str(request.url).startswith(BACKCHANNEL + "/") for request in provider.requests)


def shifted_clock(monkeypatch):
    loop = asyncio.get_running_loop()
    real_clock = loop.time
    offset = [0.0]
    monkeypatch.setattr(loop, "time", lambda: real_clock() + offset[0])
    return loop, offset


def test_metadata_integration_contract_exists():
    assert callable(RealmEndpoints.validate_discovery)
    assert callable(OidcMetadataTransport.discovery)
    assert callable(OidcMetadataTransport.jwks)
    assert callable(OidcKeyCache.keys_for)


def test_raw_http_to_public_keys_to_real_rsa_and_tamper_rejection(material):
    async def scenario():
        private, wrong = material
        provider = MetadataProvider(private)
        transport, cache = transport_and_cache(provider)
        verifier = TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000)
        signed = token(private)
        try:
            keys = await cache.keys_for(
                (token_key_id(signed),), deadline=asyncio.get_running_loop().time() + 2
            )
            identity = verifier.verify_access(signed, keys)
            assert identity.subject == "synthetic-subject"
            assert not hasattr(identity, "roles") and not hasattr(identity, "can_create_project")
            with pytest.raises(DomainError) as caught:
                verifier.verify_access(token(wrong), keys)
            assert_safe(caught.value, 401)
            assert len(provider.requests) == 2
            assert all(stream.closed for stream in provider.streams)
            assert_no_cookie_or_external_request(provider)
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field",
    ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "revocation_endpoint"],
)
def test_malicious_discovery_blocks_jwks_and_cooldown_prevents_retry(material, field):
    async def scenario():
        provider = MetadataProvider(material[0])
        provider.discovery[field] = EVIL
        transport, cache = transport_and_cache(provider)
        loop = asyncio.get_running_loop()
        try:
            await rejected(cache.keys_for((KID,), deadline=loop.time() + 2))
            for n in range(8):
                await rejected(cache.keys_for((f"unknown-{n}",), deadline=loop.time() + 2))
            assert len(provider.requests) == 1
            assert provider.streams[0].closed
            assert_no_cookie_or_external_request(provider)
        finally:
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("rotation", ["same_kid", "removed_kid"])
def test_real_rotation_replaces_keys_while_returned_snapshot_stays_immutable(
    material, monkeypatch, rotation
):
    async def scenario():
        with monkeypatch.context() as patch:
            loop, offset = shifted_clock(patch)
            private, rotated = material
            provider = MetadataProvider(private)
            transport, cache = transport_and_cache(provider)
            verifier = TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000)
            try:
                old = await cache.keys_for((KID,), deadline=loop.time() + 2)
                new_kid = KID if rotation == "same_kid" else "rotated-key"
                provider.jwks = jwks_document(rotated, new_kid)
                offset[0] = 301 if rotation == "same_kid" else 31
                current = await cache.keys_for((new_kid,), deadline=loop.time() + 2)
                assert (
                    verifier.verify_access(token(rotated, new_kid), current).subject
                    == "synthetic-subject"
                )
                with pytest.raises(DomainError) as caught:
                    verifier.verify_access(token(private), current)
                assert_safe(caught.value, 401)
                assert verifier.verify_access(token(private), old).subject == "synthetic-subject"
                assert len(provider.requests) == (4 if rotation == "same_kid" else 3)
                if rotation == "removed_kid":
                    await rejected(cache.keys_for((KID,), deadline=loop.time() + 2), 401)
                    assert len(provider.requests) == 3
                assert all(stream.closed for stream in provider.streams)
                assert_no_cookie_or_external_request(provider)
            finally:
                await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [304, 503])
def test_failed_refresh_preserves_fresh_key_but_never_extends_snapshot_ttl(
    material, monkeypatch, status
):
    async def scenario():
        with monkeypatch.context() as patch:
            loop, offset = shifted_clock(patch)
            provider = MetadataProvider(material[0])
            transport, cache = transport_and_cache(provider)
            try:
                original = await cache.keys_for((KID,), deadline=loop.time() + 2)
                offset[0], provider.jwks_status = 31, status
                await rejected(cache.keys_for(("new-key",), deadline=loop.time() + 2))
                fresh = await cache.keys_for((KID,), deadline=loop.time() + 2)
                assert fresh.key_for(KID).public_numbers() == original.key_for(KID).public_numbers()
                for n in range(10):
                    await rejected(cache.keys_for((f"unknown-{n}",), deadline=loop.time() + 2))
                assert len(provider.requests) == 3
                offset[0] = 301
                await rejected(cache.keys_for((KID,), deadline=loop.time() + 2))
                assert len(provider.requests) == 5
                assert all(stream.closed for stream in provider.streams)
                assert_no_cookie_or_external_request(provider)
            finally:
                await transport.aclose()

    asyncio.run(scenario())


def test_concurrent_unknown_kid_storm_is_one_real_streamed_refresh(material):
    async def scenario():
        provider = MetadataProvider(material[0])
        provider.entered, provider.release = asyncio.Event(), asyncio.Event()
        transport, cache = transport_and_cache(provider)
        loop = asyncio.get_running_loop()
        tasks = []
        try:
            leader = asyncio.create_task(cache.keys_for((KID,), deadline=loop.time() + 2))
            tasks.append(leader)
            await asyncio.wait_for(provider.entered.wait(), timeout=1)
            tasks.extend(
                asyncio.create_task(cache.keys_for((f"unknown-{n}",), deadline=loop.time() + 2))
                for n in range(24)
            )
            await asyncio.sleep(0)
            provider.release.set()
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=1
            )
            assert results[0].key_for(KID) is not None
            for error in results[1:]:
                assert_safe(error, 401)
            assert len(provider.requests) == 2
            assert all(stream.closed for stream in provider.streams)
            assert_no_cookie_or_external_request(provider)
        finally:
            provider.release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await transport.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("close_failure", [False, True])
def test_cancelled_streaming_leader_propagates_cancel_and_preserves_global_cooldown(
    material, close_failure
):
    async def scenario():
        provider = MetadataProvider(material[0])
        provider.entered, provider.release = asyncio.Event(), asyncio.Event()
        provider.close_failure = close_failure
        transport, cache = transport_and_cache(provider)
        loop = asyncio.get_running_loop()
        tasks = []
        try:
            leader = asyncio.create_task(cache.keys_for((KID,), deadline=loop.time() + 2))
            tasks.append(leader)
            await asyncio.wait_for(provider.entered.wait(), timeout=1)
            cancelled_waiter = asyncio.create_task(cache.keys_for((KID,), deadline=loop.time() + 2))
            tasks.append(cancelled_waiter)
            await asyncio.sleep(0)
            cancelled_waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await cancelled_waiter
            assert not leader.done()
            tasks.extend(
                asyncio.create_task(cache.keys_for((f"unknown-{n}",), deadline=loop.time() + 2))
                for n in range(8)
            )
            await asyncio.sleep(0)
            leader.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(leader, timeout=1)
            results = await asyncio.wait_for(
                asyncio.gather(*tasks[2:], return_exceptions=True), timeout=1
            )
            for error in results:
                assert_safe(error, 503)
            await rejected(cache.keys_for((KID,), deadline=loop.time() + 2))
            assert len(provider.requests) == 2
            assert provider.streams[0].closed and provider.streams[1].close_entered
            if not close_failure:
                assert provider.streams[1].closed
        finally:
            provider.release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await transport.aclose()

    asyncio.run(scenario())


def test_real_waiter_deadline_expires_without_cancelling_streaming_leader(material):
    async def scenario():
        provider = MetadataProvider(material[0])
        provider.entered, provider.release = asyncio.Event(), asyncio.Event()
        transport, cache = transport_and_cache(provider)
        loop = asyncio.get_running_loop()
        leader = asyncio.create_task(cache.keys_for((KID,), deadline=loop.time() + 2))
        try:
            await asyncio.wait_for(provider.entered.wait(), timeout=1)
            started = loop.time()
            await asyncio.wait_for(
                rejected(cache.keys_for((KID,), deadline=started + 0.03)), timeout=0.5
            )
            assert loop.time() - started < 0.5
            assert not leader.done()
            provider.release.set()
            snapshot = await asyncio.wait_for(leader, timeout=1)
            assert snapshot.key_for(KID) is not None
            assert len(provider.requests) == 2 and all(stream.closed for stream in provider.streams)
        finally:
            provider.release.set()
            if not leader.done():
                leader.cancel()
            await asyncio.gather(leader, return_exceptions=True)
            await transport.aclose()

    asyncio.run(scenario())
