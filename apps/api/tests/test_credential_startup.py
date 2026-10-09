"""SPEC-0001 B2a4b A4b-08: fail closed before application dependencies start."""

import asyncio
from unittest.mock import Mock

import pytest

import torii_api.app as app_module
from torii_api.config import Settings
from torii_api.domain.errors import DomainError


def test_factory_does_not_configure_logging_or_create_engine(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = Mock()
    engine = Mock()
    monkeypatch.setattr(app_module, "configure_credential_logging", policy)
    monkeypatch.setattr(app_module, "make_engine", engine)
    app = app_module.create_app(settings)
    assert {route.path for route in app.routes} == {"/health/live", "/health/ready"}
    policy.assert_not_called()
    engine.assert_not_called()


def test_policy_failure_prevents_dependency_startup(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = Mock(side_effect=DomainError(503, "identity_unavailable"))
    engine = Mock()
    monkeypatch.setattr(app_module, "configure_credential_logging", policy)
    monkeypatch.setattr(app_module, "make_engine", engine)
    app = app_module.create_app(settings)

    async def start() -> None:
        async with app.router.lifespan_context(app):
            pytest.fail("Startup must not yield after a policy failure")

    with pytest.raises(DomainError) as caught:
        asyncio.run(start())
    assert (caught.value.status, caught.value.code) == (503, "identity_unavailable")
    engine.assert_not_called()


def test_policy_precedes_dependencies_and_engine_is_disposed(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    engine = Mock()
    engine.dispose.side_effect = lambda: events.append("disposed")

    def configure() -> None:
        events.append("policy")

    def make_engine(_url: str) -> Mock:
        assert events == ["policy"]
        events.append("engine")
        return engine

    monkeypatch.setattr(app_module, "configure_credential_logging", configure)
    monkeypatch.setattr(app_module, "make_engine", make_engine)
    app = app_module.create_app(settings)

    async def start() -> None:
        async with app.router.lifespan_context(app):
            assert app.state.engine is engine
            events.append("serving")

    asyncio.run(start())
    assert events == ["policy", "engine", "serving", "disposed"]
