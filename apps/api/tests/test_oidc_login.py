"""SPEC-0001 B2a4c unit proofs; fake store does not prove PostgreSQL commit.

JWT signatures, cache and HTTP adapters are real; the database and network are
controlled. Separate integration tests cover PostgreSQL transactions/rotation.
"""

import asyncio
import base64
import hashlib
import json
import logging
import math
import threading
import time
import traceback
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from unittest.mock import Mock
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from jwt.api_jws import PyJWS
from sqlalchemy import Engine

from torii_api.application import oidc_login
from torii_api.application.identity_store import (
    ConsumedFlow,
    Flow,
    IdentityStore,
    NewSession,
    Principal,
    RevokedSession,
)
from torii_api.application.oidc_login import LoginStart, OidcLoginService
from torii_api.domain.errors import DomainError
from torii_api.security import credential_logging
from torii_api.security.oidc_cache import OidcKeyCache
from torii_api.security.oidc_exchange import OidcCredentialTransport
from torii_api.security.oidc_tokens import TokenVerifier
from torii_api.security.oidc_transport import OidcMetadataTransport
from torii_api.security.session_secrets import new_token, token_hash

MARKER = "synthetic-private-login-marker-123456"
OIDC = "/protocol/openid-connect/"


@pytest.fixture(autouse=True)
def logging_policy():
    previous = {
        name: logging.getLogger(name).disabled
        for name in credential_logging.CREDENTIAL_LOGGER_NAMES
    }
    configured = credential_logging._configured
    credential_logging.configure_credential_logging()
    yield
    credential_logging._configured = configured
    for name, disabled in previous.items():
        logging.getLogger(name).disabled = disabled


@pytest.fixture(scope="module")
def signing_keys():
    return {
        kid: rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for kid in ("id-key", "access-key")
    }


class Body(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.value


def response(value, status=200):
    return httpx.Response(
        status,
        headers={"content-type": "application/json"},
        stream=Body(json.dumps(value).encode()),
    )


class Transport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.closes = 0
        self.close_error = None
        self.close_entered = asyncio.Event()
        self.close_release = None

    async def aclose(self):
        self.closes += 1
        self.close_entered.set()
        if self.close_release is not None:
            await self.close_release.wait()
        if self.close_error is not None:
            raise self.close_error


class Store:
    """Behavioral double only: no claim about transactions or durability."""

    def __init__(self):
        self.flow = Flow(new_token(), new_token(), new_token(), new_token())
        self.session = NewSession(
            new_token(),
            new_token(),
            Principal(uuid4(), MARKER, False),
            datetime(2030, 1, 1, tzinfo=UTC),
        )
        self.revoked = RevokedSession(MARKER + "-refresh", False)
        self.calls = []
        self.threads = []
        self.consumed = False
        self.lock = threading.Lock()

    def record(self, *call):
        self.calls.append(call)
        self.threads.append(threading.get_ident())

    def create_flow(self):
        self.record("flow")
        return self.flow

    def consume_flow(self, state, browser):
        token_hash(state)
        token_hash(browser)
        self.record("consume", state, browser)
        with self.lock:
            if self.consumed or state != self.flow.state or browser != self.flow.browser:
                raise DomainError(401, "unauthorized")
            self.consumed = True
            return ConsumedFlow(token_hash(self.flow.nonce), self.flow.verifier)

    def create_session(self, identity, previous_session=None, refresh_token=None):
        self.record("create", identity, previous_session, refresh_token)
        return self.session

    def revoke_session(self, session_id):
        self.record("revoke", session_id)
        return self.revoked


class Harness:
    def __init__(self, settings, signing_keys):
        self.settings = settings
        self.keys = signing_keys
        self.store = Store()
        self.engine = Mock(spec=Engine)
        self.gets = []
        self.posts = []
        self.token_override = None
        self.token_error = None
        self.revoke_error = None
        self.metadata_error = None
        self.metadata = Transport(self.get)
        self.credentials = Transport(self.post)
        self.service = OidcLoginService(
            self.engine,
            settings,
            metadata_transport=self.metadata,
            credential_transport=self.credentials,
        )
        self.service._store = self.store
        self.service._verifier._clock = lambda: 1000
        self.with_at_hash = True

    def tokens(self):
        access = PyJWS().encode(
            json.dumps(
                {
                    "iss": self.settings.oidc_issuer,
                    "sub": MARKER,
                    "typ": "Bearer",
                    "aud": self.settings.oidc_audience,
                    "iat": 1000,
                    "exp": 1300,
                    "azp": self.settings.oidc_client_id,
                }
            ).encode(),
            self.keys["access-key"],
            algorithm="RS256",
            headers={"kid": "access-key"},
        )
        claims = {
            "iss": self.settings.oidc_issuer,
            "sub": MARKER,
            "typ": "ID",
            "aud": self.settings.oidc_client_id,
            "iat": 1000,
            "exp": 1300,
            "nonce": self.store.flow.nonce,
            "name": MARKER,
            "roles": ["admin"],
            "can_create_project": True,
        }
        if self.with_at_hash:
            claims["at_hash"] = (
                base64.urlsafe_b64encode(hashlib.sha256(access.encode()).digest()[:16])
                .decode()
                .rstrip("=")
            )
        identity = PyJWS().encode(
            json.dumps(claims).encode(),
            self.keys["id-key"],
            algorithm="RS256",
            headers={"kid": "id-key"},
        )
        return {
            "id_token": identity,
            "access_token": access,
            "token_type": "Bearer",
            "refresh_token": MARKER + "-refresh",
        }

    def get(self, request):
        self.gets.append(request)
        assert request.method == "GET" and "authorization" not in request.headers
        if self.metadata_error is not None:
            raise self.metadata_error
        if str(request.url).endswith("/.well-known/openid-configuration"):
            return response(
                {
                    "issuer": self.settings.oidc_issuer,
                    "authorization_endpoint": self.settings.oidc_issuer + OIDC + "auth",
                    "token_endpoint": self.settings.oidc_backchannel_url + OIDC + "token",
                    "jwks_uri": self.settings.oidc_backchannel_url + OIDC + "certs",
                    "revocation_endpoint": self.settings.oidc_backchannel_url + OIDC + "revoke",
                }
            )
        assert str(request.url) == self.settings.oidc_backchannel_url + OIDC + "certs"
        return response(
            {
                "keys": [
                    json.loads(RSAAlgorithm.to_jwk(key.public_key())) | {"kid": kid}
                    for kid, key in self.keys.items()
                ]
            }
        )

    def post(self, request):
        self.posts.append(request)
        assert request.method == "POST"
        assert self.store.consumed or self.store.calls[-1][0] == "revoke"
        if str(request.url).endswith(OIDC + "token"):
            assert self.store.calls[-1][0] == "consume"
            if self.token_error is not None:
                raise self.token_error
            return response(
                self.token_override if self.token_override is not None else self.tokens()
            )
        assert str(request.url) == self.settings.oidc_backchannel_url + OIDC + "revoke"
        if self.revoke_error is not None:
            raise self.revoke_error
        return httpx.Response(200, stream=Body(b""))

    def callback(self, **kwargs):
        return self.service.callback(
            self.store.flow.state,
            self.store.flow.browser,
            code=MARKER + "-code",
            deadline=deadline(),
            **kwargs,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.service.aclose()
        self.engine.dispose.assert_not_called()


@pytest.fixture
def harness(settings, signing_keys):
    return lambda: Harness(settings, signing_keys)


def deadline(seconds=10):
    return asyncio.get_running_loop().time() + seconds


async def denied(awaitable, status):
    with pytest.raises(DomainError) as caught:
        await awaitable
    error = caught.value
    assert (error.status, error.code, error.pointers) == (
        status,
        "unauthorized" if status == 401 else "identity_unavailable",
        (),
    )
    assert error.__cause__ is None and error.__context__ is None
    assert MARKER not in "".join(traceback.format_exception(error))
    return error


def operations(h):
    return [call[0] for call in h.store.calls]


def login_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "oidc_login"]


class Barrier:
    """Finite blocking keeps failing tests recoverable; events prove ordering."""

    def __init__(self, count=1):
        self.loop = asyncio.get_running_loop()
        self.entered = asyncio.Event()
        self.release = threading.Event()
        self.count = count
        self.calls = 0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            self.calls += 1
            if self.calls == self.count:
                self.loop.call_soon_threadsafe(self.entered.set)
        if not self.release.wait(5):
            raise AssertionError("test worker barrier not released")


def test_public_contract_and_constructor_have_no_io(harness):
    credential_logging._configured = False
    h = harness()
    assert isinstance(h.service._cache, OidcKeyCache)
    assert isinstance(h.service._verifier, TokenVerifier)
    assert isinstance(h.service._metadata, OidcMetadataTransport)
    assert isinstance(h.service._credentials, OidcCredentialTransport)
    assert h.engine.mock_calls == [] and not h.gets and not h.posts and not h.store.calls
    assert LoginStart.__dataclass_params__.frozen
    assert set(LoginStart.__slots__) == {"authorization_url", "browser"}
    value = LoginStart(MARKER + "-url", MARKER + "-browser")
    assert MARKER not in repr(value) + str(value) + repr(h.service) + str(h.service)
    with pytest.raises(FrozenInstanceError):
        value.browser = "changed"
    asyncio.run(h.service.aclose())


def test_constructor_composes_existing_store_without_connecting(settings):
    engine = Mock(spec=Engine)
    service = OidcLoginService(engine, settings)
    assert isinstance(service._store, IdentityStore)
    assert engine.mock_calls == []
    asyncio.run(service.aclose())
    engine.dispose.assert_not_called()


def test_start_exact_public_url_query_pkce_and_no_network(harness):
    async def scenario():
        async with harness() as h:
            result = await h.service.start(deadline=deadline())
            parsed = urlsplit(result.authorization_url)
            assert parsed.scheme + "://" + parsed.netloc + parsed.path == (
                h.settings.oidc_issuer + OIDC + "auth"
            )
            challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(h.store.flow.verifier.encode("ascii")).digest()
                )
                .decode()
                .rstrip("=")
            )
            pairs = parse_qsl(parsed.query)
            assert len(pairs) == 8 and dict(pairs) == {
                "client_id": h.settings.oidc_client_id,
                "redirect_uri": h.settings.public_url + "/auth/callback",
                "response_type": "code",
                "scope": "openid profile",
                "state": h.store.flow.state,
                "nonce": h.store.flow.nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            assert result.browser == h.store.flow.browser
            for secret in (
                h.store.flow.browser,
                h.store.flow.verifier,
                h.settings.oidc_client_secret,
            ):
                assert secret not in result.authorization_url
            assert not parsed.fragment and operations(h) == ["flow"]
            assert not h.gets and not h.posts
            assert h.store.threads[0] != threading.get_ident()

    asyncio.run(scenario())


@pytest.mark.parametrize("at_hash", [True, False])
def test_signed_callback_two_kids_one_snapshot_and_no_claim_grants(harness, at_hash):
    async def scenario():
        async with harness() as h:
            h.with_at_hash = at_hash
            calls = []
            original = h.service._cache.keys_for

            async def keys_for(kids, *, deadline):
                calls.append((kids, deadline))
                return await original(kids, deadline=deadline)

            h.service._cache.keys_for = keys_for
            previous = new_token()
            result = await h.callback(previous_session=previous)
            assert result is h.store.session and not result.principal.can_create_project
            assert operations(h) == ["consume", "create"]
            assert len(calls) == 1 and calls[0][0] == ("id-key", "access-key")
            assert len(h.gets) == 2 and len(h.posts) == 1
            identity = h.store.calls[-1][1]
            assert (identity.issuer, identity.subject) == (h.settings.oidc_issuer, MARKER)
            assert h.store.calls[-1][2:] == (previous, MARKER + "-refresh")
            assert not hasattr(identity, "roles") and not hasattr(identity, "can_create_project")
            form = dict(parse_qsl(h.posts[0].content.decode()))
            assert form["code_verifier"] == h.store.flow.verifier

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "code,error",
    [
        (None, None),
        ("code", "error"),
        ("", None),
        (" ", None),
        ("a\nb", None),
        ("ą", None),
        (True, None),
        (b"code", None),
        ("a" * 4097, None),
        (None, ""),
        (None, "bad error"),
        (None, "a" * 257),
        (None, False),
    ],
)
def test_malformed_callback_refused_before_consume(harness, code, error):
    async def scenario():
        async with harness() as h:
            await denied(
                h.service.callback(
                    h.store.flow.state,
                    h.store.flow.browser,
                    code=code,
                    error=error,
                    deadline=deadline(),
                ),
                401,
            )
            assert not h.store.calls and not h.posts and not h.gets

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["state", "browser"])
def test_noncanonical_callback_cookie_refused_before_store_effect(harness, field):
    async def scenario():
        async with harness() as h:
            args = {
                "state": h.store.flow.state,
                "browser": h.store.flow.browser,
                "code": "code",
                "deadline": deadline(),
            }
            args[field] += "="
            await denied(h.service.callback(**args), 401)
            assert not h.store.calls and not h.posts and not h.gets

    asyncio.run(scenario())


def test_malformed_reply_cannot_supply_refresh_for_cleanup(harness):
    async def scenario():
        async with harness() as h:
            h.token_override = {"refresh_token": MARKER + "-refresh", "id_token": "broken"}
            await denied(h.callback(), 503)
            assert operations(h) == ["consume"] and len(h.posts) == 1 and not h.gets

    asyncio.run(scenario())


def test_exchange_failure_never_retries_or_restores_flow(harness):
    async def scenario():
        async with harness() as h:
            h.token_error = RuntimeError(MARKER)
            await denied(h.callback(), 503)
            await denied(h.callback(), 401)
            assert operations(h) == ["consume", "consume"] and len(h.posts) == 1
            assert not h.gets

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["metadata", "session"])
def test_callback_cleanup_failure_keeps_original_error_and_priority(harness, failure, caplog):
    caplog.set_level(logging.INFO, logger="torii.identity")

    async def scenario():
        async with harness() as h:
            if failure == "metadata":
                h.metadata_error = RuntimeError(MARKER)
            else:

                def broken(*_):
                    h.store.record("create")
                    raise DomainError(503, "dependency_unavailable", (MARKER,))

                h.store.create_session = broken
            h.revoke_error = RuntimeError(MARKER)
            await denied(h.callback(), 503)
            assert len(h.posts) == 2 and "revoke" not in operations(h)
            await denied(h.callback(), 401)
            assert len(h.posts) == 2

    asyncio.run(scenario())
    first = next(r for r in login_records(caplog) if r.operation == "callback")
    assert first.cleanup == ("commit_unknown" if failure == "session" else "remote_failed")


@pytest.mark.parametrize("method", ["start", "callback"])
def test_broken_logging_guard_precedes_any_flow_write(harness, method):
    async def scenario():
        async with harness() as h:
            logging.getLogger("httpx").disabled = False
            operation = h.service.start(deadline=deadline()) if method == "start" else h.callback()
            await denied(operation, 503)
            assert not h.store.calls and not h.posts and not h.gets

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", [True, None, "10", float("nan"), float("inf"), -1, 2**53])
@pytest.mark.parametrize("method", ["start", "callback", "logout"])
def test_bad_deadline_refused_before_side_effect(harness, bad, method):
    async def scenario():
        async with harness() as h:
            if method == "start":
                operation = h.service.start(deadline=bad)
            elif method == "callback":
                operation = h.service.callback(
                    h.store.flow.state, h.store.flow.browser, code="code", deadline=bad
                )
            else:
                operation = h.service.logout(h.store.session.session_id, deadline=bad)
            await denied(operation, 503)
            assert not h.store.calls and not h.posts and not h.gets

    asyncio.run(scenario())


def test_no_positive_work_budget_refused_before_side_effect(harness):
    async def scenario():
        async with harness() as h:
            await denied(h.service.start(deadline=deadline(0.5)), 503)
            assert not h.store.calls

    asyncio.run(scenario())


@pytest.mark.parametrize("requested", [6, 100])
def test_one_deadline_shared_by_exchange_and_snapshot_with_max15_and_reserve(
    harness,
    requested,
    monkeypatch,
):
    async def scenario():
        async with harness() as h:
            recorded = []
            exchange, keys_for = h.service._credentials.exchange, h.service._cache.keys_for

            async def exchange_record(self, *args, deadline):
                recorded.append(deadline)
                return await exchange(*args, deadline=deadline)

            async def keys_record(*args, deadline):
                recorded.append(deadline)
                return await keys_for(*args, deadline=deadline)

            monkeypatch.setattr(OidcCredentialTransport, "exchange", exchange_record)
            h.service._cache.keys_for = keys_record
            before = asyncio.get_running_loop().time()
            await h.service.callback(
                h.store.flow.state, h.store.flow.browser, code="code", deadline=before + requested
            )
            assert len(recorded) == 2 and recorded[0] == recorded[1]
            expected = before + min(requested, 15) - 1
            assert expected <= recorded[0] <= expected + 0.05

    asyncio.run(scenario())


@pytest.mark.parametrize("queued_finish", ["timeout", "cancel"])
def test_four_worker_limit_queue_bound_and_responsive_loop(harness, queued_finish):
    async def scenario():
        async with harness() as h:
            barrier = Barrier(4)
            original = h.store.create_flow

            def blocked():
                barrier.wait()
                return original()

            h.store.create_flow = blocked
            active = [asyncio.create_task(h.service.start(deadline=deadline())) for _ in range(4)]
            queued = None
            try:
                await asyncio.wait_for(barrier.entered.wait(), 2)
                queued = asyncio.create_task(h.service.start(deadline=deadline(1.05)))
                # A loop-scheduled heartbeat while all sync workers remain blocked.
                heartbeat = asyncio.Event()
                asyncio.get_running_loop().call_soon(heartbeat.set)
                await asyncio.wait_for(heartbeat.wait(), 0.2)
                if queued_finish == "timeout":
                    await denied(queued, 503)
                else:
                    queued.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await queued
                assert barrier.calls == 4 and not any(task.done() for task in active)
            finally:
                barrier.release.set()
                await asyncio.gather(*active, return_exceptions=True)
                if queued is not None and not queued.done():
                    queued.cancel()
                    with suppress(asyncio.CancelledError, DomainError):
                        await queued
            assert barrier.calls == 4
            assert await h.service.start(deadline=deadline())
            assert barrier.calls == 5  # All permits were returned after join.

    asyncio.run(scenario())


@pytest.mark.parametrize("method", ["start", "consume", "logout"])
def test_repeated_cancellation_joins_worker_without_next_stage(harness, method):
    async def scenario():
        async with harness() as h:
            barrier = Barrier()
            attribute = {
                "start": "create_flow",
                "consume": "consume_flow",
                "logout": "revoke_session",
            }[method]
            original = getattr(h.store, attribute)

            def blocked(*args):
                barrier.wait()
                return original(*args)

            setattr(h.store, attribute, blocked)
            operation = (
                h.service.start(deadline=deadline())
                if method == "start"
                else h.callback()
                if method == "consume"
                else h.service.logout(h.store.session.session_id, deadline=deadline())
            )
            task = asyncio.create_task(operation)
            try:
                await asyncio.wait_for(barrier.entered.wait(), 2)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done() and not h.posts and not h.gets
            finally:
                barrier.release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert len(h.store.calls) == 1 and not h.posts and not h.gets

    asyncio.run(scenario())


def test_timeout_joins_store_after_budget_without_releasing_result(harness):
    async def scenario():
        async with harness() as h:
            barrier = Barrier()

            def blocked():
                barrier.wait()
                return h.store.flow

            h.store.create_flow = blocked
            task = asyncio.create_task(h.service.start(deadline=deadline(1.04)))
            expired = asyncio.Event()
            try:
                await asyncio.wait_for(barrier.entered.wait(), 2)
                asyncio.get_running_loop().call_later(0.08, expired.set)
                await expired.wait()
                assert not task.done()  # Sync DB join honestly outlives work budget.
            finally:
                barrier.release.set()
                await denied(task, 503)
            assert not h.posts and not h.gets

    asyncio.run(scenario())


def test_cancelled_worker_failure_never_overrides_cancellation(harness):
    async def scenario():
        async with harness() as h:
            barrier = Barrier()

            def blocked():
                barrier.wait()
                raise RuntimeError(MARKER)

            h.store.create_flow = blocked
            task = asyncio.create_task(h.service.start(deadline=deadline()))
            try:
                await asyncio.wait_for(barrier.entered.wait(), 2)
                task.cancel()
                await asyncio.sleep(0)
            finally:
                barrier.release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task

    asyncio.run(scenario())


@pytest.mark.parametrize("compensation_error", [None, 401, 503])
def test_late_session_compensation_is_joined_despite_repeated_cancel(
    harness,
    compensation_error,
    caplog,
):
    caplog.set_level(logging.INFO, logger="torii.identity")

    async def scenario():
        async with harness() as h:
            creation, compensation = Barrier(), Barrier()
            original_create, original_revoke = h.store.create_session, h.store.revoke_session

            def create(*args):
                creation.wait()
                return original_create(*args)

            def revoke(session_id):
                compensation.wait()
                result = original_revoke(session_id)
                if compensation_error is not None:
                    raise DomainError(
                        compensation_error,
                        "unauthorized" if compensation_error == 401 else "dependency_unavailable",
                        (MARKER,),
                    )
                return result

            h.store.create_session, h.store.revoke_session = create, revoke
            task = asyncio.create_task(h.callback())
            try:
                await asyncio.wait_for(creation.entered.wait(), 2)
                task.cancel()
                await asyncio.sleep(0)
                creation.release.set()
                await asyncio.wait_for(compensation.entered.wait(), 2)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done() and len(h.posts) == 1
            finally:
                creation.release.set()
                compensation.release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert operations(h) == ["consume", "create", "revoke"]
            assert h.store.calls[-1] == ("revoke", h.store.session.session_id)
            assert len(h.posts) == 1

    asyncio.run(scenario())
    record = next(r for r in login_records(caplog) if r.operation == "callback")
    assert record.outcome == "cancelled"
    # A store 503 does not reveal whether the compensating DELETE committed.
    assert record.cleanup == ("commit_unknown" if compensation_error == 503 else "none")


def test_close_drains_workers_blocks_admission_and_preserves_engine(harness):
    async def scenario():
        h = harness()
        barrier = Barrier()

        def blocked():
            barrier.wait()
            return h.store.flow

        h.store.create_flow = blocked
        task = asyncio.create_task(h.service.start(deadline=deadline()))
        closing = None
        try:
            await asyncio.wait_for(barrier.entered.wait(), 2)
            closing = asyncio.create_task(h.service.aclose())
            await asyncio.sleep(0)
            await denied(h.service.start(deadline=deadline()), 503)
            assert not closing.done() and h.metadata.closes == h.credentials.closes == 0
        finally:
            barrier.release.set()
            await task
            if closing is not None:
                await closing
        assert h.metadata.closes == h.credentials.closes == 1
        await h.service.aclose()
        assert h.metadata.closes == h.credentials.closes == 1
        h.engine.dispose.assert_not_called()

    asyncio.run(scenario())


def test_parallel_close_and_repeated_cancel_join_one_cleanup(harness):
    async def scenario():
        h = harness()
        h.metadata.close_release = asyncio.Event()
        first = asyncio.create_task(h.service.aclose())
        second = None
        try:
            await asyncio.wait_for(h.metadata.close_entered.wait(), 2)
            second = asyncio.create_task(h.service.aclose())
            first.cancel()
            await asyncio.sleep(0)
            first.cancel()
            await asyncio.sleep(0)
            assert not first.done() and not second.done()
        finally:
            h.metadata.close_release.set()
            with pytest.raises(asyncio.CancelledError):
                await first
            if second is not None:
                await second
        assert h.metadata.closes == h.credentials.closes == 1
        await denied(h.callback(), 503)

    asyncio.run(scenario())


@pytest.mark.parametrize("error", [RuntimeError(MARKER), asyncio.CancelledError()])
def test_first_client_close_failure_still_closes_second(harness, error):
    async def scenario():
        h = harness()
        h.metadata.close_error = error
        with suppress(DomainError, asyncio.CancelledError):
            await h.service.aclose()
        assert h.metadata.closes == h.credentials.closes == 1
        h.engine.dispose.assert_not_called()

    asyncio.run(scenario())


def test_cross_loop_refused_and_original_loop_can_close(harness):
    h = harness()
    with asyncio.Runner() as owner, asyncio.Runner() as foreign:

        async def start():
            return await h.service.start(deadline=deadline())

        async def reject():
            await denied(start(), 503)

        owner.run(start())
        foreign.run(reject())
        owner.run(h.service.aclose())
    assert operations(h) == ["flow"] and h.metadata.closes == h.credentials.closes == 1


def test_telemetry_schema_and_formatted_errors_never_expose_secrets(harness, caplog):
    caplog.set_level(logging.DEBUG)

    async def scenario():
        async with harness() as h:
            await h.service.start(deadline=deadline())
            h.token_error = RuntimeError(MARKER)
            await denied(h.callback(), 503)
            await denied(h.callback(), 401)
            secrets = [
                MARKER,
                h.settings.oidc_client_secret,
                h.settings.oidc_issuer,
                h.store.flow.state,
                h.store.flow.browser,
                h.store.flow.nonce,
                h.store.flow.verifier,
                h.store.session.session_id,
                h.store.session.csrf_token,
            ]
            for record in caplog.records:
                assert record.exc_info is None and record.exc_text is None
                rendered = logging.Formatter("%(message)s").format(record)
                assert not any(secret in rendered for secret in secrets)

    asyncio.run(scenario())
    records = login_records(caplog)
    assert {r.outcome for r in records} >= {"success", "unavailable", "unauthorized"}
    baseline = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
    for record in records:
        assert set(record.__dict__) - baseline == {
            "event",
            "operation",
            "outcome",
            "cleanup",
            "duration_ms",
        }
        assert record.operation in {"start", "callback", "logout", "close"}
        assert record.cleanup in {
            "none",
            "remote_failed",
            "local_failed",
            "secret_corrupt",
            "commit_unknown",
        }
        assert math.isfinite(record.duration_ms) and record.duration_ms >= 0


def test_cancelled_executor_queued_future_does_not_start_store(harness):
    async def scenario():
        async with harness() as h:
            loop = asyncio.get_running_loop()
            queued = asyncio.Event()

            class ObservedExecutor(ThreadPoolExecutor):
                submissions = 0

                def submit(self, function, *args, **kwargs):
                    result = super().submit(function, *args, **kwargs)
                    self.submissions += 1
                    if self.submissions == 2:
                        queued.set()
                    return result

            loop.set_default_executor(ObservedExecutor(max_workers=1))
            barrier = Barrier()
            occupying = loop.run_in_executor(None, barrier.wait)
            task = None
            try:
                await asyncio.wait_for(barrier.entered.wait(), 2)
                task = asyncio.create_task(h.service.start(deadline=deadline()))
                await asyncio.wait_for(queued.wait(), 2)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done() and not h.store.calls
            finally:
                barrier.release.set()
                await occupying
                if task is not None:
                    with pytest.raises(asyncio.CancelledError):
                        await task
            assert not h.store.calls and not h.posts and not h.gets
            assert await h.service.start(deadline=deadline())

    asyncio.run(scenario())


def test_budget_checked_after_synchronous_verification_before_session(harness, monkeypatch):
    original = TokenVerifier.verify_login

    def slow_verify(self, *args):
        result = original(self, *args)
        time.sleep(0.2)  # Models bounded CPU work; event-loop preemption is not promised.
        return result

    monkeypatch.setattr(TokenVerifier, "verify_login", slow_verify)

    async def scenario():
        async with harness() as h:
            await denied(
                h.service.callback(
                    h.store.flow.state, h.store.flow.browser, code="code", deadline=deadline(1.1)
                ),
                503,
            )
            assert operations(h) == ["consume"] and len(h.posts) == 1
            assert len(h.gets) == 2  # Verification ran over actual keys and signed JWT.

    asyncio.run(scenario())


def test_cache_lock_wait_uses_callback_budget_and_cannot_create_session(harness):
    async def scenario():
        async with harness() as h:
            await h.service._cache._lock.acquire()
            started = time.monotonic()
            limit = deadline(1.05)
            sent_at = []

            def record_post(request):
                sent_at.append(asyncio.get_running_loop().time())
                return h.post(request)

            h.credentials.handler = record_post
            try:
                await denied(
                    h.service.callback(
                        h.store.flow.state,
                        h.store.flow.browser,
                        code="code",
                        deadline=limit,
                    ),
                    503,
                )
            finally:
                h.service._cache._lock.release()
            assert time.monotonic() - started < 0.8
            assert operations(h) == ["consume"] and 1 <= len(h.posts) <= 2 and not h.gets
            # Windows may wake an asyncio timer slightly early. Best-effort
            # revoke is valid only in that remainder of the SAME work budget.
            if len(h.posts) == 2:
                assert str(h.posts[-1].url) == h.settings.oidc_backchannel_url + OIDC + "revoke"
                assert sent_at[-1] < limit - 1

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["callback", "logout"])
def test_http_timeout_respects_budget_and_logout_keeps_local_success(harness, operation):
    async def scenario():
        async with harness() as h:
            entered = asyncio.Event()

            async def hanging(request):
                h.posts.append(request)
                entered.set()
                await asyncio.Event().wait()

            h.credentials.handler = hanging
            limit = deadline(1.05)
            started = time.monotonic()
            if operation == "callback":
                await denied(
                    h.service.callback(
                        h.store.flow.state, h.store.flow.browser, code="code", deadline=limit
                    ),
                    503,
                )
                assert operations(h) == ["consume"]
            else:
                assert await h.service.logout(h.store.session.session_id, deadline=limit) is None
                assert operations(h) == ["revoke"]
            assert entered.is_set() and len(h.posts) == 1 and not h.gets
            assert time.monotonic() - started < 0.8

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["exchange", "keys"])
def test_external_network_cancellation_does_not_attempt_refresh_revoke(harness, phase):
    async def scenario():
        async with harness() as h:
            entered = asyncio.Event()

            async def hanging(request):
                if phase == "exchange":
                    h.posts.append(request)
                else:
                    h.gets.append(request)
                entered.set()
                await asyncio.Event().wait()

            transport = h.credentials if phase == "exchange" else h.metadata
            transport.handler = hanging
            task = asyncio.create_task(h.callback())
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert operations(h) == ["consume"] and len(h.posts) == 1

    asyncio.run(scenario())


def test_code_and_provider_error_maximum_lengths_are_allowed(harness):
    async def scenario():
        async with harness() as h:
            result = await h.service.callback(
                h.store.flow.state, h.store.flow.browser, code="a" * 4096, deadline=deadline()
            )
            assert result is h.store.session
        async with harness() as h:
            await denied(
                h.service.callback(
                    h.store.flow.state, h.store.flow.browser, error="a" * 256, deadline=deadline()
                ),
                401,
            )
            assert operations(h) == ["consume"] and not h.posts

    asyncio.run(scenario())


def test_cancel_during_failure_revoke_has_no_provider_exception_context(harness, monkeypatch):
    def broken_verifier(*_):
        raise RuntimeError(MARKER)

    monkeypatch.setattr(TokenVerifier, "verify_login", broken_verifier)

    async def scenario():
        async with harness() as h:
            revoke_entered = asyncio.Event()

            async def handler(request):
                if str(request.url).endswith(OIDC + "token"):
                    return h.post(request)
                h.posts.append(request)
                revoke_entered.set()
                await asyncio.Event().wait()

            h.credentials.handler = handler
            task = asyncio.create_task(h.callback())
            await asyncio.wait_for(revoke_entered.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
            assert caught.value.__context__ is None
            assert MARKER not in "".join(traceback.format_exception(caught.value))
            assert operations(h) == ["consume"] and len(h.posts) == 2

    asyncio.run(scenario())


def test_constructor_validates_pure_config_before_constructing_clients(settings, monkeypatch):
    metadata, credentials = Mock(), Mock()
    monkeypatch.setattr(oidc_login, "OidcMetadataTransport", metadata)
    monkeypatch.setattr(oidc_login, "OidcCredentialTransport", credentials)
    engine = Mock(spec=Engine)
    with pytest.raises(DomainError) as caught:
        OidcLoginService(engine, replace(settings, oidc_client_secret=""))
    assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
    assert caught.value.__context__ is None
    metadata.assert_not_called()
    credentials.assert_not_called()
    assert engine.mock_calls == []


def test_failed_second_client_constructor_spawns_no_detached_cleanup(settings, monkeypatch):
    def broken(*_, **__):
        raise RuntimeError(MARKER)

    monkeypatch.setattr(oidc_login, "OidcCredentialTransport", broken)

    async def scenario():
        engine = Mock(spec=Engine)
        metadata, credentials = Transport(Mock()), Transport(Mock())
        before = asyncio.all_tasks()
        with pytest.raises(DomainError) as caught:
            OidcLoginService(
                engine, settings, metadata_transport=metadata, credential_transport=credentials
            )
        assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
        assert caught.value.__context__ is None
        assert MARKER not in "".join(traceback.format_exception(caught.value))
        assert asyncio.all_tasks() == before
        assert engine.mock_calls == [] and metadata.closes == credentials.closes == 0
        metadata.handler.assert_not_called()
        credentials.handler.assert_not_called()
        # Ownership stays with the caller when no service was constructed.
        await metadata.aclose()
        await credentials.aclose()

    asyncio.run(scenario())
