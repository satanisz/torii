"""SPEC-0002 M-01: upstream regression probes, not new Torii JWT profiles.

Synthetic values only. Torii continues to use its bounded RS256 verifier;
unsigned decode and OKP below deliberately exercise dependency fixes directly.
"""

import json
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed448, ed25519
from jwt.exceptions import DecodeError, InvalidKeyError
from jwt.utils import base64url_encode


def compact(payload: bytes) -> str:
    header = b'{"alg":"RS256","kid":"synthetic-key"}'
    return b".".join((base64url_encode(header), base64url_encode(payload), b"")).decode()


@pytest.mark.parametrize("path", ["unsigned_decode", "jwk_client"])
def test_recursive_payload_raises_decode_error_without_key_fetch(path, monkeypatch):
    # Construct bytes directly: json.dumps would recurse before reaching PyJWT.
    # CPython 3.12's C JSON decoder limit differs from sys.getrecursionlimit().
    # This fixed 8 KiB fixture exceeds it without constructing an in-memory tree.
    depth = 4096
    payload = b'{"nested":' + b"[" * depth + b"0" + b"]" * depth + b"}"
    token = compact(payload)
    client = jwt.PyJWKClient("https://never-connect.invalid/synthetic-jwks")
    fetch = Mock(side_effect=AssertionError("regression test must never perform key fetch"))
    monkeypatch.setattr(client, "fetch_data", fetch)
    with pytest.raises(DecodeError):
        if path == "unsigned_decode":
            jwt.decode(token, options={"verify_signature": False})
        else:
            client.get_signing_key_from_jwt(token)
    fetch.assert_not_called()


def test_ordinary_payload_still_decodes_and_jwk_lookup_uses_only_stub(monkeypatch):
    claims = {"sub": "synthetic-user"}
    token = compact(json.dumps(claims).encode())
    assert jwt.decode(token, options={"verify_signature": False}) == claims
    client = jwt.PyJWKClient("https://never-connect.invalid/synthetic-jwks")
    key = object()
    lookup = Mock(return_value=key)
    fetch = Mock(side_effect=AssertionError("regression test must never perform key fetch"))
    monkeypatch.setattr(client, "get_signing_key", lookup)
    monkeypatch.setattr(client, "fetch_data", fetch)
    assert client.get_signing_key_from_jwt(token) is key
    lookup.assert_called_once_with("synthetic-key")
    fetch.assert_not_called()


def private_jwk(key, curve):
    return {
        "kty": "OKP",
        "crv": curve,
        "x": base64url_encode(
            key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode(),
        "d": base64url_encode(
            key.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
        ).decode(),
    }


@pytest.mark.parametrize(
    "curve,key_type", [("Ed25519", ed25519.Ed25519PrivateKey), ("Ed448", ed448.Ed448PrivateKey)]
)
def test_inconsistent_okp_public_private_components_rejected(curve, key_type):
    first, second = key_type.generate(), key_type.generate()
    inconsistent = private_jwk(first, curve)
    inconsistent["d"] = private_jwk(second, curve)["d"]
    with pytest.raises(InvalidKeyError):
        jwt.PyJWK.from_dict(inconsistent, algorithm="EdDSA")


@pytest.mark.parametrize(
    "curve,key_type", [("Ed25519", ed25519.Ed25519PrivateKey), ("Ed448", ed448.Ed448PrivateKey)]
)
def test_consistent_okp_private_and_public_keys_remain_usable(curve, key_type):
    key = key_type.generate()
    document = private_jwk(key, curve)
    imported_private = jwt.PyJWK.from_dict(document, algorithm="EdDSA").key
    imported_public = jwt.PyJWK.from_dict(
        {k: v for k, v in document.items() if k != "d"}, algorithm="EdDSA"
    ).key
    payload = b"synthetic-dependency-regression-control"
    imported_public.verify(imported_private.sign(payload), payload)
