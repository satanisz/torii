"""SPEC-0002 AC-03/05: fail-closed local configuration without secret disclosure."""

import traceback
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from torii_api.config import ConfigurationError, Settings, database_url, read_secret


@pytest.fixture
def config_env() -> dict[str, str]:
    return {
        "TORII_PROFILE": "test",
        "TORII_DATABASE_URL": "postgresql+psycopg://torii_runtime:secret@database/torii_platform",
        "TORII_SESSION_KEY": Fernet.generate_key().decode(),
        "TORII_CURSOR_KEY": "synthetic-cursor-key-" + "a" * 32,
        "TORII_OIDC_CLIENT_SECRET": "synthetic-client-secret-" + "b" * 32,
        "TORII_PUBLIC_URL": "https://localhost:9443",
        "TORII_OIDC_ISSUER": "https://localhost:9443/identity/realms/torii-dev",
        "TORII_OIDC_BACKCHANNEL_URL": "http://identity:8080/identity/realms/torii-dev",
        "TORII_OIDC_CLIENT_ID": "torii-web",
        "TORII_OIDC_AUDIENCE": "torii-api",
    }


def test_valid_config_never_repr_secrets(config_env: dict[str, str]) -> None:
    settings = Settings.from_env(config_env)
    assert settings.public_url == "https://localhost:9443"
    for name in (
        "TORII_DATABASE_URL",
        "TORII_SESSION_KEY",
        "TORII_CURSOR_KEY",
        "TORII_OIDC_CLIENT_SECRET",
    ):
        assert config_env[name] not in repr(settings)


@pytest.mark.parametrize(
    "name",
    [
        "TORII_DATABASE_URL",
        "TORII_SESSION_KEY",
        "TORII_CURSOR_KEY",
        "TORII_OIDC_CLIENT_SECRET",
        "TORII_OIDC_ISSUER",
    ],
)
def test_missing_critical_config_rejected(config_env: dict[str, str], name: str) -> None:
    del config_env[name]
    with pytest.raises(ConfigurationError):
        Settings.from_env(config_env)


@pytest.mark.parametrize(
    "name,value",
    [
        ("TORII_SESSION_KEY", "bad-secret-value"),
        ("TORII_DATABASE_URL", "sqlite:///:memory:"),
        ("TORII_PUBLIC_URL", "http://localhost:9443"),
        ("TORII_PUBLIC_URL", "https://user:password@localhost:9443/path"),
        ("TORII_OIDC_ISSUER", "https://attacker.invalid/realms/other"),
        ("TORII_OIDC_BACKCHANNEL_URL", "http://evil.invalid/identity/realms/torii-dev"),
        ("TORII_PROFILE", "prod"),
    ],
)
def test_bad_config_errors_do_not_expose_values(
    config_env: dict[str, str], name: str, value: str
) -> None:
    config_env[name] = value
    with pytest.raises(ConfigurationError) as err:
        Settings.from_env(config_env)
    assert value not in str(err.value)


def test_secret_files_and_ambiguous_empty_env(tmp_path: Path) -> None:
    path = tmp_path / "test-secret"
    path.write_text("fixture-secret\n", encoding="utf-8")
    env = {"TORII_TEST_FILE": str(path)}
    assert read_secret(env, "TORII_TEST") == "fixture-secret"
    env["TORII_TEST"] = ""
    with pytest.raises(ConfigurationError):
        read_secret(env, "TORII_TEST")


def test_direct_secrets_only_in_explicit_test(config_env: dict[str, str]) -> None:
    config_env["TORII_PROFILE"] = "dev"
    with pytest.raises(ConfigurationError):
        Settings.from_env(config_env)


def test_migrator_database_config_independent_of_oidc(tmp_path: Path) -> None:
    path = tmp_path / "dsn"
    path.write_text("postgresql+psycopg://torii_migrator:fake@database/torii_platform")
    assert database_url({"TORII_DATABASE_URL_FILE": str(path)}).startswith("postgresql+psycopg:")


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+psycopg://user:secret@localhost:SECRET_MARKER/database",
        "SECRET_MARKER-not-a-dsn",
    ],
)
def test_invalid_dsn_traceback_does_not_expose_secret(value: str) -> None:
    try:
        database_url({"TORII_PROFILE": "test", "TORII_DATABASE_URL": value})
    except ConfigurationError as exc:
        rendered = "".join(traceback.format_exception(exc))
        assert "SECRET_MARKER" not in rendered
    else:
        pytest.fail("Invalid DSN accepted")
