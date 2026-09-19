"""SPEC-0001 B1: new, guarded PostgreSQL database for every integration test.

Only deploy/platform/test-projects.ps1 provisions the dedicated ephemeral server.
No fixture accepts an external DSN or uses an existing application database.
"""

import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from torii_api.storage.database import make_engine

POSTGRES_IMAGE = (
    "postgres:17@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675"
)
API_ROOT = Path(__file__).resolve().parents[2]
ENV_KEYS = (
    "TORII_B1_RUN_ID",
    "TORII_B1_CONTAINER_ID",
    "TORII_B1_PORT",
    "TORII_B1_DOCKER_CONTEXT",
    "TORII_B1_ADMIN_PASSWORD",
    "TORII_B1_MIGRATOR_PASSWORD",
    "TORII_B1_RUNTIME_PASSWORD",
)


def reject_ambient_environment(environ: Mapping[str, str]) -> None:
    if any(name.upper().startswith("PG") or name.upper() == "DOCKER_HOST" for name in environ):
        pytest.fail(
            "Inherited database or Docker endpoint environment is forbidden for B1 tests",
            pytrace=False,
        )


def local_docker_endpoint(endpoint: str) -> bool:
    return bool(
        re.fullmatch(r"npipe:/{2,4}\./pipe/[A-Za-z0-9_.-]+", endpoint)
        or re.fullmatch(r"unix:///(?!/)[^\x00\r\n?#]+", endpoint)
    )


def verify_docker_context(context: str) -> None:
    reject_ambient_environment(os.environ)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", context):
        pytest.fail("Invalid B1 Docker context", pytrace=False)
    try:
        result = subprocess.run(
            [
                "docker",
                "context",
                "inspect",
                context,
                "--format",
                "{{json .Endpoints.docker.Host}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        endpoint = json.loads(result.stdout)
        valid = (
            result.returncode == 0 and isinstance(endpoint, str) and local_docker_endpoint(endpoint)
        )
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        valid = False
    if not valid:
        pytest.fail("B1 tests require a verified local Docker pipe or Unix socket", pytrace=False)


@dataclass(frozen=True)
class DatabasePair:
    runtime: Engine
    migrator: Engine


@dataclass(frozen=True)
class Harness:
    run_id: str
    container_id: str
    port: int
    docker_context: str
    admin_password: str = field(repr=False)
    migrator_password: str = field(repr=False)
    runtime_password: str = field(repr=False)

    def url(self, username: str, password: str, database: str) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=username,
            password=password,
            host="127.0.0.1",
            port=self.port,
            database=database,
        )

    def verify_container(self) -> None:
        verify_docker_context(self.docker_context)
        template = (
            '{"id":"{{.Id}}","running":{{.State.Running}},'
            '"image":"{{.Config.Image}}","labels":{{json .Config.Labels}},'
            '"ports":{{json .NetworkSettings.Ports}}}'
        )
        try:
            result = subprocess.run(
                [
                    "docker",
                    "--context",
                    self.docker_context,
                    "inspect",
                    "--format",
                    template,
                    self.container_id,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            state: dict[str, Any] = json.loads(result.stdout)
            expected_port = [{"HostIp": "127.0.0.1", "HostPort": str(self.port)}]
            valid = (
                result.returncode == 0
                and state["id"] == self.container_id
                and state["running"] is True
                and state["image"] == POSTGRES_IMAGE
                and state["labels"].get("io.torii.scope") == "b1-integration"
                and state["labels"].get("io.torii.test-run") == self.run_id
                and state["ports"].get("5432/tcp") == expected_port
            )
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            pytest.fail(
                "B1 PostgreSQL container ownership/binding could not be verified", pytrace=False
            )


@pytest.fixture(scope="session")
def _b1_harness() -> Harness:
    present = [name in os.environ for name in ENV_KEYS]
    if not any(present):
        pytest.skip("Real PostgreSQL integration requires deploy/platform/test-projects.ps1")
    reject_ambient_environment(os.environ)
    if not all(present):
        pytest.fail("Incomplete TORII_B1_* harness configuration", pytrace=False)
    values = {name: os.environ[name] for name in ENV_KEYS}
    if (
        not re.fullmatch(r"[0-9a-f]{32}", values["TORII_B1_RUN_ID"])
        or not re.fullmatch(r"[0-9a-f]{64}", values["TORII_B1_CONTAINER_ID"])
        or not re.fullmatch(r"[0-9]{1,5}", values["TORII_B1_PORT"])
        or not 1024 <= int(values["TORII_B1_PORT"]) <= 65535
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", values["TORII_B1_DOCKER_CONTEXT"])
        or any(not re.fullmatch(r"[0-9a-f]{64}", values[name]) for name in ENV_KEYS[4:])
    ):
        pytest.fail("Invalid TORII_B1_* harness configuration", pytrace=False)
    harness = Harness(
        run_id=values["TORII_B1_RUN_ID"],
        container_id=values["TORII_B1_CONTAINER_ID"],
        port=int(values["TORII_B1_PORT"]),
        docker_context=values["TORII_B1_DOCKER_CONTEXT"],
        admin_password=values["TORII_B1_ADMIN_PASSWORD"],
        migrator_password=values["TORII_B1_MIGRATOR_PASSWORD"],
        runtime_password=values["TORII_B1_RUNTIME_PASSWORD"],
    )
    harness.verify_container()
    return harness


@pytest.fixture
def db_pair(_b1_harness: Harness) -> Iterator[DatabasePair]:
    """Fresh migrated database; tests seed their actors through `.migrator`."""
    harness = _b1_harness
    harness.verify_container()
    database = f"torii_b1_{uuid.uuid4().hex}"
    admin = create_engine(
        harness.url("postgres", harness.admin_password, "postgres"),
        isolation_level="AUTOCOMMIT",
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )
    migrator_url = harness.url("torii_migrator", harness.migrator_password, database)
    runtime_url = harness.url("torii_runtime", harness.runtime_password, database)
    migrator = make_engine(migrator_url.render_as_string(hide_password=False))
    runtime = make_engine(runtime_url.render_as_string(hide_password=False))
    created = False
    marked = False
    try:
        try:
            with admin.connect() as connection:
                # Identifiers and marker come only from UUID/validated hex, never test payloads.
                connection.execute(text(f'CREATE DATABASE "{database}" OWNER torii_migrator'))
                created = True
                connection.execute(
                    text(
                        f"ALTER DATABASE \"{database}\" SET torii.test_run_id = '{harness.run_id}'"
                    )
                )
                marked = True
                connection.execute(text(f'REVOKE ALL ON DATABASE "{database}" FROM PUBLIC'))
                connection.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO torii_runtime'))
            with migrator.begin() as connection:
                connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
                connection.execute(text("GRANT USAGE ON SCHEMA public TO torii_runtime"))
            migration_env = dict(os.environ)
            migration_env.pop("TORII_DATABASE_URL_FILE", None)
            migration_env.update(
                TORII_PROFILE="test",
                TORII_DATABASE_URL=migrator_url.render_as_string(hide_password=False),
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    str(API_ROOT / "alembic.ini"),
                    "upgrade",
                    "head",
                ],
                cwd=API_ROOT,
                env=migration_env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                pytest.fail(
                    "B1 migration failed; raw diagnostics withheld to protect credentials",
                    pytrace=False,
                )
            with runtime.connect() as connection:
                if connection.scalar(text("SELECT current_user")) != "torii_runtime":
                    pytest.fail("B1 service engine is not using the runtime role", pytrace=False)
        except (OSError, subprocess.SubprocessError, SQLAlchemyError):
            pytest.fail("B1 bootstrap or migration process failed", pytrace=False)
        yield DatabasePair(runtime=runtime, migrator=migrator)
    finally:
        runtime.dispose()
        try:
            if created:
                harness.verify_container()
                with admin.connect() as connection:
                    owner = connection.scalar(
                        text(
                            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = :name"
                        ),
                        {"name": database},
                    )
                    if owner != "torii_migrator":
                        pytest.fail("B1 cleanup refused: database ownership changed", pytrace=False)
                if not marked:
                    pytest.fail(
                        "B1 database marker missing; defer cleanup to owned-container removal",
                        pytrace=False,
                    )
                with migrator.connect() as connection:
                    if (
                        connection.scalar(text("SELECT current_setting('torii.test_run_id', true)"))
                        != harness.run_id
                    ):
                        pytest.fail("B1 cleanup refused: database marker changed", pytrace=False)
                migrator.dispose()
                with admin.connect() as connection:
                    connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        finally:
            migrator.dispose()
            admin.dispose()
