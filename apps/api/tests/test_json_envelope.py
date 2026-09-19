"""SPEC-0001 AC-08/14: strict HTTP JSON envelope rules."""

import pytest

from torii_api.domain.errors import DomainError
from torii_api.http.json import decode_json


@pytest.mark.parametrize(
    "body",
    [
        b'{"a": 1, "a": 2}',
        b'{"x":{"a":1,"a":2}}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"{} {}",
        b"\xff",
        b'{"x":"\\ud800"}',
        b'{"x":"\\udfff"}',
        b"\xef\xbb\xbf{}",
    ],
)
def test_invalid_json_never_silently_coerced(body: bytes) -> None:
    with pytest.raises(DomainError) as err:
        decode_json(body, "application/json")
    assert (err.value.status, err.value.code) == (400, "invalid_json")


def test_depth_and_size_bounds() -> None:
    assert decode_json(b"[" * 32 + b"0" + b"]" * 32, "application/json")
    for body in [b"[" * 33 + b"0" + b"]" * 33, b" " * (256 * 1024 + 1)]:
        with pytest.raises(DomainError) as err:
            decode_json(body, "application/json")
        assert err.value.status == 413


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/json; charset=latin1"])
def test_wrong_content_type(content_type: str | None) -> None:
    with pytest.raises(DomainError) as err:
        decode_json(b"{}", content_type)
    assert err.value.status == 415


def test_valid_unicode_and_json() -> None:
    assert decode_json('{"text":"Żółć"}'.encode(), "application/json; charset=utf-8") == {
        "text": "Żółć"
    }


@pytest.mark.parametrize(
    "number", ["1e400", "-1e400", "1e-9999999999999999999", "0e9999999999999999999"]
)
def test_numeric_overflow_rejected(number: str) -> None:
    with pytest.raises(DomainError) as err:
        decode_json(('{"n":' + number + "}").encode(), "application/json")
    assert err.value.status == 400


@pytest.mark.parametrize(
    "body",
    [
        b'{"n":1.0000000000000001}',
        b'{"n":9007199254740992}',
        b'{"n":1e-400}',
        b'{"name":"\\u0000"}',
        b'{"\\u0000":"value"}',
    ],
)
def test_unsupported_values_rejected_before_rounding_or_persistence(body: bytes) -> None:
    with pytest.raises(DomainError) as err:
        decode_json(body, "application/json")
    assert err.value.status == 422


def test_exact_integer_alternative_notation() -> None:
    assert decode_json(b'{"n":1.0, "m":1e3}', "application/json") == {"n": 1, "m": 1000}
