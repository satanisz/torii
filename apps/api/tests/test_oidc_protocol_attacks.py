"""SPEC-0001 B2a4a A4a-01/02/03/04/05: independent protocol attack vectors.

Only synthetic in-memory messages; no HTTP, IdP, signature validation or login.
"""

import base64
import json
import logging
import socket
import traceback
from dataclasses import FrozenInstanceError, fields
from urllib.parse import parse_qsl, unquote_plus, urlsplit

import httpx
import pytest
import sqlalchemy

from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity
from torii_api.security.oidc_replies import TokenReply, validate_revocation_response
from torii_api.security.oidc_requests import OAuthRequest, OAuthRequests
from torii_api.security.oidc_tokens import token_key_id
from torii_api.security.oidc_transport import RealmEndpoints

ISSUER = "https://protocol.example.invalid:9443/identity/realms/synthetic"
BACKCHANNEL = "http://identity:8080/identity/realms/synthetic"
CALLBACK = "https://protocol.example.invalid:9443/auth/callback"
MARKER = "SYNTHETIC_PROTOCOL_PRIVATE_MARKER"
CLIENT = "cl:ie+nt% /ą"
SECRET = "SYNTHETIC_SECRET_0123456789 :+/% żółć !"
VERIFIER = "A" * 43  # Canonical encoding of 32 zero bytes, not production entropy.
GOLDEN_BASIC = (
    "Basic Y2wlM0FpZSUyQm50JTI1KyUyRiVDNCU4NTpTWU5USEVUSUNfU0VDUkVUXzAxMjM0"
    "NTY3ODkrJTNBJTJCJTJGJTI1KyVDNSVCQyVDMyVCMyVDNSU4MiVDNCU4NyslMjE="
)


def requests():
    return OAuthRequests(RealmEndpoints(ISSUER, BACKCHANNEL), CLIENT, SECRET)


def encoded(value):
    return json.dumps(value, separators=(",", ":")).encode()


def success(**extra):
    return {
        "access_token": "synthetic-access",
        "id_token": "synthetic-id",
        "token_type": "Bearer",
    } | extra


def assert_safe_error(operation, status=503):
    with pytest.raises(DomainError) as caught:
        operation()
    error = caught.value
    assert error.status == status
    assert error.code == ("unauthorized" if status == 401 else "identity_unavailable")
    assert error.__cause__ is None
    assert error.__context__ is None
    surfaces = (str(error), repr(error), "".join(traceback.format_exception(error)))
    for surface in surfaces:
        for secret in (MARKER, SECRET, GOLDEN_BASIC, BACKCHANNEL):
            assert secret not in surface


def test_basic_matches_independent_literal_and_decodes_exactly_once():
    request = requests().exchange("synthetic-code", VERIFIER)
    assert request.authorization == GOLDEN_BASIC
    # This literal is independent of production quote_plus/urlencode helpers.
    credentials = base64.b64decode(request.authorization[6:], validate=True).decode("ascii")
    assert credentials == (
        "cl%3Aie%2Bnt%25+%2F%C4%85:"
        "SYNTHETIC_SECRET_0123456789+%3A%2B%2F%25+%C5%BC%C3%B3%C5%82%C4%87+%21"
    )
    assert credentials.count(":") == 1
    assert tuple(unquote_plus(part) for part in credentials.split(":")) == (CLIENT, SECRET)
    assert requests().revoke("synthetic-refresh").authorization == GOLDEN_BASIC


def test_credential_whitespace_and_unicode_normalization_are_not_silently_changed():
    first = OAuthRequests(RealmEndpoints(ISSUER, BACKCHANNEL), " é ", " " + SECRET + " ")
    second = OAuthRequests(RealmEndpoints(ISSUER, BACKCHANNEL), " e\u0301 ", " " + SECRET + " ")
    first_auth = first.exchange("synthetic-code", VERIFIER).authorization
    second_auth = second.exchange("synthetic-code", VERIFIER).authorization
    assert first_auth != second_auth
    for header, expected_id in ((first_auth, " é "), (second_auth, " e\u0301 ")):
        parts = base64.b64decode(header[6:], validate=True).decode("ascii").split(":")
        assert tuple(unquote_plus(part) for part in parts) == (expected_id, " " + SECRET + " ")


def test_exchange_literal_form_preserves_reserved_chars_without_parameter_injection():
    request = requests().exchange("c:+%/&code=second#fragment?x=1", VERIFIER)
    assert request.body == (
        b"grant_type=authorization_code&code=c%3A%2B%25%2F%26code%3Dsecond%23fragment%3Fx%3D1"
        b"&redirect_uri=https%3A%2F%2Fprotocol.example.invalid%3A9443%2Fauth%2Fcallback"
        b"&code_verifier=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    assert parse_qsl(request.body.decode("ascii"), strict_parsing=True) == [
        ("grant_type", "authorization_code"),
        ("code", "c:+%/&code=second#fragment?x=1"),
        ("redirect_uri", CALLBACK),
        ("code_verifier", VERIFIER),
    ]
    assert request.url == BACKCHANNEL + "/protocol/openid-connect/token"
    assert urlsplit(request.url).query == ""
    assert CLIENT not in request.url and SECRET not in request.url


@pytest.mark.parametrize(
    "injected",
    [
        "&grant_type=client_credentials&client_secret=" + MARKER,
        "&redirect_uri=https://attacker.invalid/" + MARKER + "#fragment",
        "%26code%3D" + MARKER,
        "?code=one;code=two+%2526",
    ],
)
def test_exchange_and_revoke_have_closed_parameter_sets(injected):
    exchange = requests().exchange(injected, VERIFIER)
    revoke = requests().revoke(injected)
    assert parse_qsl(exchange.body.decode("ascii"), keep_blank_values=True) == [
        ("grant_type", "authorization_code"),
        ("code", injected),
        ("redirect_uri", CALLBACK),
        ("code_verifier", VERIFIER),
    ]
    assert parse_qsl(revoke.body.decode("ascii"), keep_blank_values=True) == [
        ("token", injected),
        ("token_type_hint", "refresh_token"),
    ]
    assert revoke.url == BACKCHANNEL + "/protocol/openid-connect/revoke"
    assert exchange.authorization == revoke.authorization == GOLDEN_BASIC


def test_maximally_escaped_refresh_is_bounded_and_roundtrips_without_jwt_parsing():
    opaque = "%" * 16384
    request = requests().revoke(opaque)
    assert len(request.body) < 65536
    assert request.body.startswith(b"token=%25%25%25")
    assert parse_qsl(request.body.decode("ascii")) == [
        ("token", opaque),
        ("token_type_hint", "refresh_token"),
    ]


def test_invalid_code_has_precedence_over_noncanonical_verifier():
    assert_safe_error(lambda: requests().exchange(MARKER + "\r\nX-Injected: yes", "B" * 43), 401)
    assert_safe_error(lambda: requests().exchange(MARKER, "B" * 43))


def test_secret_request_fields_are_frozen_slotted_and_not_displayed():
    builder = requests()
    request = builder.exchange(MARKER, VERIFIER)
    assert isinstance(request, OAuthRequest)
    assert {field.name for field in fields(request)} == {"url", "authorization", "body"}
    assert not hasattr(request, "__dict__")
    for value in (builder, request):
        for rendered in (str(value), repr(value)):
            for hidden in (MARKER, SECRET, GOLDEN_BASIC, CLIENT, ISSUER, BACKCHANNEL, VERIFIER):
                assert hidden not in rendered
    for field_name, value in (("url", "https://attacker.invalid"), ("body", b"changed")):
        with pytest.raises(FrozenInstanceError):
            setattr(request, field_name, value)


def test_unsigned_and_non_jwt_replies_are_explicitly_untrusted_without_projected_grants():
    unsigned = "eyJhbGciOiJub25lIn0.e30."
    reply = TokenReply.from_response(
        200,
        encoded(
            success(
                access_token=unsigned,
                id_token="not-a-jwt",
                realm_access={"roles": ["admin"]},
                can_create_project=True,
                email=MARKER,
                display_name=MARKER,
                issuer="https://attacker.invalid/" + MARKER,
                token_endpoint="https://attacker.invalid/" + MARKER,
            )
        ),
    )
    assert reply.access_token == unsigned
    assert reply.id_token == "not-a-jwt"
    assert reply.refresh_token is None
    assert not isinstance(reply, Identity)
    assert {field.name for field in fields(reply)} == {
        "access_token",
        "id_token",
        "refresh_token",
    }
    assert not hasattr(reply, "__dict__")
    for name in ("claims", "roles", "can_create_project", "email", "issuer", "display_name"):
        assert not hasattr(reply, name)
    # Parsing a token response cannot bypass the already existing verifier boundary.
    assert_safe_error(lambda: token_key_id(reply.access_token), 401)


@pytest.mark.parametrize("body", [b"", b"null", b"[]", b"{}{}", b"\xff", b"\xef\xbb\xbf{}"])
def test_non_objects_and_noncanonical_json_are_not_oauth_success(body):
    assert_safe_error(lambda: TokenReply.from_response(200, body))


@pytest.mark.parametrize(
    "body",
    [
        b'{"access_token":"one","access_token":"two","id_token":"i","token_type":"Bearer"}',
        b'{"access_token":"a","id_token":"i","token_type":"Bearer",'
        b'"ignored":{"roles":[],"roles":["admin"]}}',
        b'{"access_token":"a","id_token":"i","token_type":"Bearer","ignored":1e400}',
        b'{"access_token":"a","id_token":"i","token_type":"Bearer","ignored":"\\ud800"}',
    ],
)
def test_even_ignored_extensions_must_pass_strict_json_before_projection(body):
    assert_safe_error(lambda: TokenReply.from_response(200, body))


@pytest.mark.parametrize("error", [None, False, 0, "", "invalid_grant"])
def test_200_error_presence_cannot_be_hidden_by_valid_token_fields(error):
    body = encoded(success(error=error, error_description=MARKER))
    assert_safe_error(lambda: TokenReply.from_response(200, body))


def test_duplicate_error_cannot_choose_between_unauthorized_and_provider_failure():
    for first, second in (("invalid_grant", "invalid_client"), ("invalid_client", "invalid_grant")):
        body = ('{"error":"' + first + '","error":"' + second + '"}').encode()
        assert_safe_error(lambda body=body: TokenReply.from_response(400, body))


def test_invalid_grant_classification_does_not_apply_success_field_rules():
    body = encoded(
        {
            "error": "invalid_grant",
            "access_token": None,
            "token_type": False,
            "expires_in": "not-a-duration",
            "scope": {"not": "a string"},
            "error_description": {"opaque": MARKER},
            "error_uri": "https://attacker.invalid/" + MARKER,
        }
    )
    assert_safe_error(lambda: TokenReply.from_response(400, body), 401)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, "invalid_grant"),
        (503, "invalid_grant"),
        (400, "Invalid_grant"),
        (400, "invalid_client"),
    ],
)
def test_only_exact_status_and_error_pair_is_unauthorized(status, error):
    body = encoded({"error": error, "error_uri": BACKCHANNEL, "error_description": MARKER})
    assert_safe_error(lambda: TokenReply.from_response(status, body))


def test_token_reply_keeps_secrets_out_of_repr_and_cannot_be_mutated():
    reply = TokenReply.from_response(
        200, encoded(success(access_token=MARKER, id_token=MARKER, refresh_token=MARKER))
    )
    assert MARKER not in repr(reply) and MARKER not in str(reply)
    with pytest.raises(FrozenInstanceError):
        reply.access_token = "changed"
    with pytest.raises(TypeError):
        TokenReply(access_token=MARKER, id_token=MARKER, refresh_token=None)


@pytest.mark.parametrize("body", [b"", b"not JSON", b"\xff\x00", b'{"error":"invalid_token"}'])
def test_revocation_200_ignores_body_and_does_not_use_exchange_parser(body):
    assert validate_revocation_response(200, body) is None
    assert_safe_error(lambda: TokenReply.from_response(200, body))


def test_revocation_can_ignore_maximum_body_but_not_exceed_its_bound():
    assert validate_revocation_response(200, b"x" * 65536) is None
    assert_safe_error(lambda: validate_revocation_response(200, b"x" * 65537))


def test_protocol_operations_do_not_create_clients_open_sockets_or_log(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("external effect")
        raise AssertionError("Protocol values must not perform external effects")

    for name in ("create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)
    monkeypatch.setattr(logging.Logger, "_log", forbidden)
    builder = requests()
    assert builder.exchange(MARKER, VERIFIER).body
    assert builder.revoke(MARKER).body
    reply = TokenReply.from_response(200, encoded(success(refresh_token=MARKER)))
    assert reply.refresh_token == MARKER
    assert validate_revocation_response(200, b"not JSON") is None
    assert_safe_error(lambda: TokenReply.from_response(400, encoded({"error": MARKER})))
    assert_safe_error(lambda: builder.exchange("bad code", VERIFIER), 401)
    assert calls == []
