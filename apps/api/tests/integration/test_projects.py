"""SPEC-0001 B1: real PostgreSQL invariants, not HTTP/OIDC acceptance."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import event, text

from torii_api.application.projects import ProjectService
from torii_api.domain.errors import DomainError
from torii_api.security.cursor import CursorSigner
from torii_api.storage.receipts import ReceiptKey

pytestmark = pytest.mark.integration


@pytest.fixture
def sample(db_pair):
    ids = {name: uuid4() for name in ("org", "owner", "editor", "reader", "other", "second", "off")}
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("INSERT INTO organizations(id,name) VALUES (:id, :name)"),
            {"id": ids["org"], "name": "Synthetic B1"},
        )
        for name, identifier in ids.items():
            if name == "org":
                continue
            conn.execute(
                text(
                    "INSERT INTO principals(id,org_id,issuer,subject,display_name,active) "
                    "VALUES (:id,:org,:issuer,:subject,:name,:active)"
                ),
                {
                    "id": identifier,
                    "org": ids["org"],
                    "issuer": "https://fixture.invalid",
                    "subject": name,
                    "name": name,
                    "active": name != "off",
                },
            )
        for name in ("owner", "other"):
            conn.execute(
                text("INSERT INTO global_grants VALUES (:id,'project.create')"), {"id": ids[name]}
            )
    service = ProjectService(
        db_pair.runtime, CursorSigner(b"synthetic-test-cursor-key-" + b"x" * 32)
    )
    return service, ids


def create(service, ids, name="Synthetic project", key=None, actor="owner"):
    return service.create_project(
        ids[actor],
        body={"name": name, "description": "Synthetic only"},
        key=key or str(uuid4()),
        request_id=uuid4(),
    )


def policy(service, ids, project, members, tag=None, key=None, actor="owner"):
    return service.replace_policy(
        ids[actor],
        project,
        body={
            "members": [{"principal_id": str(ids[name]), "role": role} for name, role in members]
        },
        if_match=tag or service.get_policy(ids[actor], project).headers["ETag"],
        key=key or str(uuid4()),
        request_id=uuid4(),
    )


def denied(status, call, code=None):
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.status == status
    if code:
        assert caught.value.code == code
    return caught.value


def counts(engine):
    with engine.connect() as conn:
        return tuple(
            conn.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("projects", "memberships", "audit_events", "idempotency_receipts")
        )


def test_atomic_create_receipt_and_new_service_instance(sample, db_pair):
    service, ids = sample
    key = str(uuid4())
    first = create(service, ids, key=key)
    replay = create(service, ids, key=key)
    assert first == replay
    assert first.status_code == 201
    assert counts(db_pair.runtime) == (1, 1, 1, 1)
    independent = ProjectService(db_pair.runtime, CursorSigner(b"x" * 32))
    assert independent.get_project(ids["owner"], UUID(first.body["id"])).body == first.body
    denied(409, lambda: create(service, ids, "Different", key=key), "idempotency_conflict")
    assert counts(db_pair.runtime) == (1, 1, 1, 1)


def test_parallel_identical_create_is_one_transaction_effect(sample, db_pair):
    service, ids = sample
    key, barrier = str(uuid4()), Barrier(2)

    def execute():
        barrier.wait(timeout=5)
        return create(service, ids, key=key)

    with ThreadPoolExecutor(max_workers=2) as executor:
        a, b = executor.submit(execute), executor.submit(execute)
        assert a.result(timeout=15) == b.result(timeout=15)
    assert counts(db_pair.runtime) == (1, 1, 1, 1)


@pytest.mark.parametrize("relation", ["audit_events", "idempotency_receipts"])
def test_fault_rolls_back_create_and_key_can_retry(sample, db_pair, relation):
    service, ids = sample
    key = str(uuid4())
    # Fault is a real DB constraint failure, installed only by the fixture migrator.
    with db_pair.migrator.begin() as conn:
        conn.execute(text(f"ALTER TABLE {relation} ADD CONSTRAINT b1_fault CHECK (false)"))
    denied(503, lambda: create(service, ids, key=key))
    assert counts(db_pair.runtime) == (0, 0, 0, 0)
    with db_pair.migrator.begin() as conn:
        conn.execute(text(f"ALTER TABLE {relation} DROP CONSTRAINT b1_fault"))
    assert create(service, ids, key=key).status_code == 201


def test_roles_visibility_and_fresh_active_state(sample, db_pair):
    service, ids = sample
    denied(403, lambda: create(service, ids, actor="reader"))
    denied(401, lambda: create(service, ids, actor="off"))
    project = UUID(create(service, ids).body["id"])
    policy(service, ids, project, [("owner", "owner"), ("editor", "editor"), ("reader", "reader")])
    for name in ("owner", "editor", "reader"):
        assert service.get_project(ids[name], project).body["my_role"] == name
        assert len(service.list_projects(ids[name]).body["items"]) == 1
    assert service.list_projects(ids["other"]).body["items"] == []
    for method in (
        service.get_project,
        service.get_policy,
        service.list_memberships,
        service.list_audit,
    ):
        assert (
            denied(404, lambda method=method: method(ids["other"], project)).code
            == denied(404, lambda method=method: method(ids["other"], uuid4())).code
        )
    for name in ("editor", "reader"):
        for method in (service.get_policy, service.list_memberships, service.list_audit):
            denied(403, lambda method=method, name=name: method(ids[name], project))
        denied(
            403,
            lambda name=name: service.replace_policy(
                ids[name],
                project,
                body={"actor": "injected"},
                key=None,
                if_match=None,
                request_id=uuid4(),
            ),
        )
    with db_pair.migrator.begin() as conn:
        conn.execute(text("UPDATE principals SET active=false WHERE id=:id"), {"id": ids["reader"]})
    denied(401, lambda: service.get_project(ids["reader"], project))


def test_replay_create_hidden_precedes_fingerprint_and_global_grant(sample, db_pair):
    service, ids = sample
    key = str(uuid4())
    project = UUID(create(service, ids, key=key).body["id"])
    policy(service, ids, project, [("second", "owner")])
    denied(404, lambda: create(service, ids, key=key))
    denied(404, lambda: create(service, ids, "changed", key=key))
    with db_pair.migrator.begin() as conn:
        conn.execute(text("DELETE FROM global_grants WHERE principal_id=:id"), {"id": ids["owner"]})
    denied(403, lambda: create(service, ids, key=key))


def test_policy_noop_receipt_etags_and_history(sample, db_pair):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    original = service.get_policy(ids["owner"], project)
    unchanged = policy(service, ids, project, [("owner", "owner")])
    assert unchanged == original
    assert counts(db_pair.runtime) == (1, 1, 1, 2)
    key = str(uuid4())
    changed = policy(service, ids, project, [("owner", "owner"), ("reader", "reader")], key=key)
    assert changed.body["revision"] == 2
    replay = policy(
        service,
        ids,
        project,
        [("owner", "owner"), ("reader", "reader")],
        tag=original.headers["ETag"],
        key=key,
    )
    assert replay == changed
    denied(
        412,
        lambda: policy(service, ids, project, [("owner", "owner")], tag=original.headers["ETag"]),
    )
    for tag, status in ((None, 428), ("*", 400), ("W/" + changed.headers["ETag"], 400)):
        denied(
            status,
            lambda tag=tag: service.replace_policy(
                ids["owner"],
                project,
                body={"members": [{"principal_id": str(ids["owner"]), "role": "owner"}]},
                key=str(uuid4()),
                if_match=tag,
                request_id=uuid4(),
            ),
        )
    denied(409, lambda: policy(service, ids, project, [("owner", "reader")]), "last_owner")
    denied(404, lambda: policy(service, ids, project, [("owner", "owner"), ("off", "reader")]))
    members = service.list_memberships(ids["owner"], project).body["items"]
    policy(service, ids, project, [("owner", "owner"), ("reader", "editor")])
    assert [m["created_at"] for m in members] == [
        m["created_at"] for m in service.list_memberships(ids["owner"], project).body["items"]
    ]


def test_parallel_two_owner_changes_leave_owner(sample, db_pair):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    changed = policy(service, ids, project, [("owner", "owner"), ("second", "owner")])
    barrier = Barrier(2)

    def execute(actor, remaining):
        barrier.wait(timeout=5)
        try:
            return policy(
                service,
                ids,
                project,
                [(remaining, "owner")],
                tag=changed.headers["ETag"],
                actor=actor,
            ).status_code
        except DomainError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(execute, "owner", "second")
        b = executor.submit(execute, "second", "owner")
        assert sorted([a.result(timeout=15), b.result(timeout=15)]) == [200, 412]
    with db_pair.runtime.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM memberships WHERE role='owner'")) == 1


def test_revoke_while_waiting_for_project_lock_is_rechecked(sample, db_pair):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    current = policy(service, ids, project, [("owner", "owner"), ("second", "owner")])
    waiting = Event()

    def before(conn, cursor, statement, parameters, context, many):
        if "FOR UPDATE" in statement:
            waiting.set()

    event.listen(db_pair.runtime, "before_cursor_execute", before)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with db_pair.migrator.begin() as conn:
                conn.execute(
                    text("SELECT id FROM projects WHERE id=:id FOR UPDATE"), {"id": project}
                )
                attempt = executor.submit(
                    policy, service, ids, project, [("owner", "owner")], current.headers["ETag"]
                )
                assert waiting.wait(timeout=5)
                conn.execute(
                    text("DELETE FROM memberships WHERE project_id=:p AND principal_id=:a"),
                    {"p": project, "a": ids["owner"]},
                )
                conn.execute(
                    text("UPDATE projects SET acl_revision=acl_revision+1 WHERE id=:id"),
                    {"id": project},
                )
            denied(404, lambda: attempt.result(timeout=10))
    finally:
        event.remove(db_pair.runtime, "before_cursor_execute", before)


def test_literal_filter_pagination_ties_and_cursor_scope(sample, db_pair):
    service, ids = sample
    for name in ("A%_\\", "a normal", "Another"):
        create(service, ids, name)
    create(service, ids, "A%_\\", actor="other")
    with db_pair.migrator.begin() as conn:
        conn.execute(text("UPDATE projects SET created_at='2026-01-01T00:00:00Z'"))
    assert len(service.list_projects(ids["owner"], q="%_\\").body["items"]) == 1
    seen, cursor = [], None
    for _ in range(3):
        page = service.list_projects(ids["owner"], limit=1, cursor=cursor, q="a").body
        seen.extend(p["id"] for p in page["items"])
        cursor = page["next_cursor"]
    assert len(set(seen)) == 3 and cursor is None
    token = service.list_projects(ids["owner"], limit=1).body["next_cursor"]
    denied(400, lambda: service.list_projects(ids["other"], cursor=token))
    denied(400, lambda: service.list_projects(ids["owner"], cursor=token, q="A"))
    denied(400, lambda: service.list_projects(ids["owner"], cursor=token + "x"))
    project = UUID(seen[0])
    denied(400, lambda: service.list_audit(ids["owner"], project, cursor=token))


def test_expired_receipt_new_effect_and_safe_dto_contracts(sample, db_pair):
    service, ids = sample
    key = str(uuid4())
    first = create(service, ids, key=key)
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text(
                "UPDATE idempotency_receipts SET created_at=clock_timestamp()-interval '26h', "
                "expires_at=clock_timestamp()-interval '1h'"
            )
        )
    second = create(service, ids, key=key)
    assert first.body["id"] != second.body["id"]
    project = UUID(first.body["id"])
    contract = json.loads(
        (
            Path(__file__).resolve().parents[4]
            / "specs/0001-project-object-version/contracts/openapi.json"
        ).read_text(encoding="utf-8")
    )
    for schema, result in [
        ("Project", first),
        ("ProjectPage", service.list_projects(ids["owner"])),
        ("AccessPolicy", service.get_policy(ids["owner"], project)),
        ("MembershipPage", service.list_memberships(ids["owner"], project)),
        ("AuditPage", service.list_audit(ids["owner"], project)),
    ]:
        validator = Draft202012Validator(
            {"$ref": f"#/components/schemas/{schema}", **contract}, format_checker=FormatChecker()
        )
        validator.validate(result.body)
    with db_pair.runtime.connect() as conn:
        for delta in conn.scalars(text("SELECT delta FROM audit_events")):
            assert "Synthetic" not in json.dumps(delta)


@pytest.mark.parametrize("relation", ["audit_events", "idempotency_receipts"])
def test_policy_fault_rolls_back_members_revision_and_receipt(sample, db_pair, relation):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    before = service.get_policy(ids["owner"], project)
    original_counts = counts(db_pair.runtime)
    key = str(uuid4())
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text(f"ALTER TABLE {relation} ADD CONSTRAINT b1_fault CHECK (false) NOT VALID")
        )
    denied(
        503,
        lambda: policy(service, ids, project, [("owner", "owner"), ("reader", "reader")], key=key),
    )
    assert service.get_policy(ids["owner"], project) == before
    assert counts(db_pair.runtime) == original_counts
    with db_pair.migrator.begin() as conn:
        conn.execute(text(f"ALTER TABLE {relation} DROP CONSTRAINT b1_fault"))
    assert (
        policy(service, ids, project, [("owner", "owner"), ("reader", "reader")], key=key).body[
            "revision"
        ]
        == 2
    )


def test_lock_timeout_is_safe_503_without_partial_effects(sample, db_pair):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    tag = service.get_policy(ids["owner"], project).headers["ETag"]

    def shorten_lock(conn, cursor, statement, parameters, context, many):
        if "FOR UPDATE" in statement:
            conn.exec_driver_sql("SET LOCAL lock_timeout='50ms'")

    event.listen(db_pair.runtime, "before_cursor_execute", shorten_lock)
    try:
        with db_pair.migrator.begin() as conn:
            conn.execute(text("SELECT id FROM projects WHERE id=:id FOR UPDATE"), {"id": project})
            error = denied(
                503,
                lambda: policy(
                    service, ids, project, [("owner", "owner"), ("reader", "reader")], tag=tag
                ),
            )
            assert error.__suppress_context__
    finally:
        event.remove(db_pair.runtime, "before_cursor_execute", shorten_lock)
    assert counts(db_pair.runtime) == (1, 1, 1, 1)


def test_create_grant_revoke_during_advisory_lock_wait(sample, db_pair):
    service, ids = sample
    key, waiting = str(uuid4()), Event()

    def before(conn, cursor, statement, parameters, context, many):
        if "pg_advisory_xact_lock" in statement:
            waiting.set()

    event.listen(db_pair.runtime, "before_cursor_execute", before)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with db_pair.migrator.begin() as conn:
                ReceiptKey(ids["owner"], ids["org"], "createProject", UUID(key)).lock_create(conn)
                attempt = executor.submit(create, service, ids, key=key)
                assert waiting.wait(timeout=5)
                conn.execute(
                    text("DELETE FROM global_grants WHERE principal_id=:actor"),
                    {"actor": ids["owner"]},
                )
            denied(403, lambda: attempt.result(timeout=10))
    finally:
        event.remove(db_pair.runtime, "before_cursor_execute", before)
    assert counts(db_pair.runtime) == (0, 0, 0, 0)


def test_policy_read_etag_and_body_share_snapshot(sample, db_pair):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    before = service.get_policy(ids["owner"], project)

    def concurrent_change(conn, cursor, statement, parameters, context, many):
        if "SELECT principal_id,role FROM memberships" in statement:
            with db_pair.migrator.begin() as writer:
                writer.execute(
                    text(
                        "INSERT INTO memberships(project_id,principal_id,org_id,role) "
                        "VALUES (:project,:principal,:org,'reader')"
                    ),
                    {"project": project, "principal": ids["reader"], "org": ids["org"]},
                )
                writer.execute(
                    text("UPDATE projects SET acl_revision=2 WHERE id=:id"), {"id": project}
                )

    event.listen(db_pair.runtime, "before_cursor_execute", concurrent_change)
    try:
        assert service.get_policy(ids["owner"], project) == before
    finally:
        event.remove(db_pair.runtime, "before_cursor_execute", concurrent_change)
    assert service.get_policy(ids["owner"], project).body["revision"] == 2


def test_membership_and_audit_pages_with_ties_and_project_binding(sample, db_pair):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    policy(service, ids, project, [("owner", "owner"), ("reader", "reader"), ("editor", "editor")])
    policy(service, ids, project, [("owner", "owner"), ("reader", "editor"), ("editor", "editor")])
    other = UUID(create(service, ids, "Second").body["id"])
    with db_pair.migrator.begin() as conn:
        conn.execute(text("UPDATE memberships SET created_at='2026-01-01T00:00:00Z'"))
        conn.execute(text("UPDATE audit_events SET occurred_at='2026-01-01T00:00:00Z'"))
    for method, id_field in (
        (service.list_memberships, "principal_id"),
        (service.list_audit, "id"),
    ):
        first = method(ids["owner"], project, limit=1).body
        token = first["next_cursor"]
        denied(400, lambda method=method, token=token: method(ids["owner"], other, cursor=token))
        result, cursor = [], None
        for _ in range(3):
            page = method(ids["owner"], project, limit=1, cursor=cursor).body
            result.extend(item[id_field] for item in page["items"])
            cursor = page["next_cursor"]
        assert len(set(result)) == 3 and cursor is None
        assert result == sorted(result)


def test_policy_replay_is_denied_after_role_demotion(sample):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    old_tag = service.get_policy(ids["owner"], project).headers["ETag"]
    key = str(uuid4())
    members = [("owner", "owner"), ("second", "owner")]
    policy(service, ids, project, members, tag=old_tag, key=key)
    policy(service, ids, project, [("owner", "reader"), ("second", "owner")], actor="second")
    denied(403, lambda: policy(service, ids, project, members, tag=old_tag, key=key))


def test_commit_failure_does_not_return_success(sample, db_pair):
    service, ids = sample
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION b1_commit_fault() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN RAISE EXCEPTION 'synthetic confidential marker'; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE CONSTRAINT TRIGGER b1_fail_at_commit AFTER INSERT ON projects "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION b1_commit_fault()"
            )
        )
    error = denied(503, lambda: create(service, ids))
    import traceback

    assert "confidential" not in "".join(traceback.format_exception(error))
    assert counts(db_pair.runtime) == (0, 0, 0, 0)


def test_revision_ceiling_and_unknown_principal_leave_no_effect(sample, db_pair):
    service, ids = sample
    project = UUID(create(service, ids).body["id"])
    original = counts(db_pair.runtime)
    # A UUIDv1 is schema-valid, so an unknown principal must be hidden with 404.
    ids["unknown"] = UUID("a6b1caac-1ea2-11f1-8a14-0242ac120002")
    denied(404, lambda: policy(service, ids, project, [("owner", "owner"), ("unknown", "reader")]))
    denied(422, lambda: policy(service, ids, project, [("owner", "owner"), ("owner", "reader")]))
    with db_pair.migrator.begin() as conn:
        conn.execute(
            text("UPDATE projects SET acl_revision=9007199254740991 WHERE id=:id"), {"id": project}
        )
    denied(
        409,
        lambda: policy(service, ids, project, [("owner", "owner"), ("reader", "reader")]),
        "revision_exhausted",
    )
    assert counts(db_pair.runtime) == original


@pytest.mark.parametrize(
    "marker",
    [
        ["not-a-timestamp", str(uuid4())],
        ["2026-01-01T00:00:00", str(uuid4())],
        ["2026-01-01T00:00:00Z", "not-a-uuid"],
    ],
)
def test_signed_but_invalid_marker_is_safe_400(sample, marker):
    service, ids = sample
    signer = CursorSigner(b"synthetic-test-cursor-key-" + b"x" * 32)
    cursor = signer.issue(
        {"actor": str(ids["owner"]), "path": "/api/v1/projects", "q": ""},
        marker,
        now=datetime.now(UTC),
    )
    denied(400, lambda: service.list_projects(ids["owner"], cursor=cursor), "invalid_cursor")
