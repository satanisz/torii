"""SPEC-0001 B2a4a A4a-03/04/05: bounded, explicitly untrusted OAuth replies.

No transport, signature checking, Identity or grants. The caller must verify
both returned login tokens and their flow bindings before creating a session.
"""

from dataclasses import dataclass, field
from typing import Self, TypeGuard

from torii_api.security.oidc_errors import raise_identity_error
from torii_api.security.oidc_keys import decode_object


def _opaque_token(value: object) -> TypeGuard[str]:
    return (
        type(value) is str
        and 1 <= len(value) <= 16384
        and all(0x21 <= ord(char) <= 0x7E for char in value)
    )


def _success_fields(value: dict[str, object]) -> tuple[str, str, str | None]:
    access, identity, token_type = (
        value.get("access_token"),
        value.get("id_token"),
        value.get("token_type"),
    )
    if (
        "error" in value
        or not _opaque_token(access)
        or not _opaque_token(identity)
        or type(token_type) is not str
        or token_type.lower() != "bearer"
    ):
        raise ValueError("invalid token response")
    refresh: str | None = None
    if "refresh_token" in value:
        candidate = value["refresh_token"]
        if not _opaque_token(candidate):
            raise ValueError("invalid token response")
        refresh = candidate
    for field_name in ("expires_in", "refresh_expires_in"):
        if field_name in value:
            expiry = value[field_name]
            if type(expiry) is not int or not 0 <= expiry <= 2**53 - 1:
                raise ValueError("invalid token response")
    if "scope" in value:
        scope = value["scope"]
        if (
            type(scope) is not str
            or len(scope) > 1024
            or any(not 0x20 <= ord(char) <= 0x7E for char in scope)
        ):
            raise ValueError("invalid token response")
    return access, identity, refresh


@dataclass(frozen=True, slots=True, init=False)
class TokenReply:
    """Untrusted token strings, never a verified identity or successful login."""

    access_token: str = field(repr=False)
    id_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)

    def __init__(self) -> None:
        raise TypeError("use TokenReply.from_response")

    @classmethod
    def from_response(cls, status: int, body: bytes) -> Self:
        if type(status) is not int:
            raise_identity_error()
        error_status = 503
        try:
            value = decode_object(body, limit=65536)
            if status == 400 and value.get("error") == "invalid_grant":
                error_status = 401
            elif status == 200:
                access, identity, refresh = _success_fields(value)
                instance = object.__new__(cls)
                object.__setattr__(instance, "access_token", access)
                object.__setattr__(instance, "id_token", identity)
                object.__setattr__(instance, "refresh_token", refresh)
                return instance
        except (ValueError, TypeError):
            pass
        raise_identity_error(error_status)


def validate_revocation_response(status: int, body: bytes) -> None:
    """Validate only the bounded acknowledgement, not SSO or access-token revocation."""
    if type(status) is not int or status != 200 or type(body) is not bytes or len(body) > 65536:
        raise_identity_error()
