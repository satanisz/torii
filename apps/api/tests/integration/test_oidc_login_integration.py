"""SPEC-0001 A4c: actual PostgreSQL commits composed with synthetic OIDC I/O.

Only the guarded integration harness supplies databases. RSA keys and IdP
responses are synthetic; these tests do not qualify a real provider or HTTP UI.
"""

import asyncio
import base64
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from threading import Event
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from torii_api.application.identity_store import IdentityStore, NewSession
from torii_api.application.oidc_login import OidcLoginService
from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity
from torii_api.security import credential_logging
from torii_api.security.session_secrets import SecretCodec, new_token, token_hash

pytestmark = pytest.mark.integration
MARKER = "synthetic-a4c-confidential-marker"
SUBJECT = "synthetic-a4c-user"


@pytest.fixture(autouse=True)
def logging_policy():
    configured = credential_logging._configured
    previous = {
        name: logging.getLogger(name).disabled
        for name in credential_logging.CREDENTIAL_LOGGER_NAMES
    }
    credential_logging.configure_credential_logging()
    yield
    credential_logging._configured = configured
    for name, disabled in previous.items():
        logging.getLogger(name).disabled = disabled


@pytest.fixture(scope="module")
def signing_material():
    return tuple(rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))


@pytest.fixture
def organization(db_pair):
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations(id,name) VALUES (:id,'Synthetic A4c')"),
            {"id": uuid4()},
        )


def count(pair, table):
    # All identifiers are constants owned by these tests.
    with pair.migrator.connect() as conn:
        return conn.scalar(text(f"SELECT count(*) FROM {table}"))


def store_for(pair, settings):
    return IdentityStore(
        pair.runtime, SecretCodec(settings.session_key.encode()), settings.oidc_issuer
    )


def seed_session(pair, settings, *, refresh=MARKER):
    return store_for(pair, settings).create_session(
        Identity(settings.oidc_issuer, SUBJECT, "Synthetic user"), refresh_token=refresh
    )


def commit_fault(pair, table, operation):
    with pair.migrator.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION a4c_commit_fault() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'synthetic-a4c-confidential-marker'; END $$"
            )
        )
        conn.execute(
            text(
                f"CREATE CONSTRAINT TRIGGER a4c_fail_at_commit AFTER {operation} ON {table} "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                "EXECUTE FUNCTION a4c_commit_fault()"
            )
        )


class Body(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = json.dumps(value).encode()

    async def __aiter__(self):
        yield self.value


class Provider:
    def __init__(self, pair, settings, keys):
        self.pair, self.settings, self.keys = pair, settings, keys
        self.calls = []
        self.parameters = None
        self.invalid = None
        self.exchange_failure = False
        self.revoke_failure = False
        self.logout = False
        self.exclusive = True

    def tokens(self):
        now = int(time.time())
        base = {
            "iss": self.settings.oidc_issuer,
            "sub": SUBJECT,
            "iat": now,
            "exp": now + 300,
            "azp": self.settings.oidc_client_id,
            "roles": ["admin"],
        }
        access_claims = base | {"typ": "Bearer", "aud": self.settings.oidc_audience}
        access = jwt.encode(
            access_claims,
            self.keys[1 if self.invalid == "access_signature" else 0],
            algorithm="RS256",
            headers={"kid": "access-key"},
        )
        claims = base | {
            "typ": "ID",
            "aud": self.settings.oidc_client_id,
            "nonce": self.parameters["nonce"][0],
            "at_hash": base64.urlsafe_b64encode(hashlib.sha256(access.encode()).digest()[:16])
            .rstrip(b"=")
            .decode(),
        }
        if self.invalid == "nonce":
            claims["nonce"] = new_token()
        elif self.invalid == "sub":
            claims["sub"] = "other-synthetic-user"
        elif self.invalid == "at_hash":
            claims["at_hash"] = base64.urlsafe_b64encode(b"x" * 16).rstrip(b"=").decode()
        identity = jwt.encode(
            claims,
            self.keys[0 if self.invalid == "id_signature" else 1],
            algorithm="RS256",
            headers={"kid": "id-key"},
        )
        return {
            "id_token": identity,
            "access_token": access,
            "refresh_token": MARKER,
            "token_type": "Bearer",
        }

    async def handle(self, request):
        # In nonconcurrent scenarios this proves the callback released its DB connection.
        # A different racing callback may legitimately be using its own connection.
        if self.exclusive:
            assert self.pair.runtime.pool.checkedout() == 0
        suffix = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(suffix)
        if suffix == "token":
            with self.pair.migrator.connect() as conn:
                assert (
                    conn.scalar(
                        text("SELECT count(*) FROM oidc_flows WHERE state_hash=:state"),
                        {"state": token_hash(self.parameters["state"][0])},
                    )
                    == 0
                )
            fields = parse_qs(request.content.decode())
            challenge = base64.urlsafe_b64encode(
                hashlib.sha256(fields["code_verifier"][0].encode()).digest()
            ).rstrip(b"=")
            assert challenge.decode() == self.parameters["code_challenge"][0]
            if self.exchange_failure:
                raise httpx.ReadError(MARKER)
            value = self.tokens()
        elif suffix == "openid-configuration":
            issuer = self.settings.oidc_issuer
            value = {"issuer": issuer}
            for field, endpoint in (
                ("authorization_endpoint", "auth"),
                ("token_endpoint", "token"),
                ("jwks_uri", "certs"),
                ("revocation_endpoint", "revoke"),
            ):
                value[field] = issuer + "/protocol/openid-connect/" + endpoint
        elif suffix == "certs":
            value = {
                "keys": [
                    json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": kid}
                    for key, kid in zip(self.keys, ("access-key", "id-key"), strict=True)
                ]
            }
        elif suffix == "revoke":
            if self.logout:
                assert count(self.pair, "sessions") == 0
            if self.revoke_failure:
                raise httpx.ReadError(MARKER)
            value = {}
        else:
            raise AssertionError("Unexpected synthetic endpoint")
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=Body(value))


@asynccontextmanager
async def running(pair, settings, keys):
    provider = Provider(pair, settings, keys)
    service = OidcLoginService(
        pair.runtime,
        settings,
        metadata_transport=httpx.MockTransport(provider.handle),
        credential_transport=httpx.MockTransport(provider.handle),
    )
    try:
        yield service, provider
    finally:
        await service.aclose()


def deadline():
    return asyncio.get_running_loop().time() + 15


async def start(service, provider):
    result = await service.start(deadline=deadline())
    provider.parameters = parse_qs(urlsplit(result.authorization_url).query)
    return provider.parameters["state"][0], result.browser


async def failure(operation, status):
    with pytest.raises(DomainError) as caught:
        await operation
    assert caught.value.status == status
    assert caught.value.code == ("unauthorized" if status == 401 else "identity_unavailable")


def test_start_commit_and_callback_produce_verified_grant_free_session(
    db_pair, settings, signing_material, organization
):
    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            assert count(db_pair, "oidc_flows") == 1
            assert provider.calls == []
            session = await service.callback(state, browser, code="accepted", deadline=deadline())
            assert isinstance(session, NewSession)
            assert provider.calls == ["token", "openid-configuration", "certs"]
            assert count(db_pair, "principals") == count(db_pair, "sessions") == 1
            assert count(db_pair, "global_grants") == 0
            assert not session.principal.can_create_project
            fresh = store_for(db_pair, settings)
            assert fresh.authenticate_session(session.session_id).principal == session.principal
            await failure(
                service.callback(state, browser, code="accepted", deadline=deadline()), 401
            )
            assert provider.calls.count("token") == 1

    asyncio.run(scenario())


def test_racing_callbacks_exchange_only_once(db_pair, settings, signing_material, organization):
    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            provider.exclusive = False
            results = await asyncio.gather(
                *(
                    service.callback(state, browser, code="accepted", deadline=deadline())
                    for _ in range(2)
                ),
                return_exceptions=True,
            )
            assert sum(isinstance(item, NewSession) for item in results) == 1
            errors = [item for item in results if isinstance(item, DomainError)]
            assert len(errors) == 1 and errors[0].status == 401
            assert provider.calls.count("token") == count(db_pair, "sessions") == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["browser", "expired", "missing", "consume_commit"])
def test_rejected_flow_never_reaches_http(db_pair, settings, signing_material, organization, kind):
    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            if kind == "browser":
                browser = new_token()
            elif kind == "missing":
                state = new_token()
            elif kind == "expired":
                with db_pair.migrator.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE oidc_flows SET created_at=clock_timestamp()-interval '10min', "
                            "expires_at=clock_timestamp()-interval '1 second'"
                        )
                    )
            else:
                commit_fault(db_pair, "oidc_flows", "DELETE")
            await failure(
                service.callback(state, browser, code="accepted", deadline=deadline()),
                503 if kind == "consume_commit" else 401,
            )
            assert provider.calls == []
            assert count(db_pair, "sessions") == count(db_pair, "principals") == 0
            assert count(db_pair, "oidc_flows") == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["id_signature", "access_signature", "nonce", "sub", "at_hash"])
def test_invalid_verified_login_never_provisions(
    db_pair, settings, signing_material, organization, kind
):
    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            provider.invalid = kind
            await failure(
                service.callback(state, browser, code="accepted", deadline=deadline()), 401
            )
            assert count(db_pair, "principals") == count(db_pair, "sessions") == 0
            assert count(db_pair, "oidc_flows") == 0
            assert provider.calls.count("token") == provider.calls.count("revoke") == 1

    asyncio.run(scenario())


def test_exchange_failure_consumes_flow_without_retry(
    db_pair, settings, signing_material, organization
):
    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            provider.exchange_failure = True
            await failure(
                service.callback(state, browser, code="accepted", deadline=deadline()), 503
            )
            await failure(
                service.callback(state, browser, code="accepted", deadline=deadline()), 401
            )
            assert provider.calls == ["token"]
            assert count(db_pair, "sessions") == count(db_pair, "oidc_flows") == 0

    asyncio.run(scenario())


def test_session_commit_failure_rolls_back_rotation_and_revokes_refresh(
    db_pair, settings, signing_material, organization
):
    old = seed_session(db_pair, settings)
    commit_fault(db_pair, "sessions", "INSERT")

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            await failure(
                service.callback(
                    state,
                    browser,
                    code="accepted",
                    previous_session=old.session_id,
                    deadline=deadline(),
                ),
                503,
            )
            assert count(db_pair, "sessions") == 1
            assert store_for(db_pair, settings).authenticate_session(old.session_id)
            assert provider.calls.count("revoke") == 1

    asyncio.run(scenario())


def test_successful_rotation_preserves_other_device_and_grants_stay_absent(
    db_pair, settings, signing_material, organization
):
    old, other = seed_session(db_pair, settings), seed_session(db_pair, settings)

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            current = await service.callback(
                state,
                browser,
                code="accepted",
                previous_session=old.session_id,
                deadline=deadline(),
            )
            fresh = store_for(db_pair, settings)
            assert fresh.authenticate_session(current.session_id)
            assert fresh.authenticate_session(other.session_id)
            with pytest.raises(DomainError):
                fresh.authenticate_session(old.session_id)
            assert count(db_pair, "sessions") == 2
            assert count(db_pair, "principals") == 1
            assert count(db_pair, "global_grants") == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["missing_organization", "inactive"])
def test_local_provisioning_refusal_never_creates_a_new_session(
    db_pair, settings, signing_material, organization, kind
):
    if kind == "inactive":
        seed_session(db_pair, settings)
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM organizations"
                if kind == "missing_organization"
                else "UPDATE principals SET active=false"
            )
        )

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            await failure(
                service.callback(state, browser, code="accepted", deadline=deadline()),
                503 if kind == "missing_organization" else 401,
            )
            assert count(db_pair, "sessions") == (0 if kind == "missing_organization" else 1)
            assert count(db_pair, "global_grants") == 0
            if kind == "inactive":
                with db_pair.migrator.connect() as conn:
                    assert conn.scalar(text("SELECT active FROM principals")) is False
            assert provider.calls.count("revoke") == 1

    asyncio.run(scenario())


def test_provider_error_consumes_bound_flow_without_network_or_session(
    db_pair, settings, signing_material, organization
):
    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            await failure(service.callback(state, browser, error=MARKER, deadline=deadline()), 401)
            assert provider.calls == []
            assert count(db_pair, "oidc_flows") == count(db_pair, "sessions") == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("remote_failure", [False, True, "guard", "corrupt"])
def test_logout_commits_locally_before_optional_http(
    db_pair, settings, signing_material, organization, remote_failure
):
    session = seed_session(db_pair, settings)
    if remote_failure == "corrupt":
        with db_pair.migrator.begin() as conn:
            conn.execute(text("UPDATE sessions SET refresh_ciphertext='corrupt-synthetic-value'"))

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            provider.logout = True
            provider.revoke_failure = remote_failure is True
            if remote_failure == "guard":
                logging.getLogger("httpx").disabled = False
            assert await service.logout(session.session_id, deadline=deadline()) is None
            assert count(db_pair, "sessions") == 0
            with pytest.raises(DomainError):
                store_for(db_pair, settings).authenticate_session(session.session_id)
            assert provider.calls == ([] if remote_failure in ("guard", "corrupt") else ["revoke"])

    asyncio.run(scenario())


def test_logout_commit_fault_keeps_session_and_never_revokes_remote(
    db_pair, settings, signing_material, organization
):
    session = seed_session(db_pair, settings)
    commit_fault(db_pair, "sessions", "DELETE")

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            await failure(service.logout(session.session_id, deadline=deadline()), 503)
            assert provider.calls == []
            assert count(db_pair, "sessions") == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["consume", "session"])
def test_cancellation_joins_committed_worker_and_compensates_known_new_session(
    db_pair, settings, signing_material, organization, monkeypatch, stage
):
    old = seed_session(db_pair, settings)
    entered, release = Event(), Event()

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            name = "consume_flow" if stage == "consume" else "create_session"
            original = getattr(service._store, name)

            def held(*args, **kwargs):
                result = original(*args, **kwargs)  # Real COMMIT already completed.
                entered.set()
                assert release.wait(5), "Test barrier was not released"
                return result

            monkeypatch.setattr(service._store, name, held)
            task = asyncio.create_task(
                service.callback(
                    state,
                    browser,
                    code="accepted",
                    previous_session=old.session_id,
                    deadline=deadline(),
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done(), "Cancelled callback must wait for its DB worker"
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert count(db_pair, "oidc_flows") == 0
            assert count(db_pair, "sessions") == (1 if stage == "consume" else 0)
            assert provider.calls.count("token") == (0 if stage == "consume" else 1)
            assert provider.calls.count("revoke") == 0

    asyncio.run(scenario())


def test_committed_session_with_lost_ack_is_not_misreported_as_rollback(
    db_pair, settings, signing_material, organization, monkeypatch, caplog
):
    old = seed_session(db_pair, settings)
    caplog.set_level(logging.INFO, logger="torii.identity")

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            original = service._store.create_session

            def lost_ack(*args, **kwargs):
                original(*args, **kwargs)  # New session commits, then its result is lost.
                raise DomainError(503, MARKER)

            monkeypatch.setattr(service._store, "create_session", lost_ack)
            await failure(
                service.callback(
                    state,
                    browser,
                    code="accepted",
                    previous_session=old.session_id,
                    deadline=deadline(),
                ),
                503,
            )
            assert count(db_pair, "sessions") == 1  # Unknown credential was never returned.
            with pytest.raises(DomainError):
                store_for(db_pair, settings).authenticate_session(old.session_id)
            assert count(db_pair, "oidc_flows") == 0
            assert provider.calls.count("token") == provider.calls.count("revoke") == 1
            assert any(
                getattr(record, "cleanup", None) == "commit_unknown" for record in caplog.records
            )
            assert MARKER not in caplog.text

    asyncio.run(scenario())


def test_failed_known_session_compensation_preserves_cancellation(
    db_pair, settings, signing_material, organization, monkeypatch, caplog
):
    entered, release = Event(), Event()
    caplog.set_level(logging.INFO, logger="torii.identity")

    async def scenario():
        async with running(db_pair, settings, signing_material) as (service, provider):
            state, browser = await start(service, provider)
            original = service._store.create_session

            def held(*args, **kwargs):
                result = original(*args, **kwargs)
                entered.set()
                assert release.wait(5)
                return result

            def failed_revoke(_session):
                raise DomainError(503, MARKER)

            monkeypatch.setattr(service._store, "create_session", held)
            monkeypatch.setattr(service._store, "revoke_session", failed_revoke)
            task = asyncio.create_task(
                service.callback(state, browser, code="accepted", deadline=deadline())
            )
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert count(db_pair, "sessions") == 1
            assert provider.calls.count("revoke") == 0
            assert any(
                getattr(record, "cleanup", None) in {"local_failed", "commit_unknown"}
                for record in caplog.records
            )
            assert MARKER not in caplog.text

    asyncio.run(scenario())
