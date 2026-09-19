"""SPEC-0001 B2a2: signed-token claims and server boundary, not OIDC E2E."""

import ast
import json
import traceback
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.api_jws import PyJWS
from jwt.exceptions import InvalidKeyError, InvalidTokenError, PyJWTError

from torii_api.domain.errors import DomainError
from torii_api.security.oidc_keys import SigningKeys
from torii_api.security.oidc_tokens import TokenVerifier, token_key_id
from torii_api.security.session_secrets import new_token, token_hash

ISSUER = "https://synthetic.example.invalid/identity/realms/test"
CLIENT, AUDIENCE = "torii-web", "torii-api"
MARKER = "synthetic-private-marker"


@pytest.fixture(scope="module")
def material():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())) | {"kid": "key-1"}
    data = json.dumps({"keys": [jwk]}).encode()
    return private, SigningKeys.from_jwks(data, issuer=ISSUER), data


def claims(**changes):
    return dict(iss=ISSUER, sub=MARKER, typ="Bearer", aud=AUDIENCE, exp=1300, iat=1000) | changes


def signed(private, payload):
    # The fixture must sign invalid claim types too, not reject them before the SUT.
    return PyJWS().encode(
        json.dumps(payload).encode(), private, algorithm="RS256", headers={"kid": "key-1"}
    )


def safe_error(status, operation):
    with pytest.raises(DomainError) as caught:
        operation()
    error = caught.value
    assert (error.status, error.code) == (
        status,
        "unauthorized" if status == 401 else "identity_unavailable",
    )
    assert error.__context__ is error.__cause__ is None
    assert MARKER not in "".join(traceback.format_exception(error))
    return error


def test_access_verifies_and_normalizes_without_using_email_or_roles(material):
    private, keys, _ = material
    verifier = TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000)
    token = signed(private, claims(name=" \u202eAlicja\x00 ", roles=["admin"], email=MARKER))
    identity = verifier.verify_access(token, keys)
    assert (identity.issuer, identity.subject, identity.display_name) == (ISSUER, MARKER, "Alicja")
    assert MARKER not in repr(identity)
    assert token_key_id(token) == "key-1"
    assert not hasattr(identity, "roles")


@pytest.mark.parametrize("aud", [AUDIENCE, [AUDIENCE], ["account", AUDIENCE]])
def test_access_audience_membership(material, aud):
    private, keys, _ = material
    assert (
        TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000)
        .verify_access(signed(private, claims(aud=aud)), keys)
        .subject
        == MARKER
    )


@pytest.mark.parametrize("field", ["iss", "sub", "aud", "exp", "typ"])
def test_access_required_claims(material, field):
    private, keys, _ = material
    payload = claims()
    del payload[field]
    safe_error(
        401,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000).verify_access(
            signed(private, payload), keys
        ),
    )


@pytest.mark.parametrize("field", ["exp", "iat", "nbf"])
@pytest.mark.parametrize("value", [None, True, "1000", 1000.0, -1, 2**53])
def test_dates_are_bounded_exact_integers(material, field, value):
    private, keys, _ = material
    safe_error(
        401,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000).verify_access(
            signed(private, claims(**{field: value})), keys
        ),
    )


@pytest.mark.parametrize(
    "changes,allowed",
    [
        ({"exp": 970, "iat": 900}, False),
        ({"exp": 971, "iat": 900}, True),
        ({"nbf": 1030}, True),
        ({"nbf": 1031}, False),
        ({"iat": 1030}, True),
        ({"iat": 1031}, False),
        ({"iat": 1300}, False),
        ({"nbf": 1300}, False),
        ({"exp": 2**53 - 1}, True),
    ],
)
def test_time_boundaries(material, changes, allowed):
    private, keys, _ = material
    verify = TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000)

    def operation():
        return verify.verify_access(signed(private, claims(**changes)), keys)

    if allowed:
        assert operation().subject == MARKER
    else:
        safe_error(401, operation)


def test_access_allows_missing_iat_and_nbf(material):
    private, keys, _ = material
    payload = claims()
    del payload["iat"]
    assert (
        TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000)
        .verify_access(signed(private, payload), keys)
        .display_name
        == "Użytkownik"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": ISSUER.upper()},
        {"iss": [ISSUER]},
        {"sub": " bad"},
        {"sub": 1},
        {"sub": "ą"},
        {"sub": "a" * 256},
        {"azp": "other"},
        {"azp": None},
        {"aud": []},
        {"aud": [AUDIENCE, AUDIENCE]},
        {"aud": [AUDIENCE, None]},
        {"aud": [AUDIENCE] + [str(i) for i in range(16)]},
        {"aud": CLIENT},
        {"aud": [AUDIENCE, "bad\n"]},
        {"aud": [AUDIENCE, "a" * 257]},
        {"typ": "ID"},
        {"typ": "Refresh"},
        {"typ": "bearer"},
    ],
)
def test_claim_semantics_fail_closed(material, changes):
    private, keys, _ = material
    safe_error(
        401,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000).verify_access(
            signed(private, claims(**changes)), keys
        ),
    )


@pytest.mark.parametrize("clock_value", [None, True, "1000", -1, float("nan"), float("inf"), 2**53])
def test_bad_server_clock_is_dependency_failure(material, clock_value):
    private, keys, _ = material
    safe_error(
        503,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: clock_value).verify_access(
            signed(private, claims()), keys
        ),
    )


def test_clock_exception_is_safe(material):
    private, keys, _ = material

    def fail():
        raise RuntimeError(MARKER)

    safe_error(
        503,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=fail).verify_access(
            signed(private, claims()), keys
        ),
    )


@pytest.mark.parametrize(
    "error,status",
    [
        (InvalidTokenError, 401),
        (InvalidKeyError, 503),
        (PyJWTError, 503),
        (ValueError, 503),
        (TypeError, 503),
        (OSError, 503),
    ],
)
def test_signature_provider_errors_are_safe(material, monkeypatch, error, status):
    private, keys, _ = material
    token = signed(private, claims())

    def fail(*args, **kwargs):
        raise error(MARKER)

    monkeypatch.setattr(PyJWS, "decode", fail)
    safe_error(
        status,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000).verify_access(
            token, keys
        ),
    )


def test_wrong_keyset_issuer_is_dependency_failure(material):
    private, _, data = material
    keys = SigningKeys.from_jwks(data, issuer=ISSUER + "other")
    safe_error(
        503,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000).verify_access(
            signed(private, claims()), keys
        ),
    )


@pytest.mark.parametrize("result", [None, b"unexpected"])
def test_unexpected_signature_provider_output_is_dependency_failure(material, monkeypatch, result):
    private, keys, _ = material
    token = signed(private, claims())
    monkeypatch.setattr(PyJWS, "decode", lambda *args, **kwargs: result)
    safe_error(
        503,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000).verify_access(
            token, keys
        ),
    )


def test_correct_azp_and_subject_case_are_preserved(material):
    private, keys, _ = material
    verifier = TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000.5)
    for subject in ("Subject", "subject"):
        result = verifier.verify_access(signed(private, claims(sub=subject, azp=CLIENT)), keys)
        assert result.subject == subject


def test_untrusted_key_hint_does_not_claim_verification(material):
    private, keys, _ = material
    token = signed(private, {"arbitrary": "not valid identity claims"})
    assert token_key_id(token) == "key-1"
    safe_error(
        401,
        lambda: TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: 1000).verify_access(
            token, keys
        ),
    )


@pytest.mark.parametrize(
    "issuer,client,audience",
    [
        ("", CLIENT, AUDIENCE),
        (None, CLIENT, AUDIENCE),
        ("bad\x00", CLIENT, AUDIENCE),
        ("a" * 2049, CLIENT, AUDIENCE),
        (ISSUER, "", AUDIENCE),
        (ISSUER, CLIENT, CLIENT),
        (ISSUER, CLIENT, "a\n"),
    ],
)
def test_bad_configuration_is_safe(issuer, client, audience):
    safe_error(503, lambda: TokenVerifier(issuer, client, audience))


def test_login_uses_one_clock_after_both_signatures(material, monkeypatch):
    private, keys, _ = material
    nonce = new_token()
    access = signed(private, claims())
    identity = signed(private, claims(typ="ID", aud=[CLIENT], nonce=nonce, name=" Login name "))
    calls = []
    original = PyJWS.decode

    def counted(*args, **kwargs):
        calls.append("signature")
        return original(*args, **kwargs)

    def clock():
        calls.append("clock")
        return 1000

    monkeypatch.setattr(PyJWS, "decode", counted)
    result = TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=clock).verify_login(
        identity, access, token_hash(nonce), keys
    )
    assert result.display_name == "Login name"
    assert calls == ["signature", "signature", "clock"]


def test_verifier_modules_do_not_import_network_or_storage():
    directory = Path(__file__).resolve().parents[1] / "src/torii_api/security"
    for name in ("oidc_keys.py", "oidc_tokens.py"):
        modules = set()
        for node in ast.walk(ast.parse((directory / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
                assert "storage" not in (node.module or "")
        assert not modules & {"httpx", "requests", "socket", "urllib", "sqlalchemy", "fastapi"}
