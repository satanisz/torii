"""SPEC-0001 B2a1 canonical credentials and record-bound Fernet envelopes."""

import base64
import hashlib
import json
import re
import secrets
from typing import Literal, TypeGuard

from cryptography.fernet import Fernet, InvalidToken

from torii_api.domain.errors import DomainError

Purpose = Literal["verifier", "csrf", "refresh"]
_PURPOSES = frozenset({"verifier", "csrf", "refresh"})
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_RECORD_ID = re.compile(r"[0-9a-f]{64}")
_ENVELOPE_KEYS = frozenset({"v", "purpose", "record_id", "value"})
_MAX_VALUE_BYTES = 16 * 1024
# JSON escapes each ASCII control as six bytes. The fixed fields fit in 256.
_MAX_ENVELOPE_BYTES = 6 * _MAX_VALUE_BYTES + 256
_MAX_CIPHERTEXT_BYTES = 256 * 1024


class SecretDecodeError(DomainError):
    """Only corrupt/unreadable stored ciphertext; safe to distinguish on revoke."""

    def __init__(self) -> None:
        super().__init__(503, "secret_unavailable")


def new_token() -> str:
    """Return a new independent 256-bit opaque credential; never a fallback."""
    try:
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    except OSError:
        pass
    # Raise outside the handler: even __context__ must not retain secret inputs.
    raise DomainError(503, "secret_unavailable")


def token_hash(value: str) -> str:
    """Hash canonical ASCII text, including the representation used for PKCE S256."""
    if type(value) is str and _TOKEN.fullmatch(value):
        raw = base64.urlsafe_b64decode(value + "=")
        canonical = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        if len(raw) == 32 and canonical == value:
            return hashlib.sha256(value.encode("ascii")).hexdigest()
    raise DomainError(401, "unauthorized")


def _valid_context(purpose: object, record_id: object) -> bool:
    return (
        type(purpose) is str
        and purpose in _PURPOSES
        and type(record_id) is str
        and _RECORD_ID.fullmatch(record_id) is not None
    )


def _valid_value(value: object) -> TypeGuard[str]:
    if type(value) is not str or not 1 <= len(value) <= _MAX_VALUE_BYTES:
        return False
    try:
        return 1 <= len(value.encode("utf-8")) <= _MAX_VALUE_BYTES
    except UnicodeEncodeError:
        return False


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid envelope")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("invalid envelope")


class SecretCodec:
    """Current-key encryption; record expiry is checked by the database adapter."""

    __slots__ = ("_fernet",)

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes:
            raise DomainError(503, "secret_unavailable")
        try:
            self._fernet = Fernet(key)
            return
        except (TypeError, ValueError):
            pass
        raise DomainError(503, "secret_unavailable")

    def __repr__(self) -> str:
        return "SecretCodec(<redacted>)"

    def _decrypt(self, ciphertext: bytes) -> bytes:
        try:
            return self._fernet.decrypt(ciphertext)
        except InvalidToken:
            failure: DomainError = SecretDecodeError()
        except (TypeError, ValueError, OSError):
            failure = DomainError(503, "secret_unavailable")
        # Operational failures must not be suppressible as corrupt refresh on revoke.
        raise failure

    def seal(self, purpose: Purpose, record_id: str, value: str) -> bytes:
        if not _valid_context(purpose, record_id) or not _valid_value(value):
            raise DomainError(503, "secret_unavailable")
        try:
            envelope = json.dumps(
                {"v": 1, "purpose": purpose, "record_id": record_id, "value": value},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            return self._fernet.encrypt(envelope)
        except (TypeError, ValueError, OSError):
            pass
        raise DomainError(503, "secret_unavailable")

    def open(self, purpose: Purpose, record_id: str, ciphertext: bytes) -> str:
        if not _valid_context(purpose, record_id):
            raise DomainError(503, "secret_unavailable")
        if type(ciphertext) is not bytes or not 1 <= len(ciphertext) <= _MAX_CIPHERTEXT_BYTES:
            raise SecretDecodeError()
        plaintext = self._decrypt(ciphertext)
        try:
            if len(plaintext) > _MAX_ENVELOPE_BYTES:
                raise ValueError("invalid envelope")
            envelope: object = json.loads(
                plaintext.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            if (
                type(envelope) is not dict
                or envelope.keys() != _ENVELOPE_KEYS
                or type(envelope["v"]) is not int
                or envelope["v"] != 1
                or envelope["purpose"] != purpose
                or envelope["record_id"] != record_id
            ):
                raise ValueError("invalid envelope")
            value = envelope["value"]
            if not _valid_value(value):
                raise ValueError("invalid envelope")
            return value
        except (TypeError, ValueError, RecursionError):
            pass
        raise SecretDecodeError()
