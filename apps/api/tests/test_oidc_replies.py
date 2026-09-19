"""SPEC-0001 B2a4a A4a-03/04/05: untrusted replies, not transport/auth acceptance."""

import ast
import asyncio
import json
import traceback
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import cast

import pytest

from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity
from torii_api.security import oidc_replies
from torii_api.security.oidc_replies import TokenReply, validate_revocation_response

MARKER = "SYNTHETIC_PRIVATE_TOKEN_MARKER"
VALID = {"access_token": MARKER + "-access", "id_token": MARKER + "-id", "token_type": "Bearer"}


class StatusSubclass(int):
    pass


class BytesSubclass(bytes):
    pass


def body(**changes: object) -> bytes:
    return json.dumps(VALID | changes).encode()


def assert_safe(error: DomainError, status: int = 503) -> None:
    assert (error.status, error.code, error.pointers) == (
        status,
        "unauthorized" if status == 401 else "identity_unavailable",
        (),
    )
    assert error.__context__ is error.__cause__ is None
    assert MARKER not in repr(error) and MARKER not in str(error)
    assert MARKER not in "".join(traceback.format_exception(error))


@pytest.mark.parametrize("token_type", ["Bearer", "bearer", "BEARER", "bEaReR"])
@pytest.mark.parametrize("refresh", [None, "!", "~", MARKER + "-refresh"])
def test_reply_is_explicitly_untrusted_and_hides_all_fields(
    token_type: str, refresh: str | None
) -> None:
    data = body(token_type=token_type, **({} if refresh is None else {"refresh_token": refresh}))
    result = TokenReply.from_response(200, data)
    assert (result.access_token, result.id_token, result.refresh_token) == (
        VALID["access_token"],
        VALID["id_token"],
        refresh,
    )
    assert not isinstance(result, Identity)
    assert repr(result) == str(result) == "TokenReply()"
    assert {field.name for field in fields(result)} == {"access_token", "id_token", "refresh_token"}
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.access_token = "changed"
    with pytest.raises(TypeError):
        TokenReply()


def test_opaque_values_do_not_claim_compact_jwt_validation() -> None:
    result = TokenReply.from_response(200, body(access_token="!", id_token="~"))
    assert (result.access_token, result.id_token) == ("!", "~")


def test_all_three_tokens_accept_exact_maximum_without_truncation() -> None:
    tokens = {
        field: prefix * 16384
        for field, prefix in [("access_token", "a"), ("id_token", "b"), ("refresh_token", "c")]
    }
    result = TokenReply.from_response(200, body(**tokens))
    assert result.access_token == tokens["access_token"]
    assert result.id_token == tokens["id_token"]
    assert result.refresh_token == tokens["refresh_token"]


@pytest.mark.parametrize("field", ["access_token", "id_token", "refresh_token"])
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        [],
        {},
        "",
        "a" * 16385,
        " a",
        "a ",
        "a b",
        "a\t",
        "a\n",
        "a\x00",
        "a\x7f",
        "a\x80",
        "ą",
        "😀",
        "\ud800",
    ],
    ids=[
        "null",
        "bool",
        "int",
        "list",
        "dict",
        "empty",
        "oversized",
        "prefix-space",
        "suffix-space",
        "inner-space",
        "tab",
        "newline",
        "nul",
        "del",
        "c1",
        "unicode",
        "emoji",
        "surrogate",
    ],
)
def test_token_fields_reject_wrong_types_and_nonprintable_values(field: str, value: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(200, body(**{field: value}))
    assert_safe(caught.value)


@pytest.mark.parametrize("field", ["access_token", "id_token", "token_type"])
def test_required_fields_cannot_be_missing(field: str) -> None:
    value = VALID.copy()
    del value[field]
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(200, json.dumps(value).encode())
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "token_type", [None, True, 1, [], "", " Bearer", "Bearer ", "Basic", "bearer\n"]
)
def test_token_type_is_exact_untrimmed_string(token_type: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(200, body(token_type=token_type))
    assert_safe(caught.value)


@pytest.mark.parametrize("error", [None, True, "", "invalid_grant", "invalid_client", {}, []])
def test_any_error_member_in_200_invalidates_otherwise_valid_reply(error: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(200, body(error=error))
    assert_safe(caught.value)


@pytest.mark.parametrize("field", ["expires_in", "refresh_expires_in"])
@pytest.mark.parametrize("value", [0, 1, 2**53 - 1])
def test_optional_expiry_accepts_exact_safe_integer_boundaries(field: str, value: int) -> None:
    assert (
        TokenReply.from_response(200, body(**{field: value})).access_token == VALID["access_token"]
    )


@pytest.mark.parametrize("field", ["expires_in", "refresh_expires_in"])
@pytest.mark.parametrize("value", [None, True, False, -1, 2**53, 1.0, "1", [], {}])
def test_optional_expiry_rejects_coercion_and_out_of_range(field: str, value: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(200, body(**{field: value}))
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "scope",
    ["", " ", "a b", "~", " " * 1024, "a" * 1024],
    ids=["empty", "space", "scopes", "tilde", "space-limit", "ascii-limit"],
)
def test_scope_accepts_zero_to_1024_printable_ascii_with_spaces(scope: str) -> None:
    result = TokenReply.from_response(200, body(scope=scope))
    assert not hasattr(result, "scope")


@pytest.mark.parametrize(
    "scope",
    [None, True, 1, [], "a" * 1025, "\t", "\n", "\x7f", "ą", "\udfff"],
    ids=["null", "bool", "int", "array", "size", "tab", "newline", "del", "unicode", "surrogate"],
)
def test_scope_rejects_wrong_types_and_nonprintable_values(scope: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(200, body(scope=scope))
    assert_safe(caught.value)


def test_extension_fields_never_become_identity_grants_or_urls() -> None:
    result = TokenReply.from_response(
        200,
        body(
            roles=["admin"],
            claims={"sub": MARKER},
            email=MARKER,
            display_name=MARKER,
            next_url="https://never-fetch.invalid/" + MARKER,
            expires_in=1,
            arbitrary={"nested": [1, 2]},
        ),
    )
    assert not any(
        hasattr(result, field)
        for field in [
            "roles",
            "claims",
            "email",
            "display_name",
            "next_url",
            "expires_in",
            "arbitrary",
        ]
    )


def test_only_exact_invalid_grant_400_maps_to_unauthorized() -> None:
    value = {
        "error": "invalid_grant",
        "error_description": MARKER,
        "error_uri": "https://never-fetch.invalid/" + MARKER,
        "access_token": None,
        "expires_in": "not-a-number",
        "scope": ["admin"],
    }
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(400, json.dumps(value).encode())
    assert_safe(caught.value, 401)


@pytest.mark.parametrize(
    "error",
    [
        None,
        True,
        1,
        [],
        {},
        "invalid_client",
        "server_error",
        "Invalid_grant",
        "invalid_grant ",
        " invalid_grant",
    ],
)
def test_other_400_errors_are_unavailable_without_echo(error: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(
            400, json.dumps({"error": error, "error_description": MARKER}).encode()
        )
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "status",
    [
        None,
        True,
        200.0,
        400.0,
        "200",
        StatusSubclass(200),
        0,
        201,
        204,
        302,
        401,
        403,
        404,
        429,
        500,
        503,
    ],
)
def test_other_or_nonexact_statuses_are_unavailable(status: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(cast(int, status), b'{"error":"invalid_grant"}')
    assert_safe(caught.value)


@pytest.mark.parametrize("status", [200, 400])
@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        "{}",
        bytearray(b"{}"),
        BytesSubclass(b"{}"),
        b"",
        b"[]",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b'{"x":NaN}',
        b'{"x":1e309}',
        b'{"error":"invalid_grant","error":"invalid_grant"}',
        b'{"error":"invalid_grant","nested":{"x":1,"x":2}}',
        b'{"error":"invalid_grant","nested":"\\ud800"}',
        b'{"x":' + b"1" * 129 + b"}",
    ],
    ids=[
        "null",
        "bool",
        "str",
        "bytearray",
        "subclass",
        "empty",
        "array",
        "utf8",
        "bom",
        "nan",
        "float-overflow",
        "duplicate",
        "nested-duplicate",
        "surrogate",
        "number-limit",
    ],
)
def test_every_token_reply_uses_bounded_strict_json(status: int, raw: object) -> None:
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(status, cast(bytes, raw))
    assert_safe(caught.value)


def test_body_node_depth_and_size_limits_apply_to_ignored_extension_fields() -> None:
    exact_size = json.loads(body(padding=""))
    exact_size["padding"] = "a" * (65536 - len(json.dumps(exact_size).encode()))
    raw = json.dumps(exact_size).encode()
    assert len(raw) == 65536
    assert TokenReply.from_response(200, raw).access_token == VALID["access_token"]
    nested: object = 0
    for _ in range(32):
        nested = [nested]
    for invalid_raw in [raw + b" ", body(extra=[None] * 2048), body(extra=nested)]:
        with pytest.raises(DomainError) as caught:
            TokenReply.from_response(200, invalid_raw)
        assert_safe(caught.value)


@pytest.mark.parametrize(
    "data",
    [b"", b"not JSON", b"\x00\xff", b"a" * 65536, b'{"error":"invalid_token"}'],
    ids=["empty", "text", "binary", "limit", "ignored-json"],
)
def test_revocation_200_ignores_bounded_content(data: bytes) -> None:
    assert validate_revocation_response(200, data) is None


@pytest.mark.parametrize(
    "status", [None, True, 200.0, "200", StatusSubclass(200), 201, 204, 400, 401, 503]
)
def test_revocation_requires_exact_integer200(status: object) -> None:
    with pytest.raises(DomainError) as caught:
        validate_revocation_response(cast(int, status), b"")
    assert_safe(caught.value)


@pytest.mark.parametrize(
    "data",
    [None, True, "", bytearray(), BytesSubclass(b""), b"a" * 65537],
    ids=["null", "bool", "str", "bytearray", "subclass", "size"],
)
def test_revocation_requires_exact_bounded_bytes(data: object) -> None:
    with pytest.raises(DomainError) as caught:
        validate_revocation_response(200, cast(bytes, data))
    assert_safe(caught.value)


@pytest.mark.parametrize("failure", [ValueError, TypeError])
def test_parser_fault_never_retains_provider_exception(
    monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    def fail(data: bytes, *, limit: int) -> dict[str, object]:
        raise failure(MARKER)

    monkeypatch.setattr(oidc_replies, "decode_object", fail)
    with pytest.raises(DomainError) as caught:
        TokenReply.from_response(200, body())
    assert_safe(caught.value)


def test_parser_boundary_does_not_swallow_external_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = asyncio.CancelledError()

    def fail(data: bytes, *, limit: int) -> dict[str, object]:
        raise failure

    monkeypatch.setattr(oidc_replies, "decode_object", fail)
    with pytest.raises(asyncio.CancelledError) as caught:
        TokenReply.from_response(200, body())
    assert caught.value is failure


def test_reply_module_has_no_io_crypto_or_identity_verification_imports() -> None:
    tree = ast.parse(Path(oidc_replies.__file__).read_text(encoding="utf-8"))
    names = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    names |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not {name.split(".")[0] for name in names} & {
        "httpx",
        "httpcore",
        "requests",
        "socket",
        "urllib",
        "sqlalchemy",
        "fastapi",
        "jwt",
        "logging",
        "cryptography",
    }
    assert "torii_api.security.oidc_tokens" not in names
    assert "torii_api.security.oidc_transport" not in names
