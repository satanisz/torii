"""SPEC-0019 F01/F03/F05: finance snapshots, real subprocess, lifecycle and guards."""

import json
import subprocess
import threading
import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from torii_demo.app import create_app
from torii_demo.finance_api import FinanceStore, register_finance
from torii_demo.finance_engine import build_manifest, calculate, synthetic_snapshot
from torii_demo.store import Store

BASE = "http://127.0.0.1:18440"
HEADERS = {"X-Torii-Demo": "1", "Origin": BASE}
MARKER = "PRIVATE_TEST_FAILURE_DO_NOT_REFLECT"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "demo"), base_url=BASE, headers=HEADERS) as value:
        yield value


def project(client, name="Finanse"):
    response = client.post("/demo-api/projects", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def runs_path(project_id):
    return f"/demo-api/projects/{project_id}/finance/runs"


def wait_terminal(client, project_id, run_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"{runs_path(project_id)}/{run_id}")
        assert response.status_code == 200, response.text
        current = response.json()
        if current["status"] in ("succeeded", "failed"):
            return current
        threading.Event().wait(0.01)
    pytest.fail("Finance worker did not publish a terminal state")


def submit_when_ready(client, project_id, body=None):
    deadline = time.monotonic() + 5
    while True:
        response = client.post(runs_path(project_id), json=body or {})
        if response.status_code != 409 or time.monotonic() >= deadline:
            assert response.status_code == 202, response.text
            return response.json()
        threading.Event().wait(0.01)


@pytest.mark.parametrize("inject_issues", [False, True])
def test_real_finance_subprocess_export_and_project_references(client, inject_issues):
    own, other = project(client), project(client, "Other")
    sample = client.get("/demo-api/finance/sample")
    assert sample.status_code == 200
    assert sample.json() == synthetic_snapshot()
    started = submit_when_ready(client, own, {"shock_bps": -100, "inject_issues": inject_issues})
    assert started["snapshot"] == synthetic_snapshot(inject_issues=inject_issues)
    assert started["scenario"] == {
        "shock_bps": -100,
        "deposit_beta": 0.35,
        "inject_issues": inject_issues,
    }
    assert started["manifest"] == build_manifest(started["snapshot"], started["scenario"])
    current = wait_terminal(client, own, started["id"])
    assert current["status"] == "succeeded", current
    assert current["result"]["quality_status"] == ("blocked" if inject_issues else "passed")
    assert len(current["result"]["monthly"]) == 12
    for key in ("snapshot", "scenario", "manifest", "created_at"):
        assert current[key] == started[key]
    exported = client.get(f"{runs_path(own)}/{started['id']}/export")
    assert exported.status_code == 200
    assert exported.json() == current
    assert "attachment" in exported.headers["content-disposition"]
    assert client.get(runs_path(own)).json() == [current]
    assert client.get(runs_path(other)).json() == []
    for suffix in ("", "/export"):
        assert client.get(f"{runs_path(other)}/{started['id']}{suffix}").status_code == 404
    assert client.get(f"{runs_path(own)}/{uuid4()}").status_code == 404
    assert client.get(runs_path(str(uuid4()))).status_code == 404
    assert client.post(runs_path(str(uuid4())), json={}).status_code == 404
    # The existing ML contract stays separate from the financial history.
    assert client.get("/demo-api/state").json()["runs"] == []


def test_success_and_failed_envelopes_survive_restart(tmp_path):
    root = tmp_path / "persistent"
    with TestClient(create_app(root), base_url=BASE, headers=HEADERS) as first:
        own = project(first)
        started = submit_when_ready(first, own)
        completed = wait_terminal(first, own, started["id"])
        assert completed["status"] == "succeeded"
        store = first.app.state.finance_store
        queued = store.create_run(
            own, completed["snapshot"], completed["scenario"], completed["manifest"]
        )
    with TestClient(create_app(root), base_url=BASE, headers=HEADERS) as second:
        assert second.get(f"{runs_path(own)}/{completed['id']}").json() == completed
        failed = second.get(f"{runs_path(own)}/{queued['id']}").json()
        assert failed["status"] == "failed" and failed["result"] is None
        assert failed["error"]
        for key in ("snapshot", "scenario", "manifest", "created_at"):
            assert failed[key] == queued[key]
        assert second.get(f"{runs_path(own)}/{queued['id']}/export").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"shock_bps": 301},
        {"shock_bps": -301},
        {"shock_bps": 0.5},
        {"shock_bps": True},
        {"deposit_beta": -0.01},
        {"deposit_beta": 1.01},
        {"deposit_beta": True},
        {"inject_issues": "false"},
        {"untrusted": MARKER},
        {"shock_bps": "100"},
    ],
)
def test_invalid_parameters_fail_before_persistence(client, body):
    own = project(client)
    response = client.post(runs_path(own), json=body)
    assert response.status_code == 422
    assert MARKER not in response.text
    assert client.get(runs_path(own)).json() == []


def test_nonfinite_and_demo_guard_are_preserved(client):
    own = project(client)
    response = client.post(
        runs_path(own),
        content='{"deposit_beta": NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert client.get(runs_path(own)).json() == []
    assert client.post(runs_path(own), json={}, headers={"X-Torii-Demo": "0"}).status_code == 403
    assert (
        client.post(runs_path(own), json={}, headers={"Origin": "https://evil.invalid"}).status_code
        == 403
    )
    assert (
        client.get("/demo-api/finance/sample", headers={"Host": "evil.invalid"}).status_code == 400
    )
    assert client.get("/demo-api/finance/sample").headers["cache-control"] == "no-store"


def create_ml_body(client, own):
    dataset = client.post(f"/demo-api/projects/{own}/sample", json={}).json()
    model = client.post(
        f"/demo-api/projects/{own}/models",
        json={
            "name": "Baseline",
            "task": "regression",
            "algorithm": "dummy",
            "target": "target",
            "features": ["x1"],
        },
    ).json()
    return {
        "dataset_version_id": dataset["versions"][0]["id"],
        "model_version_id": model["versions"][0]["id"],
    }


@pytest.mark.parametrize("first_kind", ["finance", "ml"])
def test_ml_and_finance_use_the_same_gate(client, monkeypatch, first_kind):
    own = project(client)
    ml_body = create_ml_body(client, own)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def blocked_worker(command, **kwargs):
        calls.append((command, kwargs))
        entered.set()
        assert release.wait(5), "Test must release worker"
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr("torii_demo.finance_api.subprocess.run", blocked_worker)
    finance_path, ml_path = runs_path(own), f"/demo-api/projects/{own}/runs"
    first_path, first_body = (finance_path, {}) if first_kind == "finance" else (ml_path, ml_body)
    other_path, other_body = (ml_path, ml_body) if first_kind == "finance" else (finance_path, {})
    try:
        first = client.post(first_path, json=first_body)
        assert first.status_code == 202
        assert entered.wait(5)
        assert client.get("/demo-api/state").json()["execution_active"] is True
        assert client.post(other_path, json=other_body).status_code == 409
        assert client.post(first_path, json=first_body).status_code == 409
        assert len(calls) == 1
        if first_kind == "finance":
            current = client.get(f"{finance_path}/{first.json()['id']}").json()
            assert current["status"] == "running" and current["result"] is None
            assert current["snapshot"] and current["manifest"]
            assert client.get(f"{finance_path}/{current['id']}/export").status_code == 404
            assert calls[0][1]["timeout"] == 30
            assert calls[0][1]["stdout"] == calls[0][1]["stderr"] == subprocess.DEVNULL
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while client.get("/demo-api/state").json()["execution_active"]:
        assert time.monotonic() < deadline, "Completed worker must release its execution gate"
        threading.Event().wait(0.01)


@pytest.mark.parametrize(
    "failure", ["timeout", "exit", "json", "manifest", "snapshot", "body", "totals", "months"]
)
def test_worker_failures_are_safe_terminal_and_release_gate(client, monkeypatch, failure):
    own = project(client)
    monkeypatch.setenv("FINANCE_TEST_SECRET", MARKER)

    def broken_worker(command, **kwargs):
        assert "FINANCE_TEST_SECRET" not in kwargs["env"]
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 30, output=MARKER, stderr=MARKER)
        if failure == "exit":
            return subprocess.CompletedProcess(command, 1)
        from pathlib import Path

        job = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        output = Path(job["output_path"])
        if failure == "json":
            output.write_text(MARKER, encoding="utf-8")
        else:
            # Corrupt complete output so envelope and structural checks are both
            # exercised independently. Recalculation exists only in this test.
            report = calculate(job["snapshot"], job["scenario"])
            if failure == "manifest":
                report["manifest"]["engine_sha256"] = "0" * 64
            elif failure == "snapshot":
                report["snapshot"]["currency"] = "EUR"
            elif failure == "body":
                report = {key: report[key] for key in ("snapshot", "scenario", "manifest")}
            elif failure == "totals":
                del report["totals"]["nii_base_pln"]
            else:
                report["monthly"].pop()
            output.write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("torii_demo.finance_api.subprocess.run", broken_worker)
    first = submit_when_ready(client, own)
    failed = wait_terminal(client, own, first["id"])
    assert failed["status"] == "failed" and failed["result"] is None
    assert failed["error"] and MARKER not in failed["error"]
    assert "Traceback" not in failed["error"]
    assert failed["manifest"] == first["manifest"]
    second = submit_when_ready(client, own)
    assert second["id"] != first["id"]
    assert wait_terminal(client, own, second["id"])["status"] == "failed"


def test_submit_failure_is_persisted_and_unlocks(tmp_path):
    parent = Store(tmp_path / "submission")
    own = parent.create_project("Submit failure")["id"]
    gate = threading.Lock()

    class BrokenPool:
        def submit(self, *args):
            raise RuntimeError(MARKER)

    app = FastAPI()
    register_finance(app, parent, gate, BrokenPool())
    with TestClient(app) as client:
        response = client.post(runs_path(own), json={})
        assert response.status_code == 202
        failed = response.json()
        assert failed["status"] == "failed" and failed["result"] is None
        assert failed["snapshot"] and failed["manifest"]
        assert MARKER not in failed["error"]
        assert not gate.locked()
        assert client.get(runs_path(own)).json() == [failed]


def test_store_recovery_preserves_terminal_rows_and_immutable_copies(tmp_path):
    parent = Store(tmp_path / "store")
    own = parent.create_project("Recovery")["id"]
    store = FinanceStore(parent)
    snapshot = synthetic_snapshot()
    scenario = {"shock_bps": 0, "deposit_beta": 0.35, "inject_issues": False}
    manifest = build_manifest(snapshot, scenario)
    queued = store.create_run(own, snapshot, scenario, manifest)
    running = store.create_run(own, snapshot, scenario, manifest)
    assert store.start(running["id"])
    failed = store.create_run(own, snapshot, scenario, manifest)
    assert store.finish(failed["id"], error="Original failure")
    snapshot["currency"] = "EUR"
    scenario["shock_bps"] = 100
    manifest["engine_sha256"] = "changed"
    store.recover()
    reopened = FinanceStore(parent)
    for run in (queued, running):
        current = reopened.run(own, run["id"])
        assert current["status"] == "failed" and current["result"] is None
        for key in ("snapshot", "scenario", "manifest", "created_at"):
            assert current[key] == run[key]
    preserved = reopened.run(own, failed["id"])
    assert preserved["error"] == "Original failure"
    assert not reopened.start(failed["id"])
    assert not reopened.finish(failed["id"], error="Replacement failure")
    assert reopened.run(own, failed["id"]) == preserved
