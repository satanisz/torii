"""SPEC-0001 role capabilities; caller must fetch current membership every time."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from torii_api.domain.errors import DomainError


class Role(StrEnum):
    READER = "reader"
    EDITOR = "editor"
    OWNER = "owner"


class Capability(StrEnum):
    READ = "read"
    EDIT = "edit"
    ACCESS = "access"
    AUDIT = "audit"
    ARCHIVE = "archive"


_ALLOWED = {
    Role.READER: frozenset({Capability.READ}),
    Role.EDITOR: frozenset({Capability.READ, Capability.EDIT}),
    Role.OWNER: frozenset(Capability),
}


def authorize(role: Role | None, action: Capability) -> None:
    if role is None:
        raise DomainError(404, "not_found")
    if action not in _ALLOWED[role]:
        raise DomainError(403, "forbidden")


@dataclass(frozen=True)
class Member:
    principal_id: UUID
    role: Role


def validate_members(members: list[Member], active_ids: set[UUID]) -> None:
    """Validate within the same locked transaction used to replace the policy."""
    ids = [member.principal_id for member in members]
    if len(members) > 100 or len(ids) != len(set(ids)):
        raise DomainError(422, "validation_failed", ("/members",))
    if not set(ids).issubset(active_ids):
        raise DomainError(404, "not_found")
    if not any(member.role == Role.OWNER for member in members):
        raise DomainError(409, "last_owner")
