"""SPEC-0001 B2a2 AC-02/04: offline strict parsing and trusted-input JWKS values."""

import base64
import json
import traceback
from dataclasses import FrozenInstanceError
from typing import cast

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from torii_api.domain.errors import DomainError
from torii_api.security import oidc_keys
from torii_api.security.oidc_keys import SigningKeys, decode_object, decode_segment, valid_kid

ISSUER = "https://idp.example.invalid/realms/test"
MARKER = "SYNTHETIC_PRIVATE_ERROR_MARKER"


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def uint(value: int) -> str:
    return encoded(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def document(keys: list[object]) -> bytes:
    return json.dumps({"keys": keys}, separators=(",", ":")).encode()


def assert_safe(error: Exception) -> None:
    assert MARKER not in str(error)
    assert MARKER not in repr(error)
    assert MARKER not in "".join(traceback.format_exception(error))
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.fixture(scope="module")
def public_numbers() -> rsa.RSAPublicNumbers:
    # Generated in memory only; no persisted PEM, JWT or key fixture.
    return (
        rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_numbers()
    )


@pytest.fixture
def jwk(public_numbers: rsa.RSAPublicNumbers) -> dict[str, object]:
    return {
        "kid": "test-key",
        "kty": "RSA",
        "n": uint(public_numbers.n),
        "e": uint(public_numbers.e),
    }


@pytest.mark.parametrize(
    "value", [None, True, 1, [], b"kid", "", "a" * 129, " a", "a ", "a\n", "a\x7f", "ą", "\ud800"]
)
def test_kid_rejects_wrong_types_whitespace_controls_and_non_ascii(value: object) -> None:
    assert valid_kid(value) is False


@pytest.mark.parametrize("value", ["!", "~", "a" * 128, "key:/id?!", "Case"])
def test_kid_accepts_exact_printable_ascii(value: str) -> None:
    assert valid_kid(value) is True


@pytest.mark.parametrize(
    "raw",
    [b"a", b"ab", b"abc", bytes(range(256)), b"\x00", b"\xff" * 512],
    ids=["one", "two", "three", "all-octets", "zero", "limit512"],
)
def test_segment_round_trip_and_exact_decoded_bound(raw: bytes) -> None:
    assert decode_segment(encoded(raw), limit=len(raw)) == raw
    with pytest.raises(ValueError) as caught:
        decode_segment(encoded(raw), limit=len(raw) - 1)
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        123,
        b"YQ",
        "",
        "A",
        "YQ=",
        "YQ==",
        "YR",
        "YWJ",
        "YQ\n",
        " YQ",
        "+w",
        "/w",
        "ą",
        "\ud800",
        "a" * 100,
    ],
    ids=[
        "null",
        "bool",
        "int",
        "bytes",
        "empty",
        "mod4one",
        "padding1",
        "padding2",
        "padbits1",
        "padbits2",
        "newline",
        "space",
        "plus",
        "slash",
        "unicode",
        "surrogate",
        "size",
    ],
)
def test_segment_rejects_noncanonical_encoding(value: object) -> None:
    with pytest.raises(ValueError) as caught:
        decode_segment(cast(str, value), limit=8)
    assert_safe(caught.value)


@pytest.mark.parametrize("limit", [None, True, 1.0, "4", 0, -1])
def test_parser_limits_require_positive_exact_int(limit: object) -> None:
    for operation in [
        lambda: decode_object(b"{}", limit=limit),
        lambda: decode_segment("YQ", limit=limit),
    ]:
        with pytest.raises(ValueError) as caught:
            operation()
        assert_safe(caught.value)


def test_json_preserves_values_without_unicode_normalization() -> None:
    value = {
        "emoji": "😀",
        "decomposed": "e\u0301",
        "ints": [0, -42, 9007199254740992],
        "finite": 1.25,
        "bool": True,
        "null": None,
        "nested": {"x": []},
        "control": "\x00",
    }
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    assert decode_object(raw, limit=len(raw)) == value
    with pytest.raises(ValueError):
        decode_object(raw, limit=len(raw) - 1)


@pytest.mark.parametrize(
    "prefix,suffix,number_type",
    [("1", "", int), ("-1", "", int), ("1.", "e+1", float), ("-1.", "e-1", float)],
)
def test_json_numeric_literal_limit_includes_sign_fraction_and_exponent(
    prefix: str, suffix: str, number_type: type[int] | type[float]
) -> None:
    for length in (128, 129):
        literal = prefix + "0" * (length - len(prefix) - len(suffix)) + suffix
        raw = ('{"number":' + literal + "}").encode()
        assert len(literal) == length
        if length == 128:
            assert type(decode_object(raw, limit=2048)["number"]) is number_type
        else:
            with pytest.raises(ValueError) as caught:
                decode_object(raw, limit=2048)
            assert_safe(caught.value)


def test_numeric_literal_with_small_length_still_rejects_float_overflow() -> None:
    with pytest.raises(ValueError) as caught:
        decode_object(b'{"number":1e309}', limit=2048)
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        "{}",
        bytearray(b"{}"),
        b"",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"{} trailing",
        b"{}{}",
        b"[]",
        b"null",
        b"true",
        b"1",
        b'"str"',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":-Infinity}',
        b'{"a":1e9999}',
        b'{"a":-1e9999}',
        b'{"a":"\\ud800"}',
        b'{"\\udfff":1}',
        b'{"a":{"b":"\\udfff"}}',
        b'{"a":1,"a":2}',
        b'{"a":{"b":1,"b":2}}',
        b'{"a":[{"b":1,"b":2}]}',
        b'{"a":1,"\\u0061":2}',
    ],
    ids=[
        "null",
        "bool",
        "str",
        "mutable",
        "empty",
        "utf8",
        "bom",
        "trailing",
        "two-roots",
        "array",
        "null-root",
        "bool-root",
        "int-root",
        "str-root",
        "nan",
        "inf",
        "neg-inf",
        "overflow",
        "neg-overflow",
        "high-surrogate",
        "key-surrogate",
        "nested-surrogate",
        "duplicate",
        "nested-duplicate",
        "array-duplicate",
        "escaped-duplicate",
    ],
)
def test_json_rejects_invalid_or_ambiguous_input(raw: object) -> None:
    with pytest.raises(ValueError) as caught:
        decode_object(cast(bytes, raw), limit=65536)
    assert_safe(caught.value)


def nested_document(containers: int, leaf: object) -> bytes:
    value = leaf
    for _ in range(containers - 1):
        value = [value]
    return json.dumps({"root": value}).encode()


def test_json_depth_counts_containers_not_scalars_or_keys() -> None:
    raw = nested_document(32, "scalar-at-depth32")
    assert decode_object(raw, limit=len(raw))
    for raw in [nested_document(33, 0), b'{"a":' + b"[" * 2000 + b"]" * 2000 + b"}"]:
        with pytest.raises(ValueError) as caught:
            decode_object(raw, limit=65536)
        assert_safe(caught.value)


def test_json_node_limit_counts_each_container_key_and_scalar_once() -> None:
    # root + its key + array + 2045 scalars = 2048 exactly.
    raw = json.dumps({"items": [None] * 2045}).encode()
    assert len(decode_object(raw, limit=65536)["items"]) == 2045
    with pytest.raises(ValueError):
        decode_object(json.dumps({"items": [None] * 2046}).encode(), limit=65536)
    # root + 1022 key/value pairs + tail key + array + scalar = 2048.
    value: dict[str, object] = {str(i): 0 for i in range(1022)}
    value["tail"] = [None]
    assert decode_object(json.dumps(value).encode(), limit=65536) == value
    value["tail"] = [None, None]
    with pytest.raises(ValueError):
        decode_object(json.dumps(value).encode(), limit=65536)


def test_parsers_never_retain_original_payload_in_exception() -> None:
    for operation in [
        lambda: decode_object((MARKER + "{").encode(), limit=65536),
        lambda: decode_segment(MARKER + "=", limit=65536),
    ]:
        with pytest.raises(ValueError) as caught:
            operation()
        assert_safe(caught.value)


def test_jwks_materializes_matching_public_key(
    jwk: dict[str, object], public_numbers: rsa.RSAPublicNumbers
) -> None:
    keyset = SigningKeys.from_jwks(document([jwk]), issuer=ISSUER)
    assert keyset.issuer == ISSUER
    key = keyset.key_for("test-key")
    assert isinstance(key, rsa.RSAPublicKey)
    assert key.public_numbers() == public_numbers
    assert keyset.key_for("Test-Key") is None
    assert keyset.key_for("missing") is None
    assert keyset.key_for(cast(str, None)) is None
    assert str(jwk["n"]) not in repr(keyset)
    assert "test-key" not in repr(keyset)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        keyset.issuer = "other"


def test_jwks_replacement_has_no_old_key_and_copies_input(jwk: dict[str, object]) -> None:
    first = SigningKeys.from_jwks(document([jwk]), issuer=ISSUER)
    jwk["kid"] = "replacement"
    second = SigningKeys.from_jwks(document([jwk]), issuer=ISSUER)
    assert first.key_for("replacement") is None
    assert second.key_for("test-key") is None
    assert first.key_for("test-key") is not None
    assert second.key_for("replacement") is not None


def test_keyset_cannot_be_uninitialized_or_mutated(jwk: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        SigningKeys()
    keyset = SigningKeys.from_jwks(document([jwk]), issuer=ISSUER)
    with pytest.raises(TypeError):
        keyset._keys["new"] = keyset.key_for("test-key")
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        keyset._keys = {}


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"use": "sig"},
        {"alg": "RS256"},
        {"key_ops": ["verify"]},
        {"x5c": ["ignored"], "x5u": "https://never-fetch.invalid", "other": 1},
    ],
)
def test_selected_rsa_metadata_rules(jwk: dict[str, object], metadata: dict[str, object]) -> None:
    assert SigningKeys.from_jwks(document([jwk | metadata]), issuer=ISSUER).key_for("test-key")


@pytest.mark.parametrize(
    "ignored",
    [
        {"kid": "ignored", "kty": "EC"},
        {"kid": "ignored", "kty": "RSA", "use": "enc", "key_ops": ["encrypt"]},
        {"kid": "ignored", "kty": "RSA", "alg": "RS512"},
        {"kid": "ignored", "kty": "oct", "use": "sig"},
    ],
)
def test_other_key_types_and_purposes_are_not_fallbacks(
    jwk: dict[str, object], ignored: dict[str, object]
) -> None:
    keyset = SigningKeys.from_jwks(document([jwk, ignored]), issuer=ISSUER)
    assert keyset.key_for("ignored") is None
    with pytest.raises(DomainError):
        SigningKeys.from_jwks(document([ignored]), issuer=ISSUER)


@pytest.mark.parametrize("field", ["d", "p", "q", "dp", "dq", "qi", "oth", "k"])
@pytest.mark.parametrize("kty,use", [("RSA", "sig"), ("RSA", "enc"), ("EC", "enc")])
def test_private_fields_fail_even_in_otherwise_ignored_key(
    jwk: dict[str, object], field: str, kty: str, use: str
) -> None:
    other = {"kid": "other", "kty": kty, "use": use, field: MARKER}
    with pytest.raises(DomainError) as caught:
        SigningKeys.from_jwks(document([jwk, other]), issuer=ISSUER)
    assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
    assert_safe(caught.value)


@pytest.mark.parametrize("field", ["use", "alg"])
@pytest.mark.parametrize("value", [None, True, 4, [], {}, ""])
def test_optional_fields_are_strict_before_filtering(
    jwk: dict[str, object], field: str, value: object
) -> None:
    other = {"kid": "ignored", "kty": "EC", field: value}
    with pytest.raises(DomainError) as caught:
        SigningKeys.from_jwks(document([jwk, other]), issuer=ISSUER)
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "replacement",
    [
        {"kid": None},
        {"kid": ""},
        {"kid": "has space"},
        {"kty": ""},
        {"kty": None},
        {"kty": True},
        {"key_ops": []},
        {"key_ops": ["sign"]},
        {"key_ops": ["verify", "verify"]},
        {"key_ops": ["verify", "encrypt"]},
        {"key_ops": "verify"},
        {"key_ops": None},
        {"n": ""},
        {"n": None},
        {"n": "AA"},
        {"n": uint(2**2047)},
        {"n": uint(2**2046 + 1)},
        {"n": uint(2**4096 + 1)},
        {"e": ""},
        {"e": "Aw"},
        {"e": "AAEAAQ"},
        {"e": "AQAC"},
        {"e": "AQAB="},
        {"e": "AQAB\n"},
    ],
)
def test_selected_key_invalid_values_fail_whole_set(
    jwk: dict[str, object], replacement: dict[str, object]
) -> None:
    with pytest.raises(DomainError) as caught:
        SigningKeys.from_jwks(document([jwk | replacement]), issuer=ISSUER)
    assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
    assert_safe(caught.value)


@pytest.mark.parametrize("field", ["kid", "kty", "n", "e"])
def test_required_key_fields(jwk: dict[str, object], field: str) -> None:
    del jwk[field]
    with pytest.raises(DomainError):
        SigningKeys.from_jwks(document([jwk]), issuer=ISSUER)


def test_leading_zero_modulus_rejected(jwk: dict[str, object]) -> None:
    original = cast(str, jwk["n"])
    jwk["n"] = encoded(b"\x00" + base64.urlsafe_b64decode(original + "=="))
    with pytest.raises(DomainError):
        SigningKeys.from_jwks(document([jwk]), issuer=ISSUER)


@pytest.mark.parametrize("other", [{"kty": "EC"}, {"kty": "RSA", "use": "enc"}, {"kty": "RSA"}])
def test_duplicate_kid_fails_across_types_and_purposes(
    jwk: dict[str, object], other: dict[str, object]
) -> None:
    with pytest.raises(DomainError):
        SigningKeys.from_jwks(document([jwk, jwk | other]), issuer=ISSUER)


@pytest.mark.parametrize(
    "data",
    [
        b"{}",
        b'{"keys":[]}',
        b'{"keys":null}',
        b'{"keys":{}}',
        b'{"keys":[null]}',
        b'{"keys":[true]}',
        b'{"keys":[[]]}',
        b'{"keys":[],"other":1}',
        b'{"keys":[],"keys":[]}',
        b" " * 65537,
    ],
    ids=[
        "missing",
        "empty",
        "null",
        "object",
        "null-key",
        "bool-key",
        "array-key",
        "extra-field",
        "duplicate",
        "oversized",
    ],
)
def test_jwks_requires_bounded_exact_document(data: bytes) -> None:
    with pytest.raises(DomainError) as caught:
        SigningKeys.from_jwks(data, issuer=ISSUER)
    assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
    assert_safe(caught.value)


def test_jwks_accepts_32_entries_but_not_33(jwk: dict[str, object]) -> None:
    ignored = [{"kid": f"skip-{i}", "kty": "EC"} for i in range(32)]
    assert SigningKeys.from_jwks(document([jwk, *ignored[:31]]), issuer=ISSUER).key_for("test-key")
    with pytest.raises(DomainError):
        SigningKeys.from_jwks(document([jwk, *ignored]), issuer=ISSUER)


def test_jwks_exact_byte_limit_and_atomic_selected_key_failure(jwk: dict[str, object]) -> None:
    jwk["metadata"] = ""
    remaining = 65536 - len(document([jwk]))
    jwk["metadata"] = "a" * remaining
    raw = document([jwk])
    assert len(raw) == 65536
    assert SigningKeys.from_jwks(raw, issuer=ISSUER).key_for("test-key")
    with pytest.raises(DomainError):
        SigningKeys.from_jwks(raw + b" ", issuer=ISSUER)
    del jwk["metadata"]
    bad_selected = jwk | {"kid": "bad-selected", "n": "AA"}
    with pytest.raises(DomainError):
        SigningKeys.from_jwks(document([jwk, bad_selected]), issuer=ISSUER)


def test_jwks_accepts_4096_bit_library_key() -> None:
    numbers = (
        rsa.generate_private_key(public_exponent=65537, key_size=4096).public_key().public_numbers()
    )
    key = {"kid": "large", "kty": "RSA", "n": uint(numbers.n), "e": uint(numbers.e)}
    parsed = SigningKeys.from_jwks(document([key]), issuer=ISSUER).key_for("large")
    assert parsed is not None and parsed.key_size == 4096


@pytest.mark.parametrize("issuer", [None, True, "", "a" * 2049, "a\x00b", "a\ud800b"])
def test_jwks_issuer_configuration_strict(jwk: dict[str, object], issuer: object) -> None:
    with pytest.raises(DomainError) as caught:
        SigningKeys.from_jwks(document([jwk]), issuer=cast(str, issuer))
    assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
    assert_safe(caught.value)


@pytest.mark.parametrize("failure", [ValueError, TypeError, OSError])
def test_key_provider_faults_are_safe(
    jwk: dict[str, object], monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    def fail(e: int, n: int) -> rsa.RSAPublicNumbers:
        raise failure(MARKER)

    monkeypatch.setattr(oidc_keys.rsa, "RSAPublicNumbers", fail)
    with pytest.raises(DomainError) as caught:
        SigningKeys.from_jwks(document([jwk]), issuer=ISSUER)
    assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
    assert_safe(caught.value)
