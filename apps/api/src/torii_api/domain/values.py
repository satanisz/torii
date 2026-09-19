"""SPEC-0001 names and conditional update values."""

import re
from typing import Literal
from uuid import UUID

from torii_api.domain.errors import DomainError

_ETAG = re.compile(
    r'"(?:acl|object|draft):[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-'
    r'[89ab][0-9a-f]{3}-[0-9a-f]{12}:[1-9][0-9]*"\Z'
)


def validate_name(value: str) -> str:
    if not 1 <= len(value) <= 120 or value != value.strip() or "\x00" in value:
        raise DomainError(422, "validation_failed", ("/name",))
    return value


def etag(kind: Literal["acl", "object", "draft"], identifier: UUID, revision: int) -> str:
    if identifier.version != 4 or revision < 1:
        raise ValueError("Invalid server ETag state")
    return f'"{kind}:{identifier}:{revision}"'


def check_etag(supplied: str | None, expected: str) -> None:
    if supplied is None:
        raise DomainError(428, "precondition_required")
    if len(supplied) > 128 or not _ETAG.fullmatch(supplied):
        raise DomainError(400, "invalid_etag")
    if supplied != expected:
        raise DomainError(412, "precondition_failed")
