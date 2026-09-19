"""SPEC-0001 B2a1: persistence invariants on real, disposable PostgreSQL.

Synthetic Identity values deliberately do not prove JWT/OIDC verification. The
SUT uses only runtime grants; the migrator seeds fixtures and injects DB faults.
"""

import hashlib
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from functools import partial
from threading import Barrier, Event, current_thread
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import event, text

from torii_api.application.identity_store import IdentityStore
from torii_api.application.projects import ProjectService
from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity
from torii_api.security.cursor import CursorSigner
from torii_api.security.session_secrets import SecretCodec, new_token, token_hash

pytestmark = pytest.mark.integration
ISSUER = "https://synthetic-identity.invalid/realms/b2a1"


@pytest.fixture
def identity():
    return Identity(ISSUER, "synthetic-subject", "Synthetic person")


@pytest.fixture
def codec():
    return SecretCodec(Fernet.generate_key())


@pytest.fixture
def store(db_pair, codec):
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations(id,name) VALUES (:id,'Synthetic B2a1')"),
            {"id": uuid4()},
        )
    return IdentityStore(db_pair.runtime, codec, ISSUER)


def denied(status, operation):
    with pytest.raises(DomainError) as caught:
        operation()
    assert caught.value.status == status
    return caught.value


def row(db_pair, table, key, value):
    # Table/column inputs below are test-owned constants, never external values.
    with db_pair.migrator.connect() as conn:
        result = (
            conn.execute(text(f"SELECT * FROM {table} WHERE {key}=:value"), {"value": value})
            .mappings()
            .one_or_none()
        )
        return dict(result) if result is not None else None


def count(db_pair, table):
    with db_pair.migrator.connect() as conn:
        return conn.scalar(text(f"SELECT count(*) FROM {table}"))


def commit_fault(db_pair, table, operation):
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION b2a1_commit_fault() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'synthetic-confidential-db-marker'; END $$"
            )
        )
        conn.execute(
            text(
                f"CREATE CONSTRAINT TRIGGER b2a1_fail_at_commit AFTER {operation} ON {table} "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                "EXECUTE FUNCTION b2a1_commit_fault()"
            )
        )


@contextmanager
def observe_statement(engine, predicate):
    attempted = Event()

    def before(conn, cursor, statement, parameters, context, many):
        if predicate(statement.lower()):
            attempted.set()

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield attempted
    finally:
        event.remove(engine, "before_cursor_execute", before)


def test_flow_persists_hashes_bound_ciphertext_and_exact_ttl(store, db_pair, codec):
    flow = store.create_flow()
    values = (flow.state, flow.browser, flow.nonce, flow.verifier)
    assert len(set(values)) == 4
    saved = row(db_pair, "oidc_flows", "state_hash", token_hash(flow.state))
    assert saved is not None
    assert saved["browser_hash"] == hashlib.sha256(flow.browser.encode()).hexdigest()
    assert saved["nonce_hash"] == hashlib.sha256(flow.nonce.encode()).hexdigest()
    assert saved["expires_at"] - saved["created_at"] == timedelta(minutes=5)
    cipher = bytes(saved["verifier_ciphertext"])
    assert codec.open("verifier", token_hash(flow.state), cipher) == flow.verifier
    assert all(value not in repr(saved) and value not in repr(flow) for value in values)
    assert count(db_pair, "sessions") == 0
    wrong = denied(401, lambda: store.consume_flow(flow.state, new_token()))
    assert count(db_pair, "oidc_flows") == 1
    consumed = store.consume_flow(flow.state, flow.browser)
    assert consumed.nonce_hash == saved["nonce_hash"]
    assert consumed.verifier == flow.verifier
    assert flow.verifier not in repr(consumed)
    used = denied(401, lambda: store.consume_flow(flow.state, flow.browser))
    missing = denied(401, lambda: store.consume_flow(new_token(), new_token()))
    assert wrong.code == used.code == missing.code


def test_two_flow_consumers_only_one_receives_exchange_material(store, db_pair):
    flow, barrier = store.create_flow(), Barrier(2)

    def consume():
        barrier.wait(timeout=5)
        try:
            return store.consume_flow(flow.state, flow.browser)
        except DomainError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(consume) for _ in range(2)]
        outcomes = [future.result(timeout=10) for future in futures]
    assert sum(outcome == 401 for outcome in outcomes) == 1
    assert sum(getattr(outcome, "verifier", None) == flow.verifier for outcome in outcomes) == 1
    assert count(db_pair, "oidc_flows") == 0


@pytest.mark.parametrize("operation", ["INSERT", "DELETE"])
def test_flow_commit_failure_never_returns_material(store, db_pair, operation):
    flow = store.create_flow() if operation == "DELETE" else None
    commit_fault(db_pair, "oidc_flows", operation)
    call = (
        store.create_flow if flow is None else lambda: store.consume_flow(flow.state, flow.browser)
    )
    error = denied(503, call)
    assert "synthetic-confidential-db-marker" not in "".join(traceback.format_exception(error))
    assert count(db_pair, "oidc_flows") == (1 if flow else 0)


@pytest.mark.parametrize("kind", ["flow", "absolute", "idle"])
def test_expiry_uses_fresh_clock_after_row_lock_wait(store, db_pair, identity, kind):
    if kind == "flow":
        flow = store.create_flow()
        table, column, identifier = "oidc_flows", "state_hash", token_hash(flow.state)
        call = partial(store.consume_flow, flow.state, flow.browser)
    else:
        session = store.create_session(identity)
        table, column, identifier = "sessions", "id_hash", token_hash(session.session_id)
        call = partial(store.authenticate_session, session.session_id)
    with (
        observe_statement(
            db_pair.runtime, lambda sql: table in sql and "for update" in sql
        ) as attempted,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        with db_pair.migrator.begin() as conn:
            conn.execute(
                text(f"SELECT {column} FROM {table} WHERE {column}=:id FOR UPDATE"),
                {"id": identifier},
            )
            future = executor.submit(call)
            assert attempted.wait(timeout=5)
            if kind == "idle":
                conn.execute(
                    text(
                        "UPDATE sessions SET last_seen_at=clock_timestamp()-interval '30min' "
                        "+interval '100ms' WHERE id_hash=:id"
                    ),
                    {"id": identifier},
                )
            else:
                conn.execute(
                    text(
                        f"UPDATE {table} SET created_at=clock_timestamp()-interval '10h', "
                        f"expires_at=clock_timestamp()+interval '100ms' WHERE {column}=:id"
                    ),
                    {"id": identifier},
                )
            # Server-side delay crosses expiry after the SUT transaction began.
            conn.execute(text("SELECT pg_sleep(0.2)"))
        denied(401, lambda: future.result(timeout=10))
    assert row(db_pair, table, column, identifier) is not None


def test_parallel_identity_provision_is_unique_and_grant_free(store, db_pair, identity):
    barrier = Barrier(2)

    def provision():
        barrier.wait(timeout=5)
        return store.provision_identity(identity)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(provision) for _ in range(2)]
        first, second = [future.result(timeout=10) for future in futures]
    assert first.principal_id == second.principal_id
    assert first.can_create_project is False
    assert count(db_pair, "principals") == 1
    assert all(count(db_pair, table) == 0 for table in ("global_grants", "memberships", "sessions"))
    renamed = store.provision_identity(Identity(ISSUER, identity.subject, "Renamed person"))
    assert renamed.principal_id == first.principal_id
    assert renamed.display_name == "Renamed person"
    case_distinct = store.provision_identity(
        Identity(ISSUER, identity.subject.upper(), "Same name")
    )
    assert case_distinct.principal_id != first.principal_id


def test_inactive_and_foreign_identity_never_provision_or_reactivate(store, db_pair, identity):
    principal = store.provision_identity(identity)
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("UPDATE principals SET active=false WHERE id=:id"), {"id": principal.principal_id}
        )
    denied(401, lambda: store.provision_identity(Identity(ISSUER, identity.subject, "New name")))
    denied(401, lambda: store.create_session(identity))
    denied(
        401,
        lambda: store.provision_identity(Identity("https://foreign.invalid", "unknown", "Other")),
    )
    saved = row(db_pair, "principals", "id", principal.principal_id)
    assert saved["active"] is False and saved["display_name"] == identity.display_name
    assert count(db_pair, "principals") == 1 and count(db_pair, "sessions") == 0


def test_missing_organization_fails_closed_without_effects(db_pair, codec, identity):
    empty_store = IdentityStore(db_pair.runtime, codec, ISSUER)
    denied(503, lambda: empty_store.provision_identity(identity))
    denied(503, lambda: empty_store.create_session(identity))
    assert count(db_pair, "principals") == count(db_pair, "sessions") == 0


def test_session_persistence_touch_grant_freshness_and_new_store(store, db_pair, codec, identity):
    refresh = "synthetic-refresh-value"
    session = store.create_session(identity, refresh_token=refresh)
    session_hash = token_hash(session.session_id)
    saved = row(db_pair, "sessions", "id_hash", session_hash)
    assert saved["expires_at"] - saved["created_at"] == timedelta(hours=8)
    assert saved["last_seen_at"] == saved["created_at"]
    assert codec.open("csrf", session_hash, bytes(saved["csrf_ciphertext"])) == session.csrf_token
    assert codec.open("refresh", session_hash, bytes(saved["refresh_ciphertext"])) == refresh
    assert all(
        secret not in repr(saved) and secret not in repr(session)
        for secret in (session.session_id, session.csrf_token, refresh)
    )
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET last_seen_at=clock_timestamp()-interval '1min'"),
        )
        conn.execute(
            text("INSERT INTO global_grants VALUES (:id,'project.create')"),
            {"id": session.principal.principal_id},
        )
    independent = IdentityStore(db_pair.runtime, codec, ISSUER)
    active = independent.authenticate_session(session.session_id)
    assert active.principal.can_create_project is True
    assert active.csrf_token == session.csrf_token and session.csrf_token not in repr(active)
    touched = row(db_pair, "sessions", "id_hash", session_hash)
    assert touched["last_seen_at"] >= saved["last_seen_at"]
    assert active.expires_at == touched["expires_at"] == saved["expires_at"]
    with db_pair.migrator.begin() as conn:
        conn.execute(text("DELETE FROM global_grants"))
    assert store.authenticate_session(session.session_id).principal.can_create_project is False


def test_session_clock_starts_after_principal_lock_wait(store, db_pair, identity):
    principal = store.provision_identity(identity)
    with (
        observe_statement(
            db_pair.runtime,
            lambda sql: "principals" in sql and ("insert" in sql or "for update" in sql),
        ) as attempted,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        with db_pair.migrator.begin() as conn:
            conn.execute(
                text("SELECT id FROM principals WHERE id=:id FOR UPDATE"),
                {"id": principal.principal_id},
            )
            future = executor.submit(store.create_session, identity)
            assert attempted.wait(timeout=5)
            conn.execute(text("SELECT pg_sleep(0.15)"))
            before_unlock = conn.scalar(text("SELECT clock_timestamp()"))
        session = future.result(timeout=10)
    saved = row(db_pair, "sessions", "id_hash", token_hash(session.session_id))
    assert saved["created_at"] >= before_unlock
    assert saved["created_at"] == saved["last_seen_at"]
    assert saved["expires_at"] - saved["created_at"] == timedelta(hours=8)


def test_session_commit_rollback_includes_new_identity_and_account_rotation(
    store, db_pair, identity
):
    old, other_device = store.create_session(identity), store.create_session(identity)
    new_identity = Identity(ISSUER, "different-account", "Another person")
    commit_fault(db_pair, "sessions", "INSERT")
    error = denied(503, lambda: store.create_session(new_identity, previous_session=old.session_id))
    assert "synthetic-confidential-db-marker" not in "".join(traceback.format_exception(error))
    assert count(db_pair, "principals") == 1 and count(db_pair, "sessions") == 2
    assert (
        store.authenticate_session(old.session_id).principal.principal_id
        == old.principal.principal_id
    )
    with db_pair.migrator.begin() as conn:
        conn.execute(text("DROP TRIGGER b2a1_fail_at_commit ON sessions"))
    replacement = store.create_session(new_identity, previous_session=old.session_id)
    denied(401, lambda: store.authenticate_session(old.session_id))
    assert replacement.principal.principal_id != old.principal.principal_id
    assert store.authenticate_session(other_device.session_id).principal == other_device.principal
    assert count(db_pair, "principals") == 2 and count(db_pair, "sessions") == 2
    store.create_session(identity, previous_session="malformed-previous-cookie")
    assert count(db_pair, "sessions") == 3


def test_deactivation_denies_existing_session_and_does_not_touch(store, db_pair, identity):
    session = store.create_session(identity)
    identifier = token_hash(session.session_id)
    before = row(db_pair, "sessions", "id_hash", identifier)
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("UPDATE principals SET active=false WHERE id=:id"),
            {"id": session.principal.principal_id},
        )
    denied(401, lambda: store.authenticate_session(session.session_id))
    assert row(db_pair, "sessions", "id_hash", identifier)["last_seen_at"] == before["last_seen_at"]


def test_session_from_other_trusted_issuer_is_denied_without_touch(store, db_pair, codec, identity):
    session = store.create_session(identity)
    identifier = token_hash(session.session_id)
    before = row(db_pair, "sessions", "id_hash", identifier)
    foreign = IdentityStore(db_pair.runtime, codec, "https://different-issuer.invalid")
    denied(401, lambda: foreign.authenticate_session(session.session_id))
    assert row(db_pair, "sessions", "id_hash", identifier)["last_seen_at"] == before["last_seen_at"]


@pytest.mark.parametrize("corruption", ["wrong_key", "other_record", "other_purpose"])
def test_bound_ciphertext_failure_is_safe_and_does_not_touch(store, db_pair, identity, corruption):
    session = store.create_session(identity, refresh_token="synthetic-refresh")
    identifier = token_hash(session.session_id)
    if corruption == "wrong_key":
        target = IdentityStore(db_pair.runtime, SecretCodec(Fernet.generate_key()), ISSUER)
    else:
        target = store
        source = session if corruption == "other_purpose" else store.create_session(identity)
        source_row = row(db_pair, "sessions", "id_hash", token_hash(source.session_id))
        source_field = "refresh_ciphertext" if corruption == "other_purpose" else "csrf_ciphertext"
        with db_pair.migrator.begin() as conn:
            conn.execute(
                text("UPDATE sessions SET csrf_ciphertext=:cipher WHERE id_hash=:id"),
                {"cipher": source_row[source_field], "id": identifier},
            )
    before = row(db_pair, "sessions", "id_hash", identifier)
    error = denied(503, lambda: target.authenticate_session(session.session_id))
    assert session.csrf_token not in "".join(traceback.format_exception(error))
    assert row(db_pair, "sessions", "id_hash", identifier)["last_seen_at"] == before["last_seen_at"]


def test_revoke_commits_before_return_and_preserves_other_devices(store, db_pair, identity):
    session = store.create_session(identity, refresh_token="synthetic-refresh")
    other = store.create_session(identity)
    result = store.revoke_session(session.session_id)
    assert result.refresh_token == "synthetic-refresh" and result.secret_error is False
    assert "synthetic-refresh" not in repr(result)
    assert row(db_pair, "sessions", "id_hash", token_hash(session.session_id)) is None
    denied(401, lambda: store.authenticate_session(session.session_id))
    denied(401, lambda: store.revoke_session(session.session_id))
    denied(401, lambda: store.revoke_session("invalid"))
    assert store.authenticate_session(other.session_id).principal == other.principal


@pytest.mark.parametrize("fail_commit", [False, True])
def test_corrupt_refresh_revokes_locally_unless_commit_fails(store, db_pair, identity, fail_commit):
    session = store.create_session(identity, refresh_token="synthetic-refresh")
    identifier = token_hash(session.session_id)
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET refresh_ciphertext=:cipher WHERE id_hash=:id"),
            {"cipher": b"synthetic-corrupt-cipher", "id": identifier},
        )
    if fail_commit:
        commit_fault(db_pair, "sessions", "DELETE")
        denied(503, lambda: store.revoke_session(session.session_id))
        assert row(db_pair, "sessions", "id_hash", identifier) is not None
    else:
        result = store.revoke_session(session.session_id)
        assert result.refresh_token is None and result.secret_error is True
        assert row(db_pair, "sessions", "id_hash", identifier) is None


@pytest.mark.parametrize("failure", [ValueError, TypeError, OSError])
def test_provider_failure_during_revoke_is_safe_and_preserves_session(
    store, db_pair, identity, monkeypatch, failure
):
    session = store.create_session(identity, refresh_token="synthetic-refresh")
    identifier = token_hash(session.session_id)
    before = row(db_pair, "sessions", "id_hash", identifier)

    def fail_provider(self, token, ttl=None):
        raise failure("synthetic-confidential-provider-marker")

    monkeypatch.setattr(Fernet, "decrypt", fail_provider)
    error = denied(503, lambda: store.revoke_session(session.session_id))
    assert type(error) is DomainError
    assert error.__context__ is None and error.__cause__ is None
    assert "synthetic-confidential-provider-marker" not in "".join(
        traceback.format_exception(error)
    )
    assert row(db_pair, "sessions", "id_hash", identifier) == before


@pytest.mark.parametrize("first_method", ["authenticate_session", "revoke_session"])
def test_auth_revoke_serialization_never_resurrects_session(store, db_pair, identity, first_method):
    session = store.create_session(identity)
    locked, release, second_attempt = Event(), Event(), Event()
    second_method = (
        "revoke_session" if first_method == "authenticate_session" else "authenticate_session"
    )

    def after(conn, cursor, statement, parameters, context, many):
        if (
            "sessions" in statement.lower()
            and "for update" in statement.lower()
            and current_thread().name.startswith("first")
            and not locked.is_set()
        ):
            locked.set()
            assert release.wait(timeout=5)

    def before(conn, cursor, statement, parameters, context, many):
        if current_thread().name.startswith("second") and "for update" in statement.lower():
            second_attempt.set()

    event.listen(db_pair.runtime, "after_cursor_execute", after)
    event.listen(db_pair.runtime, "before_cursor_execute", before)
    try:
        with (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="first") as one,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="second") as two,
        ):
            first = one.submit(getattr(store, first_method), session.session_id)
            try:
                assert locked.wait(timeout=5)
                second = two.submit(getattr(store, second_method), session.session_id)
                assert second_attempt.wait(timeout=5)
            finally:
                release.set()
            first.result(timeout=10)
            if first_method == "revoke_session":
                denied(401, lambda: second.result(timeout=10))
            else:
                second.result(timeout=10)
    finally:
        release.set()
        event.remove(db_pair.runtime, "after_cursor_execute", after)
        event.remove(db_pair.runtime, "before_cursor_execute", before)
    assert count(db_pair, "sessions") == 0
    denied(401, lambda: store.authenticate_session(session.session_id))


def test_auth_and_same_identity_login_have_no_principal_session_lock_cycle(
    store, db_pair, identity
):
    old = store.create_session(identity)
    auth_locked, login_waiting, release_auth = Event(), Event(), Event()

    def after(conn, cursor, statement, parameters, context, many):
        if (
            current_thread().name.startswith("auth")
            and "sessions" in statement.lower()
            and "for update" in statement.lower()
            and not auth_locked.is_set()
        ):
            auth_locked.set()
            assert release_auth.wait(timeout=5)

    def before(conn, cursor, statement, parameters, context, many):
        if (
            current_thread().name.startswith("login")
            and "sessions" in statement.lower()
            and ("for update" in statement.lower() or "delete" in statement.lower())
        ):
            login_waiting.set()

    event.listen(db_pair.runtime, "after_cursor_execute", after)
    event.listen(db_pair.runtime, "before_cursor_execute", before)
    try:
        with (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="auth") as one,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="login") as two,
        ):
            auth = one.submit(store.authenticate_session, old.session_id)
            try:
                assert auth_locked.wait(timeout=5)
                login = two.submit(store.create_session, identity, previous_session=old.session_id)
                assert login_waiting.wait(timeout=5)
            finally:
                release_auth.set()
            assert auth.result(timeout=10).principal.principal_id == old.principal.principal_id
            replacement = login.result(timeout=10)
    finally:
        release_auth.set()
        event.remove(db_pair.runtime, "after_cursor_execute", after)
        event.remove(db_pair.runtime, "before_cursor_execute", before)
    denied(401, lambda: store.authenticate_session(old.session_id))
    assert store.authenticate_session(replacement.session_id).principal == old.principal


def test_cleanup_is_bounded_stable_skips_locks_and_preserves_active_entities(
    store, db_pair, identity
):
    flows = sorted(token_hash(store.create_flow().state) for _ in range(5))
    sessions = sorted(token_hash(store.create_session(identity).session_id) for _ in range(5))
    principal = store.provision_identity(identity)
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("INSERT INTO global_grants VALUES (:id,'project.create')"),
            {"id": principal.principal_id},
        )
    ProjectService(
        db_pair.runtime, CursorSigner(b"synthetic-b2a1-cursor-key-" + b"x" * 32)
    ).create_project(
        principal.principal_id,
        body={"name": "Synthetic project", "description": "Cleanup preservation fixture"},
        key=str(uuid4()),
        request_id=uuid4(),
    )
    protected_tables = (
        "principals",
        "organizations",
        "global_grants",
        "projects",
        "memberships",
        "audit_events",
        "idempotency_receipts",
    )
    protected_counts = tuple(count(db_pair, table) for table in protected_tables)
    assert all(value > 0 for value in protected_counts)
    with db_pair.migrator.begin() as conn:
        for table, key, ids in (
            ("oidc_flows", "state_hash", flows),
            ("sessions", "id_hash", sessions),
        ):
            conn.execute(
                text(
                    f"UPDATE {table} SET created_at='2026-01-01T00:00:00Z', "
                    f"expires_at='2026-01-01T00:01:00Z' WHERE {key} IN (:a,:b,:c,:d)"
                ),
                dict(zip(("a", "b", "c", "d"), ids[:4], strict=True)),
            )
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("SELECT state_hash FROM oidc_flows WHERE state_hash=:id FOR UPDATE"),
            {"id": flows[0]},
        )
        conn.execute(
            text("SELECT id_hash FROM sessions WHERE id_hash=:id FOR UPDATE"), {"id": sessions[0]}
        )
        assert store.cleanup_expired(limit=2) == (2, 2)
    for table, key, ids in (("oidc_flows", "state_hash", flows), ("sessions", "id_hash", sessions)):
        assert row(db_pair, table, key, ids[0]) is not None
        assert row(db_pair, table, key, ids[1]) is row(db_pair, table, key, ids[2]) is None
        assert row(db_pair, table, key, ids[3]) is not None
        assert row(db_pair, table, key, ids[4]) is not None
    assert store.cleanup_expired() == (2, 2)
    assert store.cleanup_expired() == (0, 0)
    assert protected_counts == tuple(count(db_pair, table) for table in protected_tables)
    for invalid in (0, 101, True, 1.5):
        denied(422, lambda invalid=invalid: store.cleanup_expired(limit=invalid))


def test_cleanup_includes_idle_expiry_without_waiting_for_absolute(store, db_pair, identity):
    expired = store.create_session(identity)
    active = store.create_session(identity)
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text(
                "UPDATE sessions SET last_seen_at=clock_timestamp()-interval '31min' "
                "WHERE id_hash=:id"
            ),
            {"id": token_hash(expired.session_id)},
        )
    denied(401, lambda: store.authenticate_session(expired.session_id))
    assert store.cleanup_expired() == (0, 1)
    assert store.authenticate_session(active.session_id).principal == active.principal


def test_default_cleanup_never_deletes_more_than_one_hundred_of_each_kind(
    store, db_pair, identity, codec
):
    principal = store.provision_identity(identity)
    with db_pair.migrator.begin() as conn:
        expired = conn.scalar(text("SELECT clock_timestamp()-interval '1h'"))
        created = expired - timedelta(hours=8)
        flows, sessions = [], []
        for _ in range(101):
            flow_id, session_id = token_hash(new_token()), token_hash(new_token())
            flows.append(
                {
                    "id": flow_id,
                    "browser": token_hash(new_token()),
                    "nonce": token_hash(new_token()),
                    "cipher": codec.seal("verifier", flow_id, new_token()),
                    "created": created,
                    "expired": expired,
                }
            )
            sessions.append(
                {
                    "id": session_id,
                    "principal": principal.principal_id,
                    "cipher": codec.seal("csrf", session_id, new_token()),
                    "created": created,
                    "expired": expired,
                }
            )
        conn.execute(
            text(
                "INSERT INTO oidc_flows(state_hash,browser_hash,nonce_hash,verifier_ciphertext,"
                "created_at,expires_at) VALUES (:id,:browser,:nonce,:cipher,:created,:expired)"
            ),
            flows,
        )
        conn.execute(
            text(
                "INSERT INTO sessions(id_hash,principal_id,csrf_ciphertext,created_at,last_seen_at,"
                "expires_at) VALUES (:id,:principal,:cipher,:created,:created,:expired)"
            ),
            sessions,
        )
    assert store.cleanup_expired() == (100, 100)
    assert count(db_pair, "oidc_flows") == count(db_pair, "sessions") == 1
    assert store.cleanup_expired() == (1, 1)
