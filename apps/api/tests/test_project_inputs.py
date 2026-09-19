"""SPEC-0001 B1 AC-08/10/14: strict inputs, not HTTP/transaction acceptance."""

import json
from copy import deepcopy
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from torii_api.domain.errors import DomainError
from torii_api.domain.policy import Member, Role, validate_members
from torii_api.domain.project_inputs import (
    idempotency_key,
    parse_policy,
    parse_project_create,
    validate_page,
)

ROOT = Path(__file__).resolve().parents[3]
PRINCIPAL = "a2df4d4c-a807-4b03-a34f-5851d0acbb81"
VALID_PROJECT: dict[str, object] = {"name": "Żółć 東京", "description": "Opis\nbez zmian"}
VALID_MEMBER = {"principal_id": PRINCIPAL, "role": "owner"}


@pytest.mark.parametrize(
    "body,pointer",
    [
        (None, ""),
        ([], ""),
        ("secret-payload", ""),
        (False, ""),
        ({}, "/name"),
        ({"name": "A"}, "/description"),
        ({**VALID_PROJECT, "untrusted/secret~key": "secret-payload"}, ""),
        ({**VALID_PROJECT, "name": None}, "/name"),
        ({**VALID_PROJECT, "name": 1}, "/name"),
        ({**VALID_PROJECT, "name": True}, "/name"),
        ({**VALID_PROJECT, "name": []}, "/name"),
        ({**VALID_PROJECT, "name": ""}, "/name"),
        ({**VALID_PROJECT, "name": " a"}, "/name"),
        ({**VALID_PROJECT, "name": "a\t"}, "/name"),
        ({**VALID_PROJECT, "name": "a" * 121}, "/name"),
        ({**VALID_PROJECT, "name": "secret\x00payload"}, "/name"),
        ({**VALID_PROJECT, "name": "secret\ud800payload"}, "/name"),
        ({**VALID_PROJECT, "description": None}, "/description"),
        ({**VALID_PROJECT, "description": 1}, "/description"),
        ({**VALID_PROJECT, "description": {}}, "/description"),
        ({**VALID_PROJECT, "description": "a" * 4001}, "/description"),
        ({**VALID_PROJECT, "description": "secret\x00payload"}, "/description"),
        ({**VALID_PROJECT, "description": "secret\udfffpayload"}, "/description"),
    ],
)
def test_project_rejects_types_unknown_fields_and_limits(body: object, pointer: str) -> None:
    with pytest.raises(DomainError) as caught:
        parse_project_create(body)
    assert (caught.value.status, caught.value.code, caught.value.pointers) == (
        422,
        "validation_failed",
        (pointer,),
    )
    assert caught.value.args == ("validation_failed",)
    assert "secret" not in repr(caught.value)
    assert "secret" not in repr(caught.value.pointers)


@pytest.mark.parametrize("name", ["A", "a" * 120, "a\nb", "Żółć 東京", "e\u0301", "😀"])
@pytest.mark.parametrize("description", ["", "a" * 4000, "\n unchanged \t", "😀"])
def test_project_preserves_valid_unicode_and_boundaries(name: str, description: str) -> None:
    body = {"name": name, "description": description}
    assert parse_project_create(body) == (name, description)
    assert body == {"name": name, "description": description}


@pytest.mark.parametrize(
    "body,pointer",
    [
        (None, ""),
        ([], ""),
        ({}, "/members"),
        ({"members": [], "secret-key": "secret-payload"}, ""),
        ({"members": []}, "/members"),
        ({"members": None}, "/members"),
        ({"members": {}}, "/members"),
        ({"members": (VALID_MEMBER,)}, "/members"),
        ({"members": [VALID_MEMBER] * 101}, "/members"),
        ({"members": [None]}, "/members/0"),
        ({"members": [[]]}, "/members/0"),
        ({"members": [{}]}, "/members/0/principal_id"),
        ({"members": [{"principal_id": PRINCIPAL}]}, "/members/0/role"),
        ({"members": [{**VALID_MEMBER, "secret-key": "secret-payload"}]}, "/members/0"),
        (
            {"members": [{**VALID_MEMBER, "principal_id": UUID(PRINCIPAL)}]},
            "/members/0/principal_id",
        ),
        ({"members": [{**VALID_MEMBER, "principal_id": True}]}, "/members/0/principal_id"),
        (
            {"members": [{**VALID_MEMBER, "principal_id": PRINCIPAL.replace("-", "")}]},
            "/members/0/principal_id",
        ),
        (
            {"members": [{**VALID_MEMBER, "principal_id": "{" + PRINCIPAL + "}"}]},
            "/members/0/principal_id",
        ),
        (
            {"members": [{**VALID_MEMBER, "principal_id": "urn:uuid:" + PRINCIPAL}]},
            "/members/0/principal_id",
        ),
        (
            {"members": [{**VALID_MEMBER, "principal_id": PRINCIPAL + "\n"}]},
            "/members/0/principal_id",
        ),
        (
            {"members": [{**VALID_MEMBER, "principal_id": "secret-payload"}]},
            "/members/0/principal_id",
        ),
        ({"members": [{**VALID_MEMBER, "role": "Owner"}]}, "/members/0/role"),
        ({"members": [{**VALID_MEMBER, "role": "owner "}]}, "/members/0/role"),
        ({"members": [{**VALID_MEMBER, "role": ["owner"]}]}, "/members/0/role"),
        ({"members": [{**VALID_MEMBER, "role": True}]}, "/members/0/role"),
    ],
)
def test_policy_structure_errors_have_fixed_safe_pointers(body: object, pointer: str) -> None:
    with pytest.raises(DomainError) as caught:
        parse_policy(body)
    assert (caught.value.status, caught.value.code, caught.value.pointers) == (
        422,
        "validation_failed",
        (pointer,),
    )
    assert caught.value.args == ("validation_failed",)
    assert "secret" not in repr(caught.value.pointers)


@pytest.mark.parametrize(
    "identifier",
    [
        PRINCIPAL,
        PRINCIPAL.upper(),
        "f47ac10b-58cc-11cf-a447-001122334455",
        "00000000-0000-7000-8000-000000000001",
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
    ],
)
@pytest.mark.parametrize("role", ["reader", "editor", "owner"])
def test_principal_uuid_format_does_not_silently_require_v4(identifier: str, role: str) -> None:
    body = {"members": [{"principal_id": identifier, "role": role}]}
    original = deepcopy(body)
    assert parse_policy(body) == [Member(UUID(identifier), Role(role))]
    assert body == original


def test_empty_policy_is_structural_422_but_nonempty_without_owner_is_semantic_409() -> None:
    with pytest.raises(DomainError) as caught:
        parse_policy({"members": []})
    assert caught.value.status == 422
    members = parse_policy({"members": [{"principal_id": PRINCIPAL, "role": "reader"}]})
    with pytest.raises(DomainError) as caught:
        validate_members(members, {UUID(PRINCIPAL)})
    assert (caught.value.status, caught.value.code) == (409, "last_owner")


def test_activity_and_duplicate_ids_remain_transactional_semantics() -> None:
    members = parse_policy(
        {"members": [VALID_MEMBER, {**VALID_MEMBER, "principal_id": PRINCIPAL.upper()}]}
    )
    with pytest.raises(DomainError) as caught:
        validate_members(members, {UUID(PRINCIPAL)})
    assert (caught.value.status, caught.value.pointers) == (422, ("/members",))
    with pytest.raises(DomainError) as caught:
        validate_members(parse_policy({"members": [VALID_MEMBER]}), set())
    assert (caught.value.status, caught.value.code) == (404, "not_found")


def test_policy_accepts_100_members_without_mutating_input() -> None:
    body = {"members": [{"principal_id": str(uuid4()), "role": "owner"} for _ in range(100)]}
    original = deepcopy(body)
    members = parse_policy(body)
    assert len(members) == 100
    assert body == original


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        True,
        1,
        UUID(PRINCIPAL),
        PRINCIPAL.upper(),
        " " + PRINCIPAL,
        PRINCIPAL + "\n",
        PRINCIPAL.replace("-", ""),
        "{" + PRINCIPAL + "}",
        "urn:uuid:" + PRINCIPAL,
        "a2df4d4c-a807-1b03-a34f-5851d0acbb81",
        "a2df4d4c-a807-4b03-734f-5851d0acbb81",
        "secret-payload",
        "x" * 10000,
    ],
)
def test_idempotency_key_requires_lowercase_canonical_uuid4(value: object) -> None:
    with pytest.raises(DomainError) as caught:
        idempotency_key(cast(str | None, value))
    assert (caught.value.status, caught.value.code, caught.value.pointers) == (
        400,
        "invalid_idempotency_key",
        (),
    )
    assert caught.value.args == ("invalid_idempotency_key",)


def test_valid_idempotency_key_is_uuid_not_generated_or_normalized() -> None:
    assert idempotency_key(PRINCIPAL) == UUID(PRINCIPAL)


@pytest.mark.parametrize("limit", [None, True, False, 0, -1, 101, 1.0, "1", [], {}])
def test_page_limit_is_strict_integer_and_bounded(limit: object) -> None:
    with pytest.raises(DomainError) as caught:
        validate_page(cast(int, limit), None)
    assert (caught.value.status, caught.value.code, caught.value.pointers) == (
        422,
        "validation_failed",
        ("/limit",),
    )


@pytest.mark.parametrize("q", [True, 1, 1.0, [], {}, "", "x" * 101, "a\x00b", "\ud800", "\udfff"])
def test_query_rejects_nontext_bounds_and_non_scalar_strings(q: object) -> None:
    with pytest.raises(DomainError) as caught:
        validate_page(50, cast(str | None, q))
    assert (caught.value.status, caught.value.code, caught.value.pointers) == (
        422,
        "validation_failed",
        ("/q",),
    )


@pytest.mark.parametrize("limit", [1, 50, 100])
@pytest.mark.parametrize("q", [None, "x", "x" * 100, " ", "%_\\", "Żółć 東京", "😀", "e\u0301"])
def test_query_is_literal_and_not_trimmed_or_normalized(limit: int, q: str | None) -> None:
    assert validate_page(limit, q) is None


def test_structural_examples_match_canonical_openapi() -> None:
    schemas = json.loads(
        (ROOT / "specs/0001-project-object-version/contracts/openapi.json").read_text(
            encoding="utf-8"
        )
    )["components"]["schemas"]
    project_validator = Draft202012Validator(
        schemas["ProjectCreate"], format_checker=FormatChecker()
    )
    policy_validator = Draft202012Validator(
        schemas["AccessPolicyWrite"], format_checker=FormatChecker()
    )
    project_validator.validate(VALID_PROJECT)
    parse_project_create(VALID_PROJECT)
    for identifier in [PRINCIPAL, PRINCIPAL.upper(), "00000000-0000-7000-8000-000000000001"]:
        body = {"members": [{"principal_id": identifier, "role": "owner"}]}
        policy_validator.validate(body)
        parse_policy(body)
    assert not policy_validator.is_valid({"members": []})
