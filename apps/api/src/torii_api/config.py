"""Explicit, validated dev/test configuration; no environment-file auto-discovery."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class ConfigurationError(ValueError):
    """Only configuration key names may appear in messages."""


def read_secret(env: Mapping[str, str], name: str) -> str:
    direct, file_name = name in env, f"{name}_FILE" in env
    if direct == file_name:
        raise ConfigurationError(f"Configure exactly one source for {name}")
    if direct:
        if env.get("TORII_PROFILE") != "test":
            raise ConfigurationError(f"{name} requires a secret file outside explicit tests")
        value = env[name]
    else:
        try:
            path = Path(env[f"{name}_FILE"])
            if not path.is_absolute() or path.stat().st_size > 8192:
                raise ValueError("Invalid path")
            value = path.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            raise ConfigurationError(f"Cannot read {name} secret file") from None
    if not value or len(value) > 8192 or "\x00" in value:
        raise ConfigurationError(f"Invalid {name}")
    return value


def database_url(env: Mapping[str, str] | None = None) -> str:
    value = read_secret(os.environ if env is None else env, "TORII_DATABASE_URL")
    try:
        parsed = make_url(value)
        valid = (
            parsed.drivername == "postgresql+psycopg"
            and parsed.host
            and parsed.username
            and parsed.password
            and parsed.database
        )
        if not valid:
            raise ValueError("Invalid DSN")
    except (ValueError, ArgumentError):
        raise ConfigurationError("Invalid TORII_DATABASE_URL") from None
    return value


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value or len(value) > 2048 or value != value.strip():
        raise ConfigurationError(f"Invalid {name}")
    return value


def _url(value: str, name: str, *, internal: bool = False) -> None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ({"http", "https"} if internal else {"https"})
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port == 0
        ):
            raise ValueError("Invalid URL")
        if internal and parsed.scheme == "http" and parsed.hostname != "identity":
            raise ValueError("Untrusted plaintext backchannel")
    except ValueError:
        raise ConfigurationError(f"Invalid {name}") from None


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    session_key: str = field(repr=False)
    cursor_key: str = field(repr=False)
    oidc_client_secret: str = field(repr=False)
    public_url: str
    oidc_issuer: str
    oidc_backchannel_url: str
    oidc_client_id: str
    oidc_audience: str
    profile: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        profile = env.get("TORII_PROFILE", "dev")
        if profile not in {"dev", "test"}:
            raise ConfigurationError("Only dev/test profiles are qualified by this increment")
        public = _required(env, "TORII_PUBLIC_URL")
        issuer = _required(env, "TORII_OIDC_ISSUER")
        backchannel = _required(env, "TORII_OIDC_BACKCHANNEL_URL")
        _url(public, "TORII_PUBLIC_URL")
        _url(issuer, "TORII_OIDC_ISSUER")
        _url(backchannel, "TORII_OIDC_BACKCHANNEL_URL", internal=True)
        if urlsplit(public).path or not issuer.startswith(f"{public}/identity/realms/"):
            raise ConfigurationError("Public origin and OIDC issuer do not match dev topology")
        if urlsplit(issuer).path != urlsplit(backchannel).path:
            raise ConfigurationError("OIDC backchannel realm does not match issuer")
        session_key = read_secret(env, "TORII_SESSION_KEY")
        try:
            Fernet(session_key.encode("ascii"))
        except (ValueError, UnicodeError):
            raise ConfigurationError("Invalid TORII_SESSION_KEY") from None
        cursor_key = read_secret(env, "TORII_CURSOR_KEY")
        client_secret = read_secret(env, "TORII_OIDC_CLIENT_SECRET")
        if len(cursor_key.encode()) < 32 or len(client_secret) < 32:
            raise ConfigurationError("Insufficient cryptographic secret length")
        return cls(
            database_url(env),
            session_key,
            cursor_key,
            client_secret,
            public,
            issuer,
            backchannel,
            _required(env, "TORII_OIDC_CLIENT_ID"),
            _required(env, "TORII_OIDC_AUDIENCE"),
            profile,
        )
