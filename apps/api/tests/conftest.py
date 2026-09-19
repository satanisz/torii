from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from torii_api.app import create_app
from torii_api.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings.from_env(
        {
            "TORII_PROFILE": "test",
            "TORII_DATABASE_URL": "postgresql+psycopg://torii_runtime:fixture@127.0.0.1:1/torii",
            "TORII_SESSION_KEY": Fernet.generate_key().decode(),
            "TORII_CURSOR_KEY": "synthetic-cursor-key-" + "a" * 32,
            "TORII_OIDC_CLIENT_SECRET": "synthetic-client-secret-" + "b" * 32,
            "TORII_PUBLIC_URL": "https://localhost:9443",
            "TORII_OIDC_ISSUER": "https://localhost:9443/identity/realms/torii-dev",
            "TORII_OIDC_BACKCHANNEL_URL": "http://identity:8080/identity/realms/torii-dev",
            "TORII_OIDC_CLIENT_ID": "torii-web",
            "TORII_OIDC_AUDIENCE": "torii-api",
        }
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url=settings.public_url) as test_client:
        yield test_client
