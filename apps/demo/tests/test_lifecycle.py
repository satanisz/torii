"""SPEC-0018 D01/D03/D06: API lifecycle guards with controlled worker failures.

The subprocess is deliberately mocked here; real training/MLflow is tested in
test_worker.py. Each API instance owns only a fresh pytest temporary directory.
"""

import base64
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

from torii_demo.app import create_app
from torii_demo.data import synthetic_data
from torii_demo.store import Store

BASE = "http://127.0.0.1:18440"
HEADERS = {"X-Torii-Demo": "1", "Origin": BASE}
MARKER = "SYNTHETIC_PRIVATE_WORKER_FAILURE"


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "demo"), base_url=BASE, headers=HEADERS) as value:
        yield value


def make_project(client, name):
    created = client.post("/demo-api/projects", json={"name": name})
    assert created.status_code == 201
    project_id = created.json()["id"]
    sample = client.post(f"/demo-api/projects/{project_id}/sample", json={})
    model = client.post(
        f"/demo-api/projects/{project_id}/models",
        json={
            "name": "Ridge",
            "task": "regression",
            "algorithm": "linear",
            "target": "target",
            "features": ["x1", "x2", "x3"],
        },
    )
    assert sample.status_code == model.status_code == 201
    return project_id, sample.json(), model.json()


def run_body(dataset, model):
    return {
        "dataset_version_id": dataset["versions"][-1]["id"],
        "model_version_id": model["versions"][-1]["id"],
    }


def wait_failed(client, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        runs = client.get("/demo-api/state").json()["runs"]
        result = next(run for run in runs if run["id"] == run_id)
        if result["status"] == "failed":
            return result
        assert result["status"] in ("queued", "running")
        threading.Event().wait(0.01)
    pytest.fail("Worker did not publish a terminal state within the bounded test wait")


def test_busy_worker_refuses_second_run_without_creating_it(client, monkeypatch):
    project, dataset, model = make_project(client, "Busy demo")
    entered, release = threading.Event(), threading.Event()
    calls = []

    def blocked_worker(command, **kwargs):
        calls.append((command, kwargs))
        entered.set()
        if not release.wait(5):
            raise AssertionError("Test must release its worker")
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr("torii_demo.app.subprocess.run", blocked_worker)
    try:
        first = client.post(f"/demo-api/projects/{project}/runs", json=run_body(dataset, model))
        assert first.status_code == 202
        assert entered.wait(5)
        second = client.post(f"/demo-api/projects/{project}/runs", json=run_body(dataset, model))
        assert second.status_code == 409
        runs = client.get("/demo-api/state").json()["runs"]
        assert len(runs) == 1 and runs[0]["status"] == "running"
        assert len(calls) == 1
        assert calls[0][1]["timeout"] == 120
        assert calls[0][1]["stdout"] == subprocess.DEVNULL
        assert calls[0][1]["stderr"] == subprocess.DEVNULL
    finally:
        release.set()
    failed = wait_failed(client, first.json()["id"])
    assert failed["result"] is None


def test_timeout_is_safe_failure_and_releases_the_run_gate(client, monkeypatch):
    project, dataset, model = make_project(client, "Timeout demo")
    calls = []

    def timed_out(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=MARKER, stderr=MARKER)

    monkeypatch.setattr("torii_demo.app.subprocess.run", timed_out)
    first = client.post(f"/demo-api/projects/{project}/runs", json=run_body(dataset, model))
    assert first.status_code == 202
    failed = wait_failed(client, first.json()["id"])
    assert failed["result"] is None
    assert failed["error"] and MARKER not in failed["error"]
    assert "Traceback" not in failed["error"]
    # The terminal update precedes finally/release by a few instructions. Test
    # eventual availability, not thread scheduling between those instructions.
    deadline = time.monotonic() + 5
    while True:
        next_run = client.post(f"/demo-api/projects/{project}/runs", json=run_body(dataset, model))
        if next_run.status_code != 409 or time.monotonic() >= deadline:
            break
        threading.Event().wait(0.01)
    assert next_run.status_code == 202
    assert next_run.json()["id"] != first.json()["id"]
    wait_failed(client, next_run.json()["id"])
    assert len(calls) == 2
    state = client.get("/demo-api/state").json()
    assert not any(obj["kind"] == "analysis" for obj in state["objects"])
    artifact = client.get(f"/demo-api/runs/{first.json()['id']}/artifacts/result.json")
    assert artifact.status_code == 404


@pytest.mark.parametrize("foreign_kind", ["dataset", "model"])
def test_run_cannot_reference_another_projects_version(client, monkeypatch, foreign_kind):
    project, own_dataset, own_model = make_project(client, "Project A")
    _, foreign_dataset, foreign_model = make_project(client, "Project B")
    calls = []

    def must_not_start(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Cross-project request must not reach a worker")

    monkeypatch.setattr("torii_demo.app.subprocess.run", must_not_start)
    body = run_body(
        foreign_dataset if foreign_kind == "dataset" else own_dataset,
        foreign_model if foreign_kind == "model" else own_model,
    )
    response = client.post(f"/demo-api/projects/{project}/runs", json=body)
    assert response.status_code == 404
    assert client.get("/demo-api/state").json()["runs"] == []
    assert calls == []


def test_dataset_update_cannot_append_version_in_another_project(client):
    project, _, _ = make_project(client, "Project A")
    _, foreign_dataset, _ = make_project(client, "Project B")
    before = client.get("/demo-api/state").json()
    response = client.post(
        f"/demo-api/projects/{project}/datasets",
        json={
            "name": "Forbidden update",
            "format": "csv",
            "content_base64": base64.b64encode(b"x,target\n1,2\n").decode(),
            "object_id": foreign_dataset["id"],
        },
    )
    assert response.status_code == 404
    assert client.get("/demo-api/state").json() == before


def test_target_in_features_is_rejected_before_model_persistence(client):
    project = client.post("/demo-api/projects", json={"name": "Invalid model"}).json()["id"]
    response = client.post(
        f"/demo-api/projects/{project}/models",
        json={
            "name": MARKER,
            "task": "regression",
            "algorithm": "linear",
            "target": "target",
            "features": ["x1", "target"],
        },
    )
    assert response.status_code == 422
    assert MARKER not in response.text
    assert client.get("/demo-api/state").json()["objects"] == []


def test_state_snapshot_blocks_completion_until_objects_and_runs_are_assembled(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "snapshot")
    project = store.create_project("Coherent snapshot")["id"]
    dataset = store.create_object(
        project, "dataset", "Synthetic", {"source": "synthetic"}, synthetic_data()
    )
    model = store.create_object(
        project,
        "model",
        "Ridge",
        {"target": "target", "seed": 42, "test_size": 0.25},
    )
    dataset_version = dataset["versions"][0]["id"]
    model_version = model["versions"][0]["id"]
    run = store.create_run(project, model_version, dataset_version)
    store.update_run(run["id"], "running")
    reading, release_reader = threading.Event(), threading.Event()
    writer_probe, writer_done = threading.Event(), threading.Event()
    reader_done = threading.Event()
    blocked = []
    failures = []
    snapshots = []
    original_lock, original_object = store._lock, store.object

    class ObservedLock:
        """Observe the real RLock without adding a second synchronization lock."""

        def __enter__(self):
            if threading.current_thread() is writer and not writer_probe.is_set():
                acquired = original_lock.acquire(blocking=False)
                blocked.append(not acquired)
                writer_probe.set()
                if not acquired:
                    original_lock.acquire()
            else:
                original_lock.acquire()
            return self

        def __exit__(self, *args):
            original_lock.release()

    def paused_object(object_id):
        # state() already captured the object/run ID lists, the original race's
        # exact boundary. Only its first object read is paused, never the writer.
        if threading.current_thread() is reader and not reading.is_set():
            reading.set()
            if not release_reader.wait(5):
                raise AssertionError("Test must release its snapshot reader")
        return original_object(object_id)

    def read_snapshot():
        try:
            snapshots.append(store.state())
        except Exception as error:
            failures.append(error)
        finally:
            reader_done.set()

    def complete_run():
        try:
            store.create_object(
                project,
                "analysis",
                "Completed analysis",
                {
                    "run_id": run["id"],
                    "input_version_id": dataset_version,
                    "model_version_id": model_version,
                },
            )
            store.update_run(run["id"], "succeeded", {"metrics": {"mae": 0.5}})
        except Exception as error:
            failures.append(error)
        finally:
            writer_done.set()

    reader = threading.Thread(target=read_snapshot, name="snapshot-reader")
    writer = threading.Thread(target=complete_run, name="snapshot-writer")
    monkeypatch.setattr(store, "_lock", ObservedLock())
    monkeypatch.setattr(store, "object", paused_object)
    reader.start()
    try:
        assert reading.wait(5)
        writer.start()
        assert writer_probe.wait(5)
        # The writer tried the actual lock, not merely a scheduling delay.
        assert blocked == [True]
        assert not writer_done.is_set()
        assert not reader_done.is_set()
    finally:
        release_reader.set()
        reader.join(timeout=5)
        if writer.ident is not None:
            writer.join(timeout=5)
    assert not reader.is_alive() and not writer.is_alive()
    assert failures == []
    assert reader_done.is_set() and writer_done.is_set()
    first = snapshots[0]
    assert first["runs"][0]["status"] == "running"
    assert not any(obj["kind"] == "analysis" for obj in first["objects"])
    completed = store.state()
    assert completed["runs"][0]["status"] == "succeeded"
    analysis = next(obj for obj in completed["objects"] if obj["kind"] == "analysis")
    assert analysis["versions"][0]["definition"]["run_id"] == run["id"]
