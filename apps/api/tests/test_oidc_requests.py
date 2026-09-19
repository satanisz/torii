"""SPEC-0001 A4a-01/02/05: pure OAuth encoding, no token exchange or I/O."""

import base64
import traceback
from dataclasses import FrozenInstanceError
from urllib.parse import parse_qsl, unquote_plus

import pytest

from torii_api.domain.errors import DomainError
from torii_api.security.oidc_requests import OAuthRequest, OAuthRequests
from torii_api.security.oidc_transport import RealmEndpoints
from torii_api.security.session_secrets import new_token

ISSUER = "https://localhost:19443/identity/realms/synthetic"
BACKCHANNEL = "http://identity:8080/identity/realms/synthetic"
ENDPOINTS = RealmEndpoints(ISSUER, BACKCHANNEL)
MARKER = "synthetic-private-request-marker-123"


def safe_error(status, operation):
    with pytest.raises(DomainError) as caught:
        operation()
    error = caught.value
    assert (error.status, error.code) == (
        status,
        "unauthorized" if status == 401 else "identity_unavailable",
    )
    assert error.__cause__ is error.__context__ is None
    assert MARKER not in "".join(traceback.format_exception(error))


def test_basic_golden_form_encodes_both_sides_before_base64():
    client = OAuthRequests(ENDPOINTS, "client :+%/ż", "x" * 32 + " :+%/ż")
    request = client.exchange(MARKER, new_token())
    basic = base64.b64decode(request.authorization.removeprefix("Basic "), validate=True)
    assert basic == b"client+%3A%2B%25%2F%C5%BC:" + b"x" * 32 + b"+%3A%2B%25%2F%C5%BC"
    assert basic.count(b":") == 1
    assert [unquote_plus(item) for item in basic.decode().split(":")] == [
        "client :+%/ż",
        "x" * 32 + " :+%/ż",
    ]


def test_exact_exchange_fields_and_fixed_targets():
    verifier = new_token()
    client = OAuthRequests(ENDPOINTS, "torii-web", MARKER)
    request = client.exchange("code&grant_type=refresh_token+%#?=", verifier)
    assert type(request) is OAuthRequest
    assert request.url == BACKCHANNEL + "/protocol/openid-connect/token"
    assert type(request.body) is bytes
    assert parse_qsl(request.body.decode(), keep_blank_values=True) == [
        ("grant_type", "authorization_code"),
        ("code", "code&grant_type=refresh_token+%#?="),
        ("redirect_uri", "https://localhost:19443/auth/callback"),
        ("code_verifier", verifier),
    ]
    assert "client_secret" not in request.body.decode()
    assert "client_id" not in request.body.decode()
    assert MARKER not in request.url
    assert MARKER not in repr(client) + str(client) + repr(request) + str(request)
    assert request.authorization not in repr(request)
    assert verifier not in repr(request)
    with pytest.raises(FrozenInstanceError):
        request.body = b"changed"


def test_revoke_is_form_and_does_not_assume_jwt_format():
    client = OAuthRequests(ENDPOINTS, "torii-web", MARKER)
    request = client.revoke("opaque+/=&token_type_hint=access_token")
    assert request.url == BACKCHANNEL + "/protocol/openid-connect/revoke"
    assert parse_qsl(request.body.decode(), keep_blank_values=True) == [
        ("token", "opaque+/=&token_type_hint=access_token"),
        ("token_type_hint", "refresh_token"),
    ]


@pytest.mark.parametrize("public", ["https://localhost", "https://idp.example:443"])
def test_public_origin_is_preserved_without_realm_path(public):
    endpoints = RealmEndpoints(public + "/identity/realms/a", "http://identity/identity/realms/a")
    client = OAuthRequests(endpoints, "client", MARKER)
    request = client.exchange("code", new_token())
    assert dict(parse_qsl(request.body.decode()))["redirect_uri"] == public + "/auth/callback"


@pytest.mark.parametrize(
    "code", [None, True, b"code", "", " ", "a b", "a\n", "\x7f", "é", "x" * 4097]
)
def test_bad_code_has_precedence_over_bad_internal_verifier(code):
    client = OAuthRequests(ENDPOINTS, "client", MARKER)
    safe_error(401, lambda: client.exchange(code, "invalid"))


@pytest.mark.parametrize(
    "verifier", [None, True, "", "a" * 42, "a" * 44, "a" * 43, "=" * 43, "é" * 43]
)
def test_verifier_must_be_canonical_b2a1_value(verifier):
    client = OAuthRequests(ENDPOINTS, "client", MARKER)
    safe_error(503, lambda: client.exchange("code", verifier))


@pytest.mark.parametrize(
    "token", [None, False, b"opaque", "", "a b", "a\t", "\x7f", "é", "x" * 16385]
)
def test_bad_refresh_is_safe_internal_error(token):
    safe_error(503, lambda: OAuthRequests(ENDPOINTS, "client", MARKER).revoke(token))


@pytest.mark.parametrize(
    "client_id", [None, True, b"id", "", "x" * 257, "a\n", "\x7f", "\x80", "\ud800"]
)
def test_bad_client_id_configuration(client_id):
    safe_error(503, lambda: OAuthRequests(ENDPOINTS, client_id, MARKER))


@pytest.mark.parametrize(
    "secret",
    [
        None,
        False,
        b"secret",
        "",
        "x" * 31,
        "x" * 8193,
        "😀" * 2049,
        MARKER + "\n",
        MARKER + "\x7f",
        MARKER + "\x80",
        MARKER + "\udfff",
    ],
)
def test_bad_client_secret_configuration(secret):
    safe_error(503, lambda: OAuthRequests(ENDPOINTS, "client", secret))


@pytest.mark.parametrize("secret", ["x" * 32, "x" * 8192, "😀" * 8, "😀" * 2048])
def test_secret_limit_uses_utf8_bytes_and_preserves_unicode(secret):
    client = OAuthRequests(ENDPOINTS, "😀" * 256, secret)
    request = client.revoke("token")
    encoded = base64.b64decode(request.authorization[6:]).decode("ascii").split(":")
    assert tuple(map(unquote_plus, encoded)) == ("😀" * 256, secret)


@pytest.mark.parametrize("method,value", [("exchange", "&" * 4096), ("revoke", "&" * 16384)])
def test_maximum_escaped_form_is_bounded(method, value):
    client = OAuthRequests(ENDPOINTS, "client", MARKER)
    request = client.exchange(value, new_token()) if method == "exchange" else client.revoke(value)
    assert 0 < len(request.body) <= 65536
    assert (
        dict(parse_qsl(request.body.decode()))["code" if method == "exchange" else "token"] == value
    )


def test_encoder_rejects_non_endpoint_objects_and_is_immutable():
    safe_error(503, lambda: OAuthRequests(None, "client", MARKER))
    client = OAuthRequests(ENDPOINTS, "client", MARKER)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        client.redirect_uri = "https://attacker.invalid/"


def test_encoder_errors_do_not_inherit_caller_exception():
    try:
        raise ValueError(MARKER)
    except ValueError:
        safe_error(503, lambda: OAuthRequests(ENDPOINTS, "client", None))
        safe_error(401, lambda: OAuthRequests(ENDPOINTS, "client", MARKER).exchange("", ""))
