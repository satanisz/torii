"""SPEC-0001 B1 strict input rules; no authorization or transport adapters.

Call after current authorization. Owner/activity/duplicate membership checks
belong to validate_members inside the same transaction as the mutation.
"""

import re
from typing import NoReturn, cast
from uuid import UUID

from torii_api.domain.errors import DomainError
from torii_api.domain.policy import Member, Role
from torii_api.domain.values import validate_name

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_UUID4_KEY = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_ROLES = frozenset(role.value for role in Role)


def _invalid(pointer: str) -> NoReturn:
    raise DomainError(422, "validation_failed", (pointer,))


def _object(value: object, fields: tuple[str, ...], pointer: str) -> dict[str, object]:
    if type(value) is not dict:
        _invalid(pointer)
    for field in fields:
        if field not in value:
            _invalid(f"{pointer}/{field}")
    if any(key not in fields for key in value):
        # Never reflect an arbitrary field name, which may contain secrets.
        _invalid(pointer)
    return cast(dict[str, object], value)


def _text(value: object, *, pointer: str, minimum: int, maximum: int) -> str:
    if type(value) is not str:
        _invalid(pointer)
    if not minimum <= len(value) <= maximum:
        _invalid(pointer)
    if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        _invalid(pointer)
    return value


def parse_project_create(body: object) -> tuple[str, str]:
    """Strict ProjectCreate shape; preserve valid Unicode and whitespace in description."""
    value = _object(body, ("name", "description"), "")
    name = _text(value["name"], pointer="/name", minimum=1, maximum=120)
    description = _text(value["description"], pointer="/description", minimum=0, maximum=4000)
    return validate_name(name), description


def parse_policy(body: object) -> list[Member]:
    """Parse AccessPolicyWrite; empty violates schema before last-owner semantics."""
    value = _object(body, ("members",), "")
    rows = value["members"]
    if type(rows) is not list or not 1 <= len(rows) <= 100:
        _invalid("/members")
    members: list[Member] = []
    for index, row in enumerate(rows):
        pointer = f"/members/{index}"
        member = _object(row, ("principal_id", "role"), pointer)
        principal_id = member["principal_id"]
        if type(principal_id) is not str or not _UUID.fullmatch(principal_id):
            _invalid(f"{pointer}/principal_id")
        role = member["role"]
        if type(role) is not str or role not in _ROLES:
            _invalid(f"{pointer}/role")
        members.append(Member(UUID(principal_id), Role(role)))
    return members


def idempotency_key(value: str | None) -> UUID:
    """Require the canonical lowercase UUIDv4 header without coercion or generation."""
    if type(value) is not str or not _UUID4_KEY.fullmatch(value):
        raise DomainError(400, "invalid_idempotency_key")
    return UUID(value)


def validate_page(limit: int, q: str | None) -> None:
    """Check bounds only: q is a literal substring, never trimmed or SQL-escaped here."""
    if type(limit) is not int or not 1 <= limit <= 100:
        _invalid("/limit")
    if q is not None:
        _text(q, pointer="/q", minimum=1, maximum=100)
