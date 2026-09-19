"""SPEC-0002 AC-03/05/07 foundation HTTP; readiness success needs real DB later."""

import json
import logging
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from torii_api.app import create_app
from torii_api.config import Settings
from torii_api.http.json import decode_json


def test_liveness_generates_id_and_no_store(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "untrusted-secret"})
    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert UUID(response.headers["X-Request-ID"]).version == 4
    assert response.headers["cache-control"] == "no-store"


def test_unknown_and_disallowed_method_are_problem_details(client: TestClient) -> None:
    for method, path, status in [("GET", "/missing", 404), ("POST", "/health/live", 405)]:
        response = client.request(method, path)
        assert response.status_code == status
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_health_rejects_nonempty_body(client: TestClient) -> None:
    response = client.request("GET", "/health/live", content=b"{}")
    assert response.status_code == 400
    assert response.json()["code"] == "unexpected_body"


def test_body_size_enforced_even_without_content_length(client: TestClient) -> None:
    response = client.request("GET", "/health/live", content=iter([b"x" * 200000, b"y" * 100000]))
    assert response.status_code == 413


def test_invalid_host_and_proxy_headers_cannot_select_origin(client: TestClient) -> None:
    response = client.get("/health/live", headers={"Host": "evil.invalid"})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_host"
    response = client.get(
        "/health/live",
        headers={"Forwarded": "host=evil.invalid;proto=http", "X-Forwarded-Host": "evil.invalid"},
    )
    assert response.status_code == 200


def test_readiness_failure_never_exposes_dsn(client: TestClient) -> None:
    with patch("torii_api.app.is_ready", return_value=False):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "3"
    assert "fixture" not in response.text
    assert "postgres" not in response.text


def test_error_and_access_log_redacted(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(settings)

    @app.get("/test-crash")
    async def crash() -> None:
        raise RuntimeError("secret-dsn-token")

    with (
        TestClient(app, base_url=settings.public_url) as client,
        caplog.at_level(logging.INFO, logger="torii.access"),
    ):
        response = client.get(
            "/test-crash?code=secret-dsn-token", headers={"X-Request-ID": "secret-dsn-token"}
        )
    assert response.status_code == 500
    assert "secret-dsn-token" not in response.text
    assert "secret-dsn-token" not in caplog.text
    event = json.loads(caplog.records[-1].message)
    assert event["status"] == 500
    assert event["request_id"] == response.headers["X-Request-ID"]


def test_json_transport_adapts_domain_errors(settings: Settings) -> None:
    app = create_app(settings)

    @app.post("/test-json")
    async def parse(request: Request) -> object:
        return decode_json(await request.body(), request.headers.get("content-type"))

    with TestClient(app, base_url=settings.public_url) as client:
        response = client.post(
            "/test-json",
            content=b'{"secret": 1, "secret": 2}',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_json"
    assert "secret" not in response.text
