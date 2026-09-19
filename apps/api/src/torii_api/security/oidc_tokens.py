"""SPEC-0001 B2a2 offline RS256 verification; no discovery, DB or HTTP routes."""

import hashlib
import hmac
import math
import re
import time
from collections.abc import Callable
from typing import Literal, cast

from jwt.api_jws import PyJWS
from jwt.exceptions import InvalidTokenError, PyJWTError

from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity, normalize_display_name
from torii_api.security.oidc_keys import (
    SigningKeys,
    decode_object,
    decode_segment,
    valid_kid,
)
from torii_api.security.session_secrets import token_hash

_MAX_DATE = 2**53 - 1
_NONCE_HASH = re.compile(r"[0-9a-f]{64}")


def _parse(token: str) -> tuple[str, bytes, dict[str, object]]:
    # Only bounded syntax here: none of these claims establishes a principal.
    try:
        if type(token) is not str or not 1 <= len(token) <= 16384 or not token.isascii():
            raise ValueError("invalid token")
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid token")
        header = decode_object(decode_segment(parts[0], limit=2048), limit=2048)
        payload = decode_segment(parts[1], limit=12288)
        claims = decode_object(payload, limit=12288)
        decode_segment(parts[2], limit=512)
        if (
            header.keys() != {"alg", "kid", "typ"}
            or header["alg"] != "RS256"
            or header["typ"] != "JWT"
            or not valid_kid(header["kid"])
        ):
            raise ValueError("invalid token")
        return cast(str, header["kid"]), payload, claims
    except ValueError:
        pass
    # No parser exception context, payload or token in errors.
    raise DomainError(401, "unauthorized")


def token_key_id(token: str) -> str:
    """An UNTRUSTED, bounded lookup hint, never proof of signature or identity."""
    return _parse(token)[0]


def _label(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 256
        and not any(
            ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F or 0xD800 <= ord(char) <= 0xDFFF
            for char in value
        )
    )


def _audiences(value: object) -> list[str]:
    values = [value] if type(value) is str else value
    if (
        type(values) is not list
        or not 1 <= len(values) <= 16
        or not all(_label(item) for item in values)
        or len(set(values)) != len(values)
    ):
        raise DomainError(401, "unauthorized")
    return cast(list[str], values)


def _date(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_DATE:
        raise DomainError(401, "unauthorized")
    return value


class TokenVerifier:
    """Server-owned profile and key source; never take keys/config from requests."""

    __slots__ = ("_issuer", "_client", "_audience", "_clock", "_jws")

    def __init__(
        self,
        issuer: str,
        client_id: str,
        audience: str,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (
            type(issuer) is not str
            or not 1 <= len(issuer) <= 2048
            or any(char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF for char in issuer)
            or not _label(client_id)
            or not _label(audience)
            or client_id == audience
            or not callable(clock)
        ):
            raise DomainError(503, "identity_unavailable")
        self._issuer, self._client, self._audience, self._clock = issuer, client_id, audience, clock
        self._jws = PyJWS(
            algorithms=["RS256"],
            options={"verify_signature": True, "enforce_minimum_key_length": True},
        )

    def _signed_claims(self, token: str, keys: SigningKeys) -> dict[str, object]:
        kid, payload, claims = _parse(token)
        if keys.issuer != self._issuer:
            raise DomainError(503, "identity_unavailable")
        key = keys.key_for(kid)
        if key is None:
            raise DomainError(401, "unauthorized")
        try:
            verified = self._jws.decode(
                token,
                key=key,
                algorithms=["RS256"],
                options={"verify_signature": True, "enforce_minimum_key_length": True},
            )
            if type(verified) is not bytes or verified != payload:
                raise ValueError("invalid provider output")
            return claims
        except InvalidTokenError:
            failure = DomainError(401, "unauthorized")
        except (PyJWTError, ValueError, TypeError, OSError):
            failure = DomainError(503, "identity_unavailable")
        raise failure

    def _now(self) -> float:
        try:
            value = self._clock()
            if (
                type(value) not in (int, float)
                or not 0 <= value <= _MAX_DATE
                or not math.isfinite(value)
            ):
                raise ValueError("invalid clock")
            return float(value)
        except Exception:
            # This wraps only the server clock dependency, not credential validation.
            pass
        raise DomainError(503, "identity_unavailable")

    def _identity(
        self, claims: dict[str, object], kind: Literal["Bearer", "ID"], now: float
    ) -> Identity:
        if claims.get("iss") != self._issuer or claims.get("typ") != kind:
            raise DomainError(401, "unauthorized")
        expiry = _date(claims.get("exp"))
        if expiry <= now - 30:
            raise DomainError(401, "unauthorized")
        for field in ("iat", "nbf"):
            if field in claims or (field == "iat" and kind == "ID"):
                value = _date(claims.get(field))
                if value > now + 30 or value >= expiry:
                    raise DomainError(401, "unauthorized")
        audiences = _audiences(claims.get("aud"))
        if (
            (kind == "ID" and audiences != [self._client])
            or (kind == "Bearer" and self._audience not in audiences)
            or ("azp" in claims and claims["azp"] != self._client)
        ):
            raise DomainError(401, "unauthorized")
        return Identity(
            self._issuer,
            cast(str, claims.get("sub")),
            normalize_display_name(claims.get("name"), claims.get("preferred_username")),
        )

    def verify_access(self, token: str, keys: SigningKeys) -> Identity:
        claims = self._signed_claims(token, keys)
        return self._identity(claims, "Bearer", self._now())

    def verify_login(
        self, id_token: str, access_token: str, nonce_hash: str, keys: SigningKeys
    ) -> Identity:
        if type(nonce_hash) is not str or not _NONCE_HASH.fullmatch(nonce_hash):
            raise DomainError(503, "identity_unavailable")
        id_claims = self._signed_claims(id_token, keys)
        access_claims = self._signed_claims(access_token, keys)
        now = self._now()  # One fresh timestamp after BOTH signatures.
        identity = self._identity(id_claims, "ID", now)
        access_identity = self._identity(access_claims, "Bearer", now)
        if identity.subject != access_identity.subject or not hmac.compare_digest(
            token_hash(cast(str, id_claims.get("nonce"))), nonce_hash
        ):
            raise DomainError(401, "unauthorized")
        if "at_hash" in id_claims:
            self._access_hash(id_claims["at_hash"], access_token)
        return identity

    @staticmethod
    def _access_hash(value: object, access_token: str) -> None:
        try:
            actual = decode_segment(cast(str, value), limit=16)
            expected = hashlib.sha256(access_token.encode("ascii")).digest()[:16]
            if not hmac.compare_digest(actual, expected):
                raise ValueError("invalid binding")
            return
        except ValueError:
            pass
        raise DomainError(401, "unauthorized")
