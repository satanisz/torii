"""SPEC-0001 B2a4a: pure OAuth encoding; no transport or identity proof."""

import base64
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlencode

from torii_api.domain.errors import DomainError
from torii_api.security.oidc_errors import raise_identity_error
from torii_api.security.oidc_transport import RealmEndpoints
from torii_api.security.session_secrets import token_hash


def _credential(value: object, max_chars: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= max_chars
        and all(
            ord(char) > 0x1F and not 0x7F <= ord(char) <= 0x9F and not 0xD800 <= ord(char) <= 0xDFFF
            for char in value
        )
    )


def _opaque(value: object, limit: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= limit
        and all(0x21 <= ord(char) <= 0x7E for char in value)
    )


@dataclass(frozen=True, slots=True)
class OAuthRequest:
    """Secret-bearing data, NOT a validated transport capability.

    Future transports must enforce their configured endpoint even for a manually
    constructed DTO. Explicit field access/asdict are not redaction boundaries.
    """

    url: str = field(repr=False)
    authorization: str = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True, slots=True, init=False)
class OAuthRequests:
    _endpoints: RealmEndpoints = field(repr=False)
    _authorization: str = field(repr=False)

    def __init__(self, endpoints: RealmEndpoints, client_id: str, client_secret: str) -> None:
        if (
            type(endpoints) is not RealmEndpoints
            or not _credential(client_id, 256)
            or not _credential(client_secret, 8192)
        ):
            raise_identity_error()
        if not 32 <= len(client_secret.encode("utf-8")) <= 8192:
            raise_identity_error()
        # RFC6749 2.3.1: encode each credential BEFORE Basic's colon join.
        credentials = (
            quote_plus(client_id, safe="") + ":" + quote_plus(client_secret, safe="")
        ).encode("ascii")
        authorization = "Basic " + base64.b64encode(credentials).decode("ascii")
        object.__setattr__(self, "_endpoints", endpoints)
        object.__setattr__(self, "_authorization", authorization)

    def _request(self, operation: str, pairs: list[tuple[str, str]]) -> OAuthRequest:
        body = urlencode(pairs).encode("ascii")
        if len(body) > 65536:
            raise_identity_error()
        return OAuthRequest(
            self._endpoints.backchannel + "/protocol/openid-connect/" + operation,
            self._authorization,
            body,
        )

    def exchange(self, code: str, verifier: str) -> OAuthRequest:
        if not _opaque(code, 4096):
            raise_identity_error(401)
        try:
            token_hash(verifier)
        except DomainError:
            raise_identity_error()
        # RealmEndpoints already enforces the fixed realm path and HTTPS origin.
        origin = self._endpoints.issuer.split("/identity/realms/", 1)[0]
        return self._request(
            "token",
            [
                ("grant_type", "authorization_code"),
                ("code", code),
                ("redirect_uri", origin + "/auth/callback"),
                ("code_verifier", verifier),
            ],
        )

    def revoke(self, refresh_token: str) -> OAuthRequest:
        if not _opaque(refresh_token, 16384):
            raise_identity_error()
        return self._request(
            "revoke", [("token", refresh_token), ("token_type_hint", "refresh_token")]
        )
