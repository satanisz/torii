"""SPEC-0001 B2a2 AC-02/04: bounded parsing and issuer-bound public RSA keys.

Parsing does not establish key provenance. Callers must supply trusted JWKS;
this module performs no I/O and never accepts key material from a token.
"""

import base64
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Self, cast

from cryptography.hazmat.primitives.asymmetric import rsa

from torii_api.domain.errors import DomainError

_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
_PRIVATE_FIELDS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth", "k"})


def valid_kid(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 128
        and all(0x21 <= ord(char) <= 0x7E for char in value)
    )


def decode_segment(value: str, *, limit: int) -> bytes:
    """Decode only nonempty canonical unpadded base64url within a byte limit."""
    if (
        type(limit) is not int
        or limit < 1
        or type(value) is not str
        or not 1 <= len(value) <= (limit * 4 + 2) // 3
        or len(value) % 4 == 1
        or _BASE64URL.fullmatch(value) is None
    ):
        raise ValueError("invalid encoded segment")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if (
            len(decoded) <= limit
            and base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") == value
        ):
            return decoded
    except (TypeError, ValueError):
        pass
    raise ValueError("invalid encoded segment")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid JSON object")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("invalid JSON object")


def _parse_int(value: str) -> int:
    if len(value) > 128:
        raise ValueError("invalid JSON object")
    return int(value)


def _parse_float(value: str) -> float:
    if len(value) > 128:
        raise ValueError("invalid JSON object")
    return float(value)


def _check_tree(root: dict[str, object]) -> None:
    # Depth belongs to containers only. Scalars/keys count as nodes, not levels.
    pending: list[tuple[object, int]] = [(root, 0)]
    nodes = 0
    while pending:
        value, parent_depth = pending.pop()
        nodes += 1
        if nodes > 2048:
            raise ValueError("invalid JSON object")
        if type(value) is dict or type(value) is list:
            depth = parent_depth + 1
            if depth > 32:
                raise ValueError("invalid JSON object")
            if type(value) is dict:
                for key, child in value.items():
                    pending.extend(((key, depth), (child, depth)))
            else:
                pending.extend((child, depth) for child in value)
        elif type(value) is str:
            if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                raise ValueError("invalid JSON object")
        elif type(value) is float and not math.isfinite(value):
            raise ValueError("invalid JSON object")


def decode_object(data: bytes, *, limit: int) -> dict[str, object]:
    """Strict UTF-8 JSON object; errors never contain input or chained context."""
    if (
        type(limit) is not int
        or limit < 1
        or type(data) is not bytes
        or not 1 <= len(data) <= limit
    ):
        raise ValueError("invalid JSON object")
    try:
        value: object = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=_parse_int,
            parse_float=_parse_float,
        )
        if type(value) is not dict:
            raise ValueError("invalid JSON object")
        result = cast(dict[str, object], value)
        _check_tree(result)
        return result
    except (TypeError, ValueError, RecursionError):
        pass
    raise ValueError("invalid JSON object")


def _rsa_key(value: dict[str, object]) -> rsa.RSAPublicKey:
    if "key_ops" in value and value["key_ops"] != ["verify"]:
        raise ValueError("invalid public key")
    modulus = decode_segment(cast(str, value.get("n")), limit=512)
    exponent = decode_segment(cast(str, value.get("e")), limit=3)
    if modulus[0] == 0 or exponent[0] == 0:
        raise ValueError("invalid public key")
    n = int.from_bytes(modulus, "big")
    e = int.from_bytes(exponent, "big")
    if not 2048 <= n.bit_length() <= 4096 or n % 2 != 1 or e != 65537:
        raise ValueError("invalid public key")
    return rsa.RSAPublicNumbers(e, n).public_key()


def _key_map(data: bytes) -> dict[str, rsa.RSAPublicKey]:
    document = decode_object(data, limit=65536)
    entries = document.get("keys")
    if document.keys() != {"keys"} or type(entries) is not list or not 1 <= len(entries) <= 32:
        raise ValueError("invalid public key set")
    seen: set[str] = set()
    keys: dict[str, rsa.RSAPublicKey] = {}
    for entry in entries:
        if type(entry) is not dict or _PRIVATE_FIELDS.intersection(entry):
            raise ValueError("invalid public key set")
        kid = entry.get("kid")
        kty = entry.get("kty")
        if not valid_kid(kid) or type(kty) is not str or not kty:
            raise ValueError("invalid public key set")
        kid = cast(str, kid)
        if kid in seen:
            raise ValueError("invalid public key set")
        seen.add(kid)
        for field_name in ("use", "alg"):
            if field_name in entry and (
                type(entry[field_name]) is not str or not entry[field_name]
            ):
                raise ValueError("invalid public key set")
        if kty != "RSA" or entry.get("use", "sig") != "sig" or entry.get("alg", "RS256") != "RS256":
            continue
        keys[kid] = _rsa_key(entry)
    if not keys:
        raise ValueError("invalid public key set")
    return keys


@dataclass(frozen=True, slots=True, init=False)
class SigningKeys:
    """Immutable full snapshot, not a cache or evidence of issuer provenance."""

    issuer: str = field(repr=False)
    _keys: Mapping[str, rsa.RSAPublicKey] = field(repr=False)

    def __init__(self) -> None:
        raise TypeError("use SigningKeys.from_jwks")

    @classmethod
    def from_jwks(cls, data: bytes, *, issuer: str) -> Self:
        if (
            type(issuer) is not str
            or not 1 <= len(issuer) <= 2048
            or any(char == "\x00" or 0xD800 <= ord(char) <= 0xDFFF for char in issuer)
        ):
            raise DomainError(503, "identity_unavailable")
        try:
            keys = _key_map(data)
            instance = object.__new__(cls)
            object.__setattr__(instance, "issuer", issuer)
            object.__setattr__(instance, "_keys", MappingProxyType(keys))
            return instance
        except (TypeError, ValueError, OSError):
            pass
        raise DomainError(503, "identity_unavailable")

    def key_for(self, kid: str) -> rsa.RSAPublicKey | None:
        if not valid_kid(kid):
            return None
        return self._keys.get(kid)
