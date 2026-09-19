"""SPEC-0001 B2a1: internal persistence is not a login or token verifier."""

import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from torii_api.application.identity_store import (
    ActiveSession,
    ConsumedFlow,
    Flow,
    NewSession,
    Principal,
    RevokedSession,
)


def test_auth_result_reprs_do_not_expose_secrets_or_display_name():
    marker = "SYNTHETIC_SENSITIVE_MARKER"
    principal = Principal(uuid4(), marker, False)
    for result in (
        principal,
        Flow(marker, marker, marker, marker),
        ConsumedFlow(marker, marker),
        NewSession(marker, marker, principal, datetime.now(UTC)),
        ActiveSession(principal, marker, datetime.now(UTC)),
        RevokedSession(marker, False),
    ):
        assert marker not in repr(result)


@pytest.mark.parametrize("path", ["/auth/login", "/auth/callback", "/api/v1/session"])
def test_b2a1_does_not_expose_auth_routes(client, path):
    assert client.get(path).status_code == 404


def test_identity_store_has_no_network_or_jwt_imports():
    path = Path(__file__).resolve().parents[1] / "src/torii_api/application/identity_store.py"
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    assert not modules.intersection({"jwt", "httpx", "urllib", "requests", "socket", "fastapi"})
