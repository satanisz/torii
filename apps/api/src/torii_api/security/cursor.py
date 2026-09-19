"""Signed pagination context, never a substitute for fresh authorization."""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import cast

import rfc8785

from torii_api.domain.errors import DomainError


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(decoded) != value:
        raise ValueError("Noncanonical base64")
    return decoded


class CursorSigner:
    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("Cursor key must be at least 32 bytes")
        self._key = key

    def issue(self, context: dict[str, str], marker: list[str], *, now: datetime) -> str:
        issued = int(now.timestamp())
        payload = rfc8785.dumps(
            {"v": 1, "context": context, "marker": marker, "iat": issued, "exp": issued + 900}
        )
        signature = hmac.digest(self._key, payload, hashlib.sha256)
        token = f"{_encode(payload)}.{_encode(signature)}"
        if len(token) > 2048:
            raise ValueError("Cursor context too large")
        return token

    def verify(self, token: str, context: dict[str, str], *, now: datetime) -> list[str]:
        try:
            if len(token) > 2048:
                raise ValueError("Length")
            encoded, signature = token.split(".")
            payload = _decode(encoded)
            if not hmac.compare_digest(
                _decode(signature), hmac.digest(self._key, payload, "sha256")
            ):
                raise ValueError("Signature")
            data = json.loads(payload)
            timestamp = int(now.timestamp())
            if (
                not isinstance(data, dict)
                or data.get("v") != 1
                or data.get("context") != context
                or type(data.get("iat")) is not int
                or type(data.get("exp")) is not int
                or data["exp"] - data["iat"] != 900
                or not data["iat"] <= timestamp < data["exp"]
                or not isinstance(data.get("marker"), list)
                or len(data["marker"]) != 2
                or not all(isinstance(value, str) for value in data["marker"])
            ):
                raise ValueError("Binding or expiry")
            return cast(list[str], data["marker"])
        except (ValueError, TypeError, UnicodeError, KeyError) as exc:
            raise DomainError(400, "invalid_cursor") from exc
