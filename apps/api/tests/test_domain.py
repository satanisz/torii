"""SPEC-0001 AC-08/10/14: pure invariants, not integration acceptance."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from torii_api.domain.errors import DomainError
from torii_api.domain.policy import Capability, Member, Role, authorize, validate_members
from torii_api.domain.values import check_etag, etag, validate_name
from torii_api.security.cursor import CursorSigner


@pytest.mark.parametrize("role", list(Role))
def test_all_members_read(role: Role) -> None:
    authorize(role, Capability.READ)


@pytest.mark.parametrize("role", [Role.READER, Role.EDITOR])
@pytest.mark.parametrize("action", [Capability.ACCESS, Capability.AUDIT, Capability.ARCHIVE])
def test_owner_operations_deny_other_members(role: Role, action: Capability) -> None:
    with pytest.raises(DomainError, match="forbidden") as err:
        authorize(role, action)
    assert err.value.status == 403


@pytest.mark.parametrize("action", list(Capability))
def test_invisible_and_missing_project_are_indistinguishable(action: Capability) -> None:
    with pytest.raises(DomainError) as err:
        authorize(None, action)
    assert (err.value.status, err.value.code) == (404, "not_found")


def test_reader_cannot_edit_and_editor_can() -> None:
    with pytest.raises(DomainError):
        authorize(Role.READER, Capability.EDIT)
    authorize(Role.EDITOR, Capability.EDIT)


def test_policy_requires_unique_active_owner_and_bounds() -> None:
    owner, reader = uuid4(), uuid4()
    validate_members([Member(owner, Role.OWNER), Member(reader, Role.READER)], {owner, reader})
    for members, active, code in [
        ([], set(), "last_owner"),
        ([Member(owner, Role.READER)], {owner}, "last_owner"),
        ([Member(owner, Role.OWNER)], set(), "not_found"),
        ([Member(owner, Role.OWNER)] * 2, {owner}, "validation_failed"),
        ([Member(uuid4(), Role.OWNER) for _ in range(101)], set(), "validation_failed"),
    ]:
        with pytest.raises(DomainError) as err:
            validate_members(members, active)
        assert err.value.code == code


@pytest.mark.parametrize("name", ["", " leading", "trailing\t", "x" * 121, "\n"])
def test_names_rejected_without_silent_normalization(name: str) -> None:
    with pytest.raises(DomainError, match="validation_failed"):
        validate_name(name)


def test_unicode_name_preserved() -> None:
    assert validate_name("Żółć 東京") == "Żółć 東京"


def test_strong_etag_preconditions() -> None:
    object_id = uuid4()
    current = etag("acl", object_id, 2)
    check_etag(current, current)
    for supplied, status in [
        (None, 428),
        ("*", 400),
        (f"W/{current}", 400),
        (f"{current}, {current}", 400),
        (etag("acl", object_id, 1), 412),
        (etag("acl", uuid4(), 2), 412),
    ]:
        with pytest.raises(DomainError) as err:
            check_etag(supplied, current)
        assert err.value.status == status


def test_cursor_binding_expiry_and_tampering() -> None:
    clock = datetime(2026, 9, 19, tzinfo=UTC)
    signer = CursorSigner(b"unit-test-key-not-for-runtime-12345")
    actor = str(uuid4())
    context = {"actor": actor, "project": str(uuid4()), "list": "audit", "q": ""}
    marker = ["2026-09-19T00:00:00Z", str(uuid4())]
    token = signer.issue(context, marker, now=clock)
    assert signer.verify(token, context, now=clock) == marker
    for bad_token, bad_context, now in [
        (token, {**context, "actor": str(uuid4())}, clock),
        (token, {**context, "q": "other"}, clock),
        (token, context, clock + timedelta(minutes=15)),
        (token[:-3] + "XXX", context, clock),
        (token + ".extra", context, clock),
        ("x" * 8192, context, clock),
    ]:
        with pytest.raises(DomainError) as err:
            signer.verify(bad_token, bad_context, now=now)
        assert (err.value.status, err.value.code) == (400, "invalid_cursor")


def test_cursor_cannot_move_between_objects_in_same_project() -> None:
    clock = datetime(2026, 9, 19, tzinfo=UTC)
    signer = CursorSigner(b"unit-test-key-not-for-runtime-12345")
    context = {"actor": str(uuid4()), "path": f"/projects/{uuid4()}/objects/{uuid4()}/versions"}
    token = signer.issue(context, ["1", str(uuid4())], now=clock)
    with pytest.raises(DomainError, match="invalid_cursor"):
        signer.verify(
            token,
            {**context, "path": context["path"].replace("objects/", "objects/other-")},
            now=clock,
        )
