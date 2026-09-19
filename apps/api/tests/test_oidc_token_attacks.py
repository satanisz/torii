"""SPEC-0001 B2a2 AC01-04: real RSA, adversarial compact/JSON and login binding.

Keys and tokens are generated only in memory. No fixture material is written
to disk, and these tests do not contact or authenticate to any identity service.
"""

import base64
import hashlib
import hmac
import json
import traceback

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from torii_api.domain.errors import DomainError
from torii_api.domain.identity import Identity
from torii_api.security.oidc_keys import SigningKeys
from torii_api.security.oidc_tokens import TokenVerifier, token_key_id
from torii_api.security.session_secrets import new_token, token_hash

ISSUER = "https://synthetic-oidc.invalid/realms/attacks"
CLIENT, AUDIENCE, KID = "synthetic-client", "synthetic-api", "synthetic-key"
NOW = 1_800_000_000
MARKER = "SYNTHETIC_CONFIDENTIAL_TOKEN_MARKER"


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def header(**changes):
    return {"alg": "RS256", "typ": "JWT", "kid": KID, **changes}


def access_claims(**changes):
    return {
        "iss": ISSUER,
        "sub": "synthetic-subject",
        "aud": AUDIENCE,
        "exp": NOW + 300,
        "iat": NOW,
        "typ": "Bearer",
        "azp": CLIENT,
        "name": "Synthetic person",
        "preferred_username": "synthetic-username",
        **changes,
    }


def signed(key, claims, protected=None):
    payload = claims if isinstance(claims, bytes) else json_bytes(claims)
    protected = header() if protected is None else protected
    raw_header = protected if isinstance(protected, bytes) else json_bytes(protected)
    unsigned = encoded(raw_header) + "." + encoded(payload)
    signature = key.sign(unsigned.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return unsigned + "." + encoded(signature)


def public_jwk(private):
    numbers = private.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": encoded(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        "e": encoded(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
    }


@pytest.fixture(scope="module")
def material():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    keys = SigningKeys.from_jwks(json_bytes({"keys": [public_jwk(private)]}), issuer=ISSUER)
    return private, other, keys


@pytest.fixture
def verifier():
    return TokenVerifier(ISSUER, CLIENT, AUDIENCE, clock=lambda: NOW)


def rejected(call, status=401):
    with pytest.raises(DomainError) as caught:
        call()
    error = caught.value
    assert error.status == status
    assert error.code == ("unauthorized" if status == 401 else "identity_unavailable")
    assert error.__context__ is None and error.__cause__ is None
    assert MARKER not in "".join(traceback.format_exception(error))
    return error


def login_tokens(private, *, access_changes=None, id_changes=None):
    nonce = new_token()
    access = signed(private, access_claims(**(access_changes or {})))
    claims = {
        "iss": ISSUER,
        "sub": "synthetic-subject",
        "aud": CLIENT,
        "exp": NOW + 300,
        "iat": NOW,
        "typ": "ID",
        "azp": CLIENT,
        "nonce": nonce,
        "at_hash": encoded(hashlib.sha256(access.encode("ascii")).digest()[:16]),
        "name": "  ID\u202e name\n  ",
        "preferred_username": "ID username",
        **(id_changes or {}),
    }
    return signed(private, claims), access, token_hash(nonce), claims


def noncanonical_pad_bits(value):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    assert len(value) % 4 in (2, 3)
    return value[:-1] + alphabet[alphabet.index(value[-1]) + 1]


def test_public_verifier_contract_exists():
    assert callable(SigningKeys.from_jwks)
    assert callable(TokenVerifier.verify_access)
    assert callable(TokenVerifier.verify_login)
    assert callable(token_key_id)


def test_real_rsa_access_ignores_claimed_roles_and_has_no_grants(material, verifier):
    private, _, keys = material
    claims = access_claims(
        name=MARKER,
        email="admin@example.invalid",
        scope="admin project.create",
        realm_access={"roles": ["admin"]},
        roles=["owner"],
        groups=["enterprise-admins"],
        can_create_project=True,
        principal_id="attacker-chosen",
        org_id="attacker-chosen",
        aud=[AUDIENCE, "account"],
    )
    token = signed(private, claims)
    identity = verifier.verify_access(token, keys)
    assert type(identity) is Identity
    assert identity.subject == "synthetic-subject"
    assert identity.display_name == MARKER
    assert not hasattr(identity, "can_create_project") and not hasattr(identity, "roles")
    assert MARKER not in repr(identity) and token not in repr(identity)
    assert token_key_id(token) == KID


@pytest.mark.parametrize("attack", ["payload", "signature", "wrong_key", "same_kid_replacement"])
def test_real_signature_tampering_and_wrong_key_are_rejected(material, verifier, attack):
    private, other, keys = material
    token = signed(private, access_claims())
    parts = token.split(".")
    if attack == "payload":
        parts[1] = encoded(json_bytes(access_claims(sub=MARKER)))
        token = ".".join(parts)
    elif attack == "signature":
        signature = bytearray(base64.urlsafe_b64decode(parts[2] + "=="))
        signature[0] ^= 1
        parts[2] = encoded(signature)
        token = ".".join(parts)
    elif attack == "wrong_key":
        token = signed(other, access_claims())
    else:
        keys = SigningKeys.from_jwks(json_bytes({"keys": [public_jwk(other)]}), issuer=ISSUER)
    # A syntactically valid kid hint must never be treated as successful auth.
    assert token_key_id(token) == KID
    rejected(lambda: verifier.verify_access(token, keys))


@pytest.mark.parametrize(
    "attack", ["none", "hs256_public_key", "unknown_kid", "id_as_access", "refresh"]
)
def test_algorithm_and_token_kind_confusion_are_rejected(material, verifier, attack):
    private, _, keys = material
    if attack == "none":
        token = (
            encoded(json_bytes(header(alg="none")))
            + "."
            + encoded(json_bytes(access_claims()))
            + "."
        )
    elif attack == "hs256_public_key":
        unsigned = (
            encoded(json_bytes(header(alg="HS256"))) + "." + encoded(json_bytes(access_claims()))
        )
        public_bytes = private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        token = (
            unsigned
            + "."
            + encoded(hmac.new(public_bytes, unsigned.encode(), hashlib.sha256).digest())
        )
    elif attack == "unknown_kid":
        token = signed(private, access_claims(), header(kid="unknown"))
    else:
        # Correct API audience cannot turn an ID/refresh token into an access token.
        token = signed(private, access_claims(typ="ID" if attack == "id_as_access" else "Refresh"))
    rejected(lambda: verifier.verify_access(token, keys))


@pytest.mark.parametrize(
    "change",
    [
        {"crit": []},
        {"jku": "https://attacker.invalid/jwks"},
        {"jwk": {}},
        {"x5u": "https://attacker.invalid/cert"},
        {"x5c": []},
        {"b64": True},
        {"zip": "DEF"},
        {"cty": "JWT"},
        {"unknown": MARKER},
        {"alg": "none"},
        {"alg": "HS256"},
        {"alg": "rs256"},
        {"alg": 256},
        {"typ": "Bearer"},
        {"typ": "at+jwt"},
        {"typ": None},
        {"kid": ""},
        {"kid": "with space"},
        {"kid": 1},
        {"kid": "k" * 129},
        {"kid": "\u00e9"},
    ],
)
def test_closed_header_rejects_extensions_and_wrong_types(material, verifier, change):
    private, _, keys = material
    token = signed(private, access_claims(), header(**change))
    rejected(lambda: token_key_id(token))
    rejected(lambda: verifier.verify_access(token, keys))


@pytest.mark.parametrize("field", ["alg", "typ", "kid"])
def test_header_requires_all_three_fields(material, verifier, field):
    private, _, keys = material
    protected = header()
    del protected[field]
    token = signed(private, access_claims(), protected)
    rejected(lambda: token_key_id(token))
    rejected(lambda: verifier.verify_access(token, keys))


@pytest.mark.parametrize(
    "protected",
    [
        b'{"alg":"RS256","alg":"RS256","typ":"JWT","kid":"synthetic-key"}',
        b'{"alg":"RS256","typ":"JWT","kid":"synthetic-key","kid":"synthetic-key"}',
        b"[]",
        b"null",
        b'\xef\xbb\xbf{"alg":"RS256","typ":"JWT","kid":"synthetic-key"}',
    ],
)
def test_raw_header_json_is_strict_before_using_kid(material, verifier, protected):
    private, _, keys = material
    token = signed(private, access_claims(), protected)
    rejected(lambda: token_key_id(token))
    rejected(lambda: verifier.verify_access(token, keys))


@pytest.mark.parametrize(
    "attack",
    [
        "duplicate",
        "nested_duplicate",
        "nan",
        "infinity",
        "overflow",
        "surrogate",
        "bad_utf8",
        "bom",
        "array",
        "null",
        "trailing",
    ],
)
def test_signed_payload_json_ambiguity_is_rejected(material, verifier, attack):
    private, _, keys = material
    base = json_bytes(access_claims(name=MARKER))
    additions = {
        "duplicate": b',"sub":"second-subject"}',
        "nested_duplicate": b',"extra":{"x":1,"x":2}}',
        "nan": b',"extra":NaN}',
        "infinity": b',"extra":Infinity}',
        "overflow": b',"extra":1e309}',
        "surrogate": b',"extra":"\\ud800"}',
        "bad_utf8": b',"extra":"\xff"}',
    }
    if attack in additions:
        payload = base[:-1] + additions[attack]
    elif attack == "bom":
        payload = b"\xef\xbb\xbf" + base
    elif attack in {"array", "null"}:
        payload = b"[]" if attack == "array" else b"null"
    else:
        payload = base + b" false"
    token = signed(private, payload)
    rejected(lambda: token_key_id(token))
    rejected(lambda: verifier.verify_access(token, keys))


@pytest.mark.parametrize("segment", [0, 1, 2])
def test_noncanonical_pad_bits_are_rejected_even_when_decoded_bytes_match(
    material, verifier, segment
):
    private, _, keys = material
    protected, payload = json_bytes(header()), json_bytes(access_claims())
    if len(protected) % 3 == 0:
        protected += b" "
    if len(payload) % 3 == 0:
        payload += b" "
    token = signed(private, payload, protected)
    parts = token.split(".")
    original = parts[segment]
    parts[segment] = noncanonical_pad_bits(original)
    assert base64.urlsafe_b64decode(original + "==") == base64.urlsafe_b64decode(
        parts[segment] + "=="
    )
    malformed = ".".join(parts)
    rejected(lambda: token_key_id(malformed))
    rejected(lambda: verifier.verify_access(malformed, keys))


@pytest.mark.parametrize(
    "mutation",
    ["bytes", "unicode", "padded", "two_parts", "five_parts", "empty", "bad_char", "whitespace"],
)
def test_compact_serialization_requires_exact_ascii_three_nonempty_segments(
    material, verifier, mutation
):
    private, _, keys = material
    token = signed(private, access_claims())
    parts = token.split(".")
    mutations = {
        "bytes": token.encode(),
        "unicode": token + "\u00e9",
        "padded": token + "=",
        "two_parts": ".".join(parts[:2]),
        "five_parts": token + ".a.b",
        "empty": parts[0] + ".." + parts[2],
        "bad_char": token + "!",
        "whitespace": " " + token,
    }
    malformed = mutations[mutation]
    rejected(lambda: token_key_id(malformed))
    rejected(lambda: verifier.verify_access(malformed, keys))


def test_header_and_signature_size_limits_apply_to_untrusted_hint(material, verifier):
    private, _, keys = material
    protected = json_bytes(header())
    at_limit = signed(private, access_claims(), protected.ljust(2048, b" "))
    assert token_key_id(at_limit) == KID
    assert verifier.verify_access(at_limit, keys).subject == "synthetic-subject"
    rejected(lambda: token_key_id(signed(private, access_claims(), protected.ljust(2049, b" "))))
    parts = at_limit.split(".")
    assert token_key_id(".".join([*parts[:2], encoded(b"x" * 512)])) == KID
    rejected(lambda: token_key_id(".".join([*parts[:2], encoded(b"x" * 513)])))
    payload = json_bytes(access_claims()).ljust(12289, b" ")
    rejected(lambda: token_key_id(signed(private, payload)))
    rejected(lambda: token_key_id("x" * 16385))


def test_payload_container_depth_and_total_node_exact_boundaries(material, verifier):
    private, _, keys = material
    nested = 0
    for _ in range(31):
        nested = [nested]
    valid = signed(private, access_claims(extra=nested))
    assert verifier.verify_access(valid, keys).subject == "synthetic-subject"
    rejected(lambda: verifier.verify_access(signed(private, access_claims(extra=[nested])), keys))
    # Root1 +9 original keys/values18 + extra key1/list1 +2027 scalar items =2048.
    valid = signed(private, access_claims(extra=[0] * 2027))
    assert verifier.verify_access(valid, keys).subject == "synthetic-subject"
    rejected(lambda: verifier.verify_access(signed(private, access_claims(extra=[0] * 2028)), keys))


def test_verified_login_binds_real_tokens_and_chooses_id_display_name(material, verifier):
    private, _, keys = material
    id_token, access, nonce_hash, claims = login_tokens(private)
    identity = verifier.verify_login(id_token, access, nonce_hash, keys)
    assert type(identity) is Identity and identity.display_name == "ID name"
    assert identity.subject == "synthetic-subject" and identity.issuer == ISSUER
    del claims["at_hash"]
    without_hash = signed(private, claims)
    assert verifier.verify_login(without_hash, access, nonce_hash, keys) == identity
    # Correct ID token without at_hash still requires a valid access signature.
    wrong_access = signed(material[1], access_claims())
    rejected(lambda: verifier.verify_login(without_hash, wrong_access, nonce_hash, keys))


@pytest.mark.parametrize(
    "attack", ["missing_iat", "extra_audience", "foreign_azp", "foreign_issuer", "expired"]
)
def test_login_id_specific_claim_rules_are_not_replaced_by_valid_access(material, verifier, attack):
    private, _, keys = material
    _, access, nonce_hash, claims = login_tokens(private)
    if attack == "missing_iat":
        claims.pop("iat")
    elif attack == "extra_audience":
        claims["aud"] = [CLIENT, AUDIENCE]
    elif attack == "foreign_azp":
        claims["azp"] = "another-client"
    elif attack == "foreign_issuer":
        claims["iss"] = "https://foreign-issuer.invalid"
    else:
        claims["exp"], claims["iat"] = NOW - 30, NOW - 60
    rejected(lambda: verifier.verify_login(signed(private, claims), access, nonce_hash, keys))


def test_login_rejects_tampered_id_signature_even_with_valid_nonce_and_access(material, verifier):
    private, other, keys = material
    _, access, nonce_hash, claims = login_tokens(private)
    rejected(lambda: verifier.verify_login(signed(other, claims), access, nonce_hash, keys))


@pytest.mark.parametrize("bad_nonce", [None, "", "malformed", True, "A" * 42 + "B"])
def test_login_requires_canonical_matching_nonce(material, verifier, bad_nonce):
    private, _, keys = material
    id_token, access, nonce_hash, _ = login_tokens(private, id_changes={"nonce": bad_nonce})
    rejected(lambda: verifier.verify_login(id_token, access, nonce_hash, keys))


def test_login_missing_or_different_valid_nonce_is_rejected(material, verifier):
    private, _, keys = material
    _, access, nonce_hash, claims = login_tokens(private)
    claims.pop("nonce")
    rejected(lambda: verifier.verify_login(signed(private, claims), access, nonce_hash, keys))
    claims["nonce"] = new_token()
    rejected(lambda: verifier.verify_login(signed(private, claims), access, nonce_hash, keys))


@pytest.mark.parametrize("bad_hash", [None, "", "x" * 64, "A" * 64, "0" * 63])
def test_login_internal_nonce_hash_input_is_safe_dependency_error(material, verifier, bad_hash):
    private, _, keys = material
    id_token, access, _, _ = login_tokens(private)
    rejected(lambda: verifier.verify_login(id_token, access, bad_hash, keys), 503)


@pytest.mark.parametrize("bad_hash", [None, "", True, "A" * 21 + "B", "A" * 22 + "=", "A" * 43])
def test_login_at_hash_if_present_has_strict_type_length_and_encoding(material, verifier, bad_hash):
    private, _, keys = material
    id_token, access, nonce_hash, _ = login_tokens(private, id_changes={"at_hash": bad_hash})
    rejected(lambda: verifier.verify_login(id_token, access, nonce_hash, keys))


def test_login_rejects_access_substitution_subject_mismatch_and_swapped_kinds(material, verifier):
    private, _, keys = material
    id_token, access, nonce_hash, claims = login_tokens(private)
    changed_access = signed(private, access_claims(name="Different but correctly signed"))
    rejected(lambda: verifier.verify_login(id_token, changed_access, nonce_hash, keys))
    # Remove at_hash so the subject-equality check independently rejects the pair.
    claims.pop("at_hash")
    mismatched_access = signed(private, access_claims(sub="SYNTHETIC-SUBJECT"))
    rejected(
        lambda: verifier.verify_login(signed(private, claims), mismatched_access, nonce_hash, keys)
    )
    rejected(lambda: verifier.verify_login(access, id_token, nonce_hash, keys))
