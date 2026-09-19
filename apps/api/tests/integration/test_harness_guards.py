"""Pure regression tests for B1 target guards; no Docker/DB/network is called."""

import json
import os
import subprocess
from unittest.mock import Mock

import pytest
from conftest import (
    POSTGRES_IMAGE,
    Harness,
    local_docker_endpoint,
    reject_ambient_environment,
    verify_docker_context,
)


@pytest.mark.parametrize(
    "name",
    ["PGHOSTADDR", "PGSSLMODE", "PGPASSWORD", "pgservice", "Pg", "DOCKER_HOST", "docker_host"],
)
@pytest.mark.parametrize("value", ["", "SYNTHETIC_SENSITIVE_VALUE"])
def test_ambient_override_is_rejected_without_echo(name, value):
    with pytest.raises(pytest.fail.Exception) as caught:
        reject_ambient_environment({name: value})
    assert name not in str(caught.value)
    assert "SYNTHETIC_SENSITIVE_VALUE" not in str(caught.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "npipe:////./pipe/dockerDesktopLinuxEngine",
        "npipe://./pipe/docker_engine",
        "unix:///var/run/docker.sock",
        "unix:///Users/example/.docker/run/docker.sock",
    ],
)
def test_only_local_endpoint_shapes_are_accepted(endpoint):
    assert local_docker_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "tcp://127.0.0.1:2375",
        "tcp://remote.invalid:2376",
        "ssh://remote.invalid",
        "npipe:////remote/pipe/docker",
        "unix://remote/run/docker.sock",
        "unix:////remote/run/docker.sock",
        "unix:///tmp/docker.sock?x=1",
        "",
        "relative.sock",
    ],
)
def test_remote_or_ambiguous_endpoint_shapes_are_rejected(endpoint):
    assert not local_docker_endpoint(endpoint)


def test_ambient_guard_precedes_docker_inspect(monkeypatch):
    command = Mock(side_effect=AssertionError("No subprocess may run"))
    monkeypatch.setattr(subprocess, "run", command)
    monkeypatch.setenv("PGHOSTADDR", "SYNTHETIC_SENSITIVE_VALUE")
    with pytest.raises(pytest.fail.Exception):
        verify_docker_context("desktop-linux")
    command.assert_not_called()


def test_remote_context_rejected_before_container_inspect(monkeypatch):
    for name in list(os.environ):
        if name.upper().startswith("PG") or name.upper() == "DOCKER_HOST":
            monkeypatch.delenv(name)
    command = Mock(
        return_value=subprocess.CompletedProcess([], 0, json.dumps("ssh://remote.invalid"), "")
    )
    monkeypatch.setattr(subprocess, "run", command)
    with pytest.raises(pytest.fail.Exception):
        verify_docker_context("remote-context")
    assert command.call_count == 1
    assert command.call_args.args[0][:3] == ["docker", "context", "inspect"]


def test_container_inspection_pins_verified_context(monkeypatch):
    for name in list(os.environ):
        if name.upper().startswith("PG") or name.upper() == "DOCKER_HOST":
            monkeypatch.delenv(name)
    run_id, container_id = "a" * 32, "b" * 64
    state = {
        "id": container_id,
        "running": True,
        "image": POSTGRES_IMAGE,
        "labels": {"io.torii.scope": "b1-integration", "io.torii.test-run": run_id},
        "ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]},
    }
    command = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0, json.dumps("unix:///var/run/docker.sock"), ""),
            subprocess.CompletedProcess([], 0, json.dumps(state), ""),
        ]
    )
    monkeypatch.setattr(subprocess, "run", command)
    harness = Harness(run_id, container_id, 15432, "local-context", "", "", "")
    harness.verify_container()
    assert command.call_args_list[1].args[0][:4] == [
        "docker",
        "--context",
        "local-context",
        "inspect",
    ]
