"""SPEC-0020 AC-04/05: exercise MLflow 3.14.0 ACLs through its SDK and HTTP.

Only generated trial resources are mutated. Secrets are read from container secret
files and never serialized. The harness has no storage/database credentials.
"""

# check() executes callbacks synchronously, before a loop advances.
# ruff: noqa: B023

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import tempfile
import uuid
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests
from mlflow.entities import Metric, Param, RunTag
from mlflow.server import get_app_client

import mlflow
from mlflow import MlflowClient

URI = "http://mlflow:5000"
USERS = {"A": "analyst_a", "B": "analyst_b", "admin": "admin"}
SECRET_FILES = {"A": "user_a", "B": "user_b", "admin": "admin_password"}
PAYLOAD = b'{"kind":"synthetic_finance_rule","version":1,"threshold":100000}\n'
PAYLOAD_HASH = hashlib.sha256(PAYLOAD).hexdigest()


def http_status(exc: Exception) -> int | None:
    """Retain only structured HTTP status, never arbitrary exception text."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        if response is not None and isinstance(
            getattr(response, "status_code", None), int
        ):
            return response.status_code
        get_status = getattr(current, "get_http_status_code", None)
        if callable(get_status):
            status = get_status()
            if status in (401, 403, 404):
                return status
        current = current.__cause__ or current.__context__
    return None


class Harness:
    def __init__(self) -> None:
        self.matrix: list[dict[str, Any]] = []
        self.resources: dict[str, dict[str, str]] = {}
        self.secrets = {
            actor: (Path("/run/secrets") / filename).read_text().strip()
            for actor, filename in SECRET_FILES.items()
        }
        if not all(self.secrets.values()):
            raise ValueError("empty_secret")
        self.prefix = "exp03_" + uuid.uuid4().hex
        self.session = requests.Session()
        self.session.trust_env = False

    @contextlib.contextmanager
    def identity(self, actor: str):
        keys = (
            "MLFLOW_TRACKING_USERNAME",
            "MLFLOW_TRACKING_PASSWORD",
            "MLFLOW_TRACKING_TOKEN",
        )
        previous = {key: os.environ.get(key) for key in keys}
        os.environ["MLFLOW_TRACKING_USERNAME"] = USERS[actor]
        os.environ["MLFLOW_TRACKING_PASSWORD"] = self.secrets[actor]
        os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
        try:
            yield MlflowClient(tracking_uri=URI, registry_uri=URI)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def record(self, case: str, actor: str, status: str, **detail: Any) -> None:
        self.matrix.append({"case": case, "actor": actor, "status": status, **detail})

    def check(
        self,
        case: str,
        actor: str,
        operation: Callable[[MlflowClient], Any],
        predicate: Callable[[Any], bool] = lambda _: True,
        *,
        denied: bool = False,
        filter_or_deny: bool = False,
    ) -> Any:
        try:
            with self.identity(actor) as client:
                result = operation(client)
            passed = not denied and bool(predicate(result))
            self.record(case, actor, "PASS" if passed else "FAIL")
            return result if passed else None
        except Exception as exc:  # noqa: BLE001 - safe report boundary, never prints exceptions
            status = http_status(exc)
            passed = (denied or filter_or_deny) and status in (403, 404)
            self.record(case, actor, "PASS" if passed else "FAIL", http_status=status)
            return None

    def raw(
        self,
        case: str,
        actor: str | None,
        method: str,
        path: str,
        *,
        expect_denied: bool = False,
        content: bytes | None = None,
        params: dict[str, Any] | None = None,
        body: bytes | None = None,
    ) -> None:
        try:
            response = self.session.request(
                method,
                URI + path,
                auth=(USERS[actor], self.secrets[actor]) if actor else None,
                params=params,
                data=body,
                timeout=15,
                allow_redirects=False,
            )
            if expect_denied:
                passed = response.status_code in (
                    (401,) if actor is None else (403, 404)
                )
            else:
                passed = response.status_code == 200
                if content is not None:
                    passed = (
                        passed
                        and hashlib.sha256(response.content).digest()
                        == hashlib.sha256(content).digest()
                    )
            self.record(
                case,
                actor or "anonymous",
                "PASS" if passed else "FAIL",
                http_status=response.status_code,
            )
        except requests.RequestException:
            self.record(case, actor or "anonymous", "FAIL", http_status=None)

    @staticmethod
    def all_experiments(client: MlflowClient) -> set[str]:
        ids: set[str] = set()
        token = None
        for _ in range(1000):
            page = client.search_experiments(max_results=1, page_token=token)
            ids.update(item.experiment_id for item in page)
            if not page.token:
                return ids
            token = page.token
        raise ValueError("pagination_limit")

    @staticmethod
    def all_models(client: MlflowClient) -> set[str]:
        names: set[str] = set()
        token = None
        for _ in range(1000):
            page = client.search_registered_models(max_results=1, page_token=token)
            names.update(item.name for item in page)
            if not page.token:
                return names
            token = page.token
        raise ValueError("pagination_limit")

    @staticmethod
    def download(client: MlflowClient, run_id: str, directory: str) -> str:
        result = client.download_artifacts(run_id, "rules/policy.json", directory)
        return hashlib.sha256(Path(result).read_bytes()).hexdigest()

    @staticmethod
    def uri_download(uri: str, directory: str) -> str:
        result = mlflow.artifacts.download_artifacts(
            artifact_uri=uri, dst_path=directory
        )
        return hashlib.sha256(Path(result).read_bytes()).hexdigest()

    def create_resources(self, directory: Path) -> None:
        policy = directory / "policy.json"
        policy.write_bytes(PAYLOAD)
        for actor in ("A", "B"):
            name = self.prefix + "_" + actor.lower()
            experiment = self.check(
                "own.experiment.create", actor, lambda c: c.create_experiment(name)
            )
            if experiment is None:
                raise ValueError("experiment_setup")
            run = self.check(
                "own.run.create", actor, lambda c: c.create_run(experiment)
            )
            if run is None:
                raise ValueError("run_setup")
            run_id = run.info.run_id
            model = self.check(
                "own.registry.create", actor, lambda c: c.create_registered_model(name)
            )
            if model is None:
                raise ValueError("model_setup")
            self.check(
                "own.run.log_batch",
                actor,
                lambda c: c.log_batch(
                    run_id,
                    metrics=[Metric("synthetic_metric", 1.25, 0, 0)],
                    params=[Param("model_kind", "rule_without_fit")],
                    tags=[RunTag("trial", self.prefix)],
                ),
            )
            self.check(
                "own.artifact.upload",
                actor,
                lambda c: c.log_artifact(run_id, str(policy), "rules"),
            )
            version = self.check(
                "own.registry.version_create",
                actor,
                lambda c: c.create_model_version(
                    name, f"runs:/{run_id}/rules", run_id=run_id
                ),
            )
            if version is None:
                raise ValueError("version_setup")
            self.check(
                "own.registry.alias_set",
                actor,
                lambda c: c.set_registered_model_alias(
                    name, "candidate", version.version
                ),
            )
            parsed = urlparse(run.info.artifact_uri)
            if parsed.scheme != "mlflow-artifacts" or parsed.netloc:
                self.record("artifact.proxy_uri", actor, "FAIL")
                raise ValueError("proxy_required")
            self.record("artifact.proxy_uri", actor, "PASS")
            relative_path = parsed.path.strip("/") + "/rules/policy.json"
            if not relative_path.startswith(
                experiment + "/"
            ) or ".." in relative_path.split("/"):
                raise ValueError("proxy_path")
            self.resources[actor] = {
                "experiment_id": experiment,
                "run_id": run_id,
                "model_name": name,
                "version": version.version,
                "artifact_uri": run.info.artifact_uri + "/rules/policy.json",
                "raw_path": "/api/2.0/mlflow-artifacts/artifacts/"
                + quote(relative_path, safe="/"),
                "raw_list_path": parsed.path.strip("/") + "/rules",
            }

    def own_and_foreign(self, directory: Path) -> None:
        upload = directory / "intruder.json"
        upload.write_text('{"synthetic_test":true}\n')
        for actor, other in (("A", "B"), ("B", "A")):
            own, foreign = self.resources[actor], self.resources[other]
            oid, fid = own["experiment_id"], foreign["experiment_id"]
            orid, frid = own["run_id"], foreign["run_id"]
            omodel, fmodel = own["model_name"], foreign["model_name"]
            self.check(
                "own.experiment.get",
                actor,
                lambda c: c.get_experiment(oid),
                lambda r: r.experiment_id == oid,
            )
            self.check(
                "own.run.get",
                actor,
                lambda c: c.get_run(orid),
                lambda r: r.info.run_id == orid,
            )
            self.check(
                "own.run.mutate", actor, lambda c: c.set_tag(orid, "own_edit", "ok")
            )
            self.check(
                "own.run.metrics",
                actor,
                lambda c: c.get_metric_history(orid, "synthetic_metric"),
                lambda rows: len(rows) == 1 and rows[0].value == 1.25,
            )
            self.check(
                "list.experiments.content",
                actor,
                self.all_experiments,
                lambda rows: oid in rows and fid not in rows,
            )
            self.check(
                "search.experiments.foreign",
                actor,
                lambda c: c.search_experiments(filter_string=f"name = '{fmodel}'"),
                lambda rows: len(rows) == 0,
                filter_or_deny=True,
            )
            self.check(
                "search.runs.own",
                actor,
                lambda c: c.search_runs([oid]),
                lambda rows: orid in {r.info.run_id for r in rows},
            )
            self.check(
                "search.runs.foreign",
                actor,
                lambda c: c.search_runs([fid]),
                lambda rows: len(rows) == 0,
                filter_or_deny=True,
            )
            self.check(
                "search.runs.mixed_scope",
                actor,
                lambda c: c.search_runs([oid, fid]),
                lambda rows: (
                    orid in {r.info.run_id for r in rows}
                    and frid not in {r.info.run_id for r in rows}
                ),
                filter_or_deny=True,
            )
            self.check(
                "foreign.experiment.get",
                actor,
                lambda c: c.get_experiment(fid),
                denied=True,
            )
            self.check(
                "foreign.run.create", actor, lambda c: c.create_run(fid), denied=True
            )
            self.check("foreign.run.get", actor, lambda c: c.get_run(frid), denied=True)
            self.check(
                "foreign.run.mutate",
                actor,
                lambda c: c.set_tag(frid, "foreign_edit", "forbidden"),
                denied=True,
            )
            self.check(
                "foreign.run.metrics",
                actor,
                lambda c: c.get_metric_history(frid, "synthetic_metric"),
                denied=True,
            )
            self.check(
                "own.artifact.list",
                actor,
                lambda c: c.list_artifacts(orid, "rules"),
                lambda rows: "rules/policy.json" in {r.path for r in rows},
            )
            self.check(
                "foreign.artifact.list",
                actor,
                lambda c: c.list_artifacts(frid, "rules"),
                denied=True,
            )
            self.check(
                "own.artifact.download",
                actor,
                lambda c: self.download(c, orid, str(directory)),
                lambda digest: digest == PAYLOAD_HASH,
            )
            self.check(
                "foreign.artifact.download",
                actor,
                lambda c: self.download(c, frid, str(directory)),
                denied=True,
            )
            self.check(
                "own.artifact.known_uri_sdk",
                actor,
                lambda _: self.uri_download(own["artifact_uri"], str(directory)),
                lambda digest: digest == PAYLOAD_HASH,
            )
            with tempfile.TemporaryDirectory() as fresh:
                self.check(
                    "foreign.artifact.known_uri_sdk",
                    actor,
                    lambda _: self.uri_download(foreign["artifact_uri"], fresh),
                    denied=True,
                )
            self.check(
                "foreign.artifact.upload",
                actor,
                lambda c: c.log_artifact(frid, str(upload), "rules"),
                denied=True,
            )
            self.raw(
                "own.artifact.known_uri_http",
                actor,
                "GET",
                own["raw_path"],
                content=PAYLOAD,
            )
            self.raw(
                "foreign.artifact.known_uri_http",
                actor,
                "GET",
                foreign["raw_path"],
                expect_denied=True,
            )
            self.raw(
                "foreign.artifact.known_uri_upload_http",
                actor,
                "PUT",
                foreign["raw_path"] + ".probe",
                body=b"{}",
                expect_denied=True,
            )
            self.raw(
                "foreign.artifact.known_uri_list_http",
                actor,
                "GET",
                "/api/2.0/mlflow-artifacts/artifacts",
                params={"path": foreign["raw_list_path"]},
                expect_denied=True,
            )
            self.check(
                "list.registry.content",
                actor,
                self.all_models,
                lambda names: omodel in names and fmodel not in names,
            )
            self.check(
                "search.registry.foreign",
                actor,
                lambda c: c.search_registered_models(
                    filter_string=f"name = '{fmodel}'"
                ),
                lambda rows: len(rows) == 0,
                filter_or_deny=True,
            )
            self.check(
                "own.registry.get",
                actor,
                lambda c: c.get_registered_model(omodel),
                lambda r: r.name == omodel,
            )
            self.check(
                "own.registry.version_get",
                actor,
                lambda c: c.get_model_version(omodel, own["version"]),
                lambda r: r.run_id == orid,
            )
            self.check(
                "own.registry.alias_get",
                actor,
                lambda c: c.get_model_version_by_alias(omodel, "candidate"),
                lambda r: r.version == own["version"],
            )
            self.check(
                "own.registry.artifact_download",
                actor,
                lambda _: self.uri_download(
                    f"models:/{omodel}@candidate/policy.json", str(directory)
                ),
                lambda digest: digest == PAYLOAD_HASH,
            )
            self.check(
                "foreign.registry.get",
                actor,
                lambda c: c.get_registered_model(fmodel),
                denied=True,
            )
            self.check(
                "foreign.registry.version_get",
                actor,
                lambda c: c.get_model_version(fmodel, foreign["version"]),
                denied=True,
            )
            self.check(
                "foreign.registry.version_create",
                actor,
                lambda c: c.create_model_version(
                    fmodel, f"runs:/{orid}/rules", run_id=orid
                ),
                denied=True,
            )
            self.check(
                "foreign.registry.mutate",
                actor,
                lambda c: c.set_registered_model_tag(fmodel, "foreign", "forbidden"),
                denied=True,
            )
            self.check(
                "foreign.registry.alias_get",
                actor,
                lambda c: c.get_model_version_by_alias(fmodel, "candidate"),
                denied=True,
            )
            self.check(
                "foreign.registry.alias_set",
                actor,
                lambda c: c.set_registered_model_alias(
                    fmodel, "forbidden", foreign["version"]
                ),
                denied=True,
            )
            self.check(
                "foreign.registry.download_uri",
                actor,
                lambda c: c.get_model_version_download_uri(fmodel, foreign["version"]),
                denied=True,
            )
            with tempfile.TemporaryDirectory() as fresh:
                self.check(
                    "foreign.registry.artifact_download",
                    actor,
                    lambda _: self.uri_download(
                        f"models:/{fmodel}@candidate/policy.json", fresh
                    ),
                    denied=True,
                )
            self.check(
                "search.registry.versions_foreign",
                actor,
                lambda c: c.search_model_versions(f"name = '{fmodel}'"),
                lambda rows: len(rows) == 0,
                filter_or_deny=True,
            )
            self.raw(
                "anonymous.run.get",
                None,
                "GET",
                "/api/2.0/mlflow/runs/get",
                params={"run_id": orid},
                expect_denied=True,
            )
            self.raw(
                "anonymous.artifact.download",
                None,
                "GET",
                own["raw_path"],
                expect_denied=True,
            )
            self.raw(
                "anonymous.registry.get",
                None,
                "GET",
                "/api/2.0/mlflow/registered-models/get",
                params={"name": omodel},
                expect_denied=True,
            )

    def grant_revoke(self, directory: Path) -> None:
        target = self.resources["A"]
        experiment, run_id, model = (
            target["experiment_id"],
            target["run_id"],
            target["model_name"],
        )

        def permission(action: str, resource_type: str, resource_id: str):
            def operation(_: MlflowClient):
                auth = get_app_client("basic-auth", tracking_uri=URI)
                if action == "grant":
                    return auth.grant_user_permission(
                        "analyst_b", resource_type, resource_id, "READ"
                    )
                return auth.revoke_user_permission(
                    "analyst_b", resource_type, resource_id
                )

            return operation

        for resource_type, resource_id in (
            ("experiment", experiment),
            ("registered_model", model),
        ):
            self.check(
                f"grant.{resource_type}.READ",
                "admin",
                permission("grant", resource_type, resource_id),
            )
        self.check(
            "READ.run.get",
            "B",
            lambda c: c.get_run(run_id),
            lambda r: r.info.run_id == run_id,
        )
        self.check(
            "READ.run.search",
            "B",
            lambda c: c.search_runs([experiment]),
            lambda rows: run_id in {r.info.run_id for r in rows},
        )
        self.check(
            "READ.artifact.list",
            "B",
            lambda c: c.list_artifacts(run_id, "rules"),
            lambda rows: "rules/policy.json" in {r.path for r in rows},
        )
        self.check(
            "READ.artifact.download",
            "B",
            lambda c: self.download(c, run_id, str(directory)),
            lambda digest: digest == PAYLOAD_HASH,
        )
        self.raw(
            "READ.artifact.known_uri_http",
            "B",
            "GET",
            target["raw_path"],
            content=PAYLOAD,
        )
        self.check(
            "READ.run.write_denied",
            "B",
            lambda c: c.set_tag(run_id, "readonly_write", "forbidden"),
            denied=True,
        )
        self.check(
            "READ.run.create_denied",
            "B",
            lambda c: c.create_run(experiment),
            denied=True,
        )
        self.check(
            "READ.artifact.upload_denied",
            "B",
            lambda c: c.log_artifact(run_id, str(directory / "intruder.json"), "rules"),
            denied=True,
        )
        self.raw(
            "READ.artifact.known_uri_write_denied",
            "B",
            "PUT",
            target["raw_path"] + ".probe",
            body=b"{}",
            expect_denied=True,
        )
        self.check(
            "READ.registry.version_get",
            "B",
            lambda c: c.get_model_version(model, target["version"]),
            lambda r: r.version == target["version"],
        )
        self.check(
            "READ.registry.alias_get",
            "B",
            lambda c: c.get_model_version_by_alias(model, "candidate"),
            lambda r: r.version == target["version"],
        )
        self.check(
            "READ.registry.alias_write_denied",
            "B",
            lambda c: c.set_registered_model_alias(
                model, "readonly", target["version"]
            ),
            denied=True,
        )
        self.check(
            "READ.registry.version_create_denied",
            "B",
            lambda c: c.create_model_version(
                model, f"runs:/{run_id}/rules", run_id=run_id
            ),
            denied=True,
        )
        for resource_type, resource_id in (
            ("experiment", experiment),
            ("registered_model", model),
        ):
            self.check(
                f"revoke.{resource_type}",
                "admin",
                permission("revoke", resource_type, resource_id),
            )
        for retry in range(1, 3):
            self.check(
                f"revoked.run.get.retry{retry}",
                "B",
                lambda c: c.get_run(run_id),
                denied=True,
            )
            self.check(
                f"revoked.run.search.retry{retry}",
                "B",
                lambda c: c.search_runs([experiment]),
                lambda rows: len(rows) == 0,
                filter_or_deny=True,
            )
            self.check(
                f"revoked.artifact.list.retry{retry}",
                "B",
                lambda c: c.list_artifacts(run_id, "rules"),
                denied=True,
            )
            # A new empty directory prevents a pre-grant local download from proving access.
            with tempfile.TemporaryDirectory() as fresh:
                self.check(
                    f"revoked.artifact.download.retry{retry}",
                    "B",
                    lambda c: self.download(c, run_id, fresh),
                    denied=True,
                )
            with tempfile.TemporaryDirectory() as fresh:
                self.check(
                    f"revoked.artifact.known_uri_sdk.retry{retry}",
                    "B",
                    lambda _: self.uri_download(target["artifact_uri"], fresh),
                    denied=True,
                )
            self.raw(
                f"revoked.artifact.known_uri_http.retry{retry}",
                "B",
                "GET",
                target["raw_path"],
                expect_denied=True,
            )
            self.check(
                f"revoked.registry.get.retry{retry}",
                "B",
                lambda c: c.get_registered_model(model),
                denied=True,
            )
            self.check(
                f"revoked.registry.alias_get.retry{retry}",
                "B",
                lambda c: c.get_model_version_by_alias(model, "candidate"),
                denied=True,
            )

    def run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.create_resources(directory)
            self.own_and_foreign(directory)
            self.grant_revoke(directory)
        artifact_checks = [
            row
            for row in self.matrix
            if row["case"]
            in (
                "own.artifact.upload",
                "own.artifact.download",
                "own.registry.version_create",
                "own.registry.artifact_download",
            )
        ]
        self.record(
            "rule_without_fit.artifact_contract",
            "A",
            "PASS"
            if len(artifact_checks) == 8
            and all(row["status"] == "PASS" for row in artifact_checks)
            else "FAIL",
            limitation="Versioned JSON artifact only; no generic model execution contract.",
        )

    def report(self) -> dict[str, Any]:
        self.record(
            "audit.enterprise_qualification",
            "platform",
            "NOT TESTED",
            limitation="Independent durable authorization audit is not qualified; native service logs and this client-side test report do not provide Torii audit.",
        )
        counts = Counter(row["status"] for row in self.matrix)
        return {
            "schema_version": 1,
            "spec": "SPEC-0020",
            "mlflow_version": mlflow.__version__,
            "trial_id": self.prefix,
            "scope": "Experiments A/B with basic-auth; workspaces disabled; synthetic data only.",
            "verdict": "NO-GO",
            "api_subset": "FAIL" if counts["FAIL"] else "PASS",
            "reason": "Enterprise integration requires a qualified Torii authorization/audit boundary; evaluate every matrix failure before qualifying any adapter method.",
            "counts": dict(counts),
            "resources": self.resources,
            "artifact_sha256": PAYLOAD_HASH,
            "matrix": self.matrix,
        }


def main() -> int:
    logging.disable(logging.CRITICAL)
    os.environ["MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR"] = "false"
    os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] = "0"
    os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] = "15"
    os.environ.pop("MLFLOW_WORKSPACE", None)
    harness = None
    try:
        if (
            mlflow.__version__ != "3.14.0"
            or os.environ.get("MLFLOW_TRACKING_URI") != URI
        ):
            raise ValueError("version_or_endpoint")
        harness = Harness()
        harness.run()
        result = harness.report()
        code = 1 if result["counts"].get("FAIL", 0) else 0
    except Exception:  # noqa: BLE001 - safe CLI boundary, never prints exceptions
        if harness is not None:
            harness.record("harness.setup_or_prerequisite", "platform", "FAIL")
            harness.record("harness.remaining_scenarios", "platform", "NOT TESTED")
            result = harness.report()
        else:
            result = {
                "spec": "SPEC-0020",
                "verdict": "NO-GO",
                "matrix": [
                    {"case": "harness.setup", "actor": "platform", "status": "FAIL"}
                ],
                "reason": "Isolated endpoint, version, or secret setup failed.",
            }
        code = 2
    finally:
        if harness is not None:
            harness.session.close()
    print(
        "TORII_ACCESS_RESULT="
        + json.dumps(result, separators=(",", ":"), sort_keys=True)
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
