"""SPEC-0001 B2a1 values: pure invariants, not proof of OIDC/JWT or HTTP auth."""

import base64
import hashlib
import json
import re
import traceback
from dataclasses import FrozenInstanceError
from typing import cast

import pytest
from cryptography.fernet import Fernet

from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity, normalize_display_name
from torii_api.security import session_secrets
from torii_api.security.session_secrets import (
    SecretCodec,
    SecretDecodeError,
    new_token,
    token_hash,
)

# Synthetic test material, never a configured key or user credential.
KEY = base64.urlsafe_b64encode(bytes(range(32)))
OTHER_KEY = base64.urlsafe_b64encode(bytes(reversed(range(32))))
RECORD = "1a" * 32
OTHER_RECORD = "2b" * 32
TOKEN = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")
ISSUER = "https://identity.example.invalid/realms/test"
SECRET = "synthetic-private-marker-ąć😀"


def assert_safe_error(error: DomainError, *, status: int, code: str) -> None:
    assert (error.status, error.code, error.pointers) == (status, code, ())
    assert error.args == (code,)
    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in "".join(traceback.format_exception(error))
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize(
    "name,preferred,expected",
    [
        (" Alicja ", "ignored", "Alicja"),
        (None, "  login  ", "login"),
        (True, "  login  ", "login"),
        (42, "login", "login"),
        (["name"], "login", "login"),
        ({"name": "bad"}, "login", "login"),
        ("", "login", "login"),
        ("\x00\t\ud800\u202e\u200e", "login", "login"),
        ("\u2003\u00a0", "login", "login"),
        (None, None, "Użytkownik"),
        ("", 123, "Użytkownik"),
        ("", "\x00\udfff\u2069", "Użytkownik"),
        ("Żółć 東京 😀", "ignored", "Żółć 東京 😀"),
        ("e\u0301", None, "e\u0301"),
        ("\u200bA\u200dB\u200b", None, "\u200bA\u200dB\u200b"),
        ("A  B", None, "A  B"),
        ("a" * 201, None, "a" * 200),
        ("😀" * 201, None, "😀" * 200),
        ("a" * 199 + " " + "z", None, "a" * 199),
        ("  " + "a" * 200 + "  ", None, "a" * 200),
    ],
)
def test_display_normalization(name: object, preferred: object, expected: str) -> None:
    normalized = normalize_display_name(name, preferred)
    assert normalized == expected
    assert normalize_display_name(normalized, None) == normalized


@pytest.mark.parametrize(
    "codepoint",
    [
        *range(0x20),
        *range(0x7F, 0xA0),
        0xD800,
        0xDBFF,
        0xDC00,
        0xDFFF,
        0x061C,
        0x200E,
        0x200F,
        *range(0x202A, 0x202F),
        *range(0x2066, 0x206A),
    ],
)
def test_display_removes_only_specified_controls(codepoint: int) -> None:
    assert normalize_display_name("A" + chr(codepoint) + "B", None) == "AB"


@pytest.mark.parametrize("subject", ["!", "~", "A" * 255, "Case-Sensitive:42@example.invalid"])
def test_identity_preserves_exact_subject_and_hides_all_fields(subject: str) -> None:
    identity = Identity(ISSUER, subject, "Alicja")
    assert (identity.issuer, identity.subject, identity.display_name) == (ISSUER, subject, "Alicja")
    assert repr(identity) == "Identity()"
    with pytest.raises(FrozenInstanceError):
        identity.subject = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "subject", [None, True, 4, [], "", "a" * 256, " a", "a ", "a\n", "a\x7f", "ą", "\ud800"]
)
def test_identity_rejects_invalid_subject_without_coercion(subject: object) -> None:
    with pytest.raises(DomainError) as caught:
        Identity(ISSUER, cast(str, subject), "Alicja")
    assert_safe_error(caught.value, status=401, code="unauthorized")


@pytest.mark.parametrize("issuer", [None, True, [], "", "a" * 2049, "a\x00b", "a\udfffb"])
def test_identity_rejects_malformed_issuer(issuer: object) -> None:
    with pytest.raises(DomainError) as caught:
        Identity(cast(str, issuer), "subject", "Alicja")
    assert_safe_error(caught.value, status=401, code="unauthorized")


@pytest.mark.parametrize(
    "name", [None, 4, True, "", " a", "a ", "a" * 201, "a\x00b", "a\u202eb", "a\ud800b"]
)
def test_identity_requires_already_normalized_display_name(name: object) -> None:
    with pytest.raises(DomainError) as caught:
        Identity(ISSUER, "subject", cast(str, name))
    assert_safe_error(caught.value, status=401, code="unauthorized")


def test_display_name_does_not_replace_or_normalize_identity() -> None:
    first = Identity(ISSUER, "Subject", normalize_display_name("name", "login"))
    second = Identity(ISSUER, "subject", normalize_display_name("name", "login"))
    assert first != second
    assert Identity("urn:trusted:issuer", "subject", "a").issuer == "urn:trusted:issuer"


def test_token_uses_32_random_bytes_and_unpadded_canonical_base64url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def random_bytes(length: int) -> bytes:
        calls.append(length)
        return bytes(range(length))

    monkeypatch.setattr(session_secrets.secrets, "token_bytes", random_bytes)
    assert new_token() == TOKEN
    assert calls == [32]


def test_independently_generated_tokens_are_canonical_and_distinct() -> None:
    # A smoke assertion, not a statistical claim about the system CSPRNG.
    tokens = [new_token() for _ in range(8)]
    assert len(set(tokens)) == 8
    for value in tokens:
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", value)
        assert token_hash(value) == hashlib.sha256(value.encode("ascii")).hexdigest()


def test_token_hash_uses_ascii_input_and_matches_rfc7636_s256_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = base64.urlsafe_b64encode(bytes.fromhex(token_hash(verifier))).rstrip(b"=")
    assert challenge == b"E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert token_hash(TOKEN) != hashlib.sha256(bytes(range(32))).hexdigest()


def test_random_source_failure_has_no_fallback_or_exception_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(length: int) -> bytes:
        raise OSError(SECRET)

    monkeypatch.setattr(session_secrets.secrets, "token_bytes", fail)
    with pytest.raises(DomainError) as caught:
        new_token()
    assert type(caught.value) is DomainError
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        4,
        b"a" * 43,
        "",
        "a" * 42,
        "a" * 44,
        "a" * 42 + "=",
        "a" * 42 + "+",
        "a" * 42 + "/",
        "a" * 42 + "\n",
        "ą" * 43,
        TOKEN[:-1] + "9",
        TOKEN + "=",
        "a" * 42 + "\ud800",
    ],
)
def test_token_hash_rejects_noncanonical_credentials(value: object) -> None:
    with pytest.raises(DomainError) as caught:
        token_hash(cast(str, value))
    assert_safe_error(caught.value, status=401, code="unauthorized")


@pytest.mark.parametrize("purpose", ["verifier", "csrf", "refresh"])
@pytest.mark.parametrize(
    "value",
    ["a", SECRET, "a" * 16384, "😀" * 4096, "\x00" * 16384],
    ids=["single", "unicode", "ascii-limit", "multibyte-limit", "escaped-control-limit"],
)
def test_codec_round_trip_and_bound_envelope(purpose: str, value: str) -> None:
    codec = SecretCodec(KEY)
    encrypted = codec.seal(purpose, RECORD, value)
    assert type(encrypted) is bytes
    assert codec.open(purpose, RECORD, encrypted) == value
    assert SecretCodec(KEY).open(purpose, RECORD, encrypted) == value
    envelope = json.loads(Fernet(KEY).decrypt(encrypted))
    assert envelope == {"v": 1, "purpose": purpose, "record_id": RECORD, "value": value}
    assert SECRET not in repr(codec)
    assert KEY.decode("ascii") not in repr(codec)


def test_ciphertexts_are_randomized_and_no_plaintext_is_returned() -> None:
    codec = SecretCodec(KEY)
    first = codec.seal("refresh", RECORD, SECRET)
    second = codec.seal("refresh", RECORD, SECRET)
    assert first != second
    assert SECRET.encode("utf-8") not in first


@pytest.mark.parametrize("failure", [ValueError, TypeError, OSError])
def test_seal_provider_failures_are_safe_and_never_decode_failures(
    monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    def fail(self: Fernet, value: bytes) -> bytes:
        raise failure(SECRET)

    codec = SecretCodec(KEY)
    monkeypatch.setattr(Fernet, "encrypt", fail)
    with pytest.raises(DomainError) as caught:
        codec.seal("refresh", RECORD, SECRET)
    assert type(caught.value) is DomainError
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize("failure", [ValueError, TypeError, OSError])
def test_open_provider_failures_are_safe_and_never_decode_failures(
    monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    def fail(self: Fernet, ciphertext: bytes, ttl: int | None = None) -> bytes:
        raise failure(SECRET)

    codec = SecretCodec(KEY)
    encrypted = codec.seal("refresh", RECORD, SECRET)
    monkeypatch.setattr(Fernet, "decrypt", fail)
    with pytest.raises(DomainError) as caught:
        codec.open("refresh", RECORD, encrypted)
    assert type(caught.value) is DomainError
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize("key", [None, True, KEY.decode("ascii"), b"", b"a" * 32, b"a" * 44])
def test_invalid_codec_configuration_is_not_decode_failure(key: object) -> None:
    with pytest.raises(DomainError) as caught:
        SecretCodec(cast(bytes, key))
    assert type(caught.value) is DomainError
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize("purpose", [None, True, 1, "", "other", "CSRF", SECRET])
def test_invalid_purpose_is_not_decode_failure(purpose: object) -> None:
    codec = SecretCodec(KEY)
    for operation in [
        lambda: codec.seal(purpose, RECORD, SECRET),
        lambda: codec.open(purpose, RECORD, b"bad"),
    ]:
        with pytest.raises(DomainError) as caught:
            operation()
        assert type(caught.value) is DomainError
        assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize("record", [None, True, 1, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64])
def test_invalid_record_binding_argument_is_not_decode_failure(record: object) -> None:
    codec = SecretCodec(KEY)
    for operation in [
        lambda: codec.seal("csrf", record, SECRET),
        lambda: codec.open("csrf", record, b"bad"),
    ]:
        with pytest.raises(DomainError) as caught:
            operation()
        assert type(caught.value) is DomainError
        assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize(
    "value",
    [None, True, 1, b"text", "", "a" * 16385, "😀" * 4097, SECRET + "\ud800", SECRET + "\udfff"],
    ids=[
        "null",
        "bool",
        "int",
        "bytes",
        "empty",
        "ascii-limit",
        "multibyte-limit",
        "high-surrogate",
        "low-surrogate",
    ],
)
def test_seal_rejects_bad_value_without_decode_error_or_secret_leak(value: object) -> None:
    with pytest.raises(DomainError) as caught:
        SecretCodec(KEY).seal("refresh", RECORD, value)
    assert type(caught.value) is DomainError
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize(
    "purpose,record,key",
    [("verifier", RECORD, KEY), ("csrf", OTHER_RECORD, KEY), ("csrf", RECORD, OTHER_KEY)],
)
def test_open_rejects_swapped_purpose_record_and_key(purpose: str, record: str, key: bytes) -> None:
    encrypted = SecretCodec(KEY).seal("csrf", RECORD, SECRET)
    with pytest.raises(SecretDecodeError) as caught:
        SecretCodec(key).open(purpose, record, encrypted)
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize(
    "ciphertext",
    [None, True, "text", b"", b"invalid", b"a" * 262145],
    ids=["null", "bool", "str", "empty", "invalid", "size-limit"],
)
def test_open_rejects_corrupt_ciphertext(ciphertext: object) -> None:
    with pytest.raises(SecretDecodeError) as caught:
        SecretCodec(KEY).open("csrf", RECORD, ciphertext)
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


def test_open_rejects_tampering() -> None:
    encrypted = SecretCodec(KEY).seal("csrf", RECORD, SECRET)
    decoded = bytearray(base64.urlsafe_b64decode(encrypted))
    decoded[30] ^= 1
    tampered = base64.urlsafe_b64encode(decoded)
    with pytest.raises(SecretDecodeError) as caught:
        SecretCodec(KEY).open("csrf", RECORD, tampered)
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


def valid_envelope() -> dict[str, object]:
    return {"v": 1, "purpose": "csrf", "record_id": RECORD, "value": SECRET}


@pytest.mark.parametrize("field", ["v", "purpose", "record_id", "value"])
def test_open_requires_all_envelope_fields(field: str) -> None:
    envelope = valid_envelope()
    del envelope[field]
    encrypted = Fernet(KEY).encrypt(json.dumps(envelope).encode())
    with pytest.raises(SecretDecodeError) as caught:
        SecretCodec(KEY).open("csrf", RECORD, encrypted)
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize(
    "replacement",
    [
        {"v": True},
        {"v": 1.0},
        {"v": "1"},
        {"v": 2},
        {"v": None},
        {"purpose": []},
        {"purpose": "refresh"},
        {"record_id": None},
        {"record_id": OTHER_RECORD},
        {"value": None},
        {"value": True},
        {"value": []},
        {"value": {}},
        {"value": ""},
        {"value": "a" * 16385},
        {"value": "😀" * 4097},
        {"value": SECRET + "\ud800"},
        {"extra": SECRET},
    ],
)
def test_open_rejects_invalid_envelope_content(replacement: dict[str, object]) -> None:
    encrypted = Fernet(KEY).encrypt(json.dumps(valid_envelope() | replacement).encode())
    with pytest.raises(SecretDecodeError) as caught:
        SecretCodec(KEY).open("csrf", RECORD, encrypted)
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


@pytest.mark.parametrize(
    "plaintext",
    [
        b"\xff",
        b"not-json",
        b"null",
        b"[]",
        b"true",
        b'"text"',
        b"{}",
        b'{"v":NaN}',
        b'{"v":Infinity}',
        b'{"v":-Infinity}',
        b"[" * 2000 + b"]" * 2000,
        b" " * 100000,
    ],
    ids=[
        "bad-utf8",
        "not-json",
        "null",
        "array",
        "bool",
        "str",
        "missing-fields",
        "nan",
        "infinity",
        "negative-infinity",
        "excess-depth",
        "plaintext-limit",
    ],
)
def test_open_rejects_invalid_serialized_envelope(plaintext: bytes) -> None:
    encrypted = Fernet(KEY).encrypt(plaintext)
    with pytest.raises(SecretDecodeError) as caught:
        SecretCodec(KEY).open("csrf", RECORD, encrypted)
    assert_safe_error(caught.value, status=503, code="secret_unavailable")


def test_open_rejects_duplicate_json_keys() -> None:
    plaintext = json.dumps(valid_envelope())[:-1] + ', "v": 1}'
    encrypted = Fernet(KEY).encrypt(plaintext.encode())
    with pytest.raises(SecretDecodeError) as caught:
        SecretCodec(KEY).open("csrf", RECORD, encrypted)
    assert_safe_error(caught.value, status=503, code="secret_unavailable")
