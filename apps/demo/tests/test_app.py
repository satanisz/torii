"""SPEC-0018 D01-D07: real local API and isolated persistence."""

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from torii_demo.app import create_app

HEADERS = {"X-Torii-Demo": "1", "Origin": "http://127.0.0.1:18440"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "demo"), base_url="http://127.0.0.1:18440") as client:
        yield client


def post(client, path, data=None):
    response = client.post("/demo-api" + path, json=data or {}, headers=HEADERS)
    assert response.status_code in (201, 202), response.text
    return response.json()


def test_project_dataset_versions_transform_and_export(client):
    project = post(client, "/projects", {"name": "Test konceptu"})
    data = post(client, f"/projects/{project['id']}/sample")
    version = data["versions"][0]
    definition = post(
        client,
        f"/projects/{project['id']}/transformations",
        {
            "name": "Bez duplikatów",
            "input_version_id": version["id"],
            "operation": "drop_duplicates",
        },
    )
    output = post(client, f"/transformations/{definition['versions'][0]['id']}/execute")
    assert output["id"] != data["id"]
    assert output["versions"][0]["definition"]["input_version_id"] == version["id"]
    updated = post(
        client,
        f"/projects/{project['id']}/datasets",
        {
            "name": "Nowa wersja",
            "object_id": data["id"],
            "format": "csv",
            "content_base64": base64.b64encode(b"x,y\n1,2\n3,4\n").decode(),
        },
    )
    assert len(updated["versions"]) == 2
    assert updated["versions"][0] == version
    exported = client.get(f"/demo-api/projects/{project['id']}/export").json()
    text = json.dumps(exported)
    assert all(
        f'"{key}"' not in text for key in ("payload", "preview", "predictions", "importance")
    )


def test_host_origin_and_header_fail_closed(client):
    assert client.get("/demo-api/state", headers={"host": "evil.invalid"}).status_code == 400
    assert client.post("/demo-api/projects", json={"name": "x"}).status_code == 403
    assert (
        client.post(
            "/demo-api/projects",
            json={"name": "x"},
            headers={"X-Torii-Demo": "1", "Origin": "https://evil.invalid"},
        ).status_code
        == 403
    )
    assert client.get("/demo-api/state").headers["cache-control"] == "no-store"


def test_invalid_upload_is_not_reflected_and_oversized_body_rejected(client):
    project = post(client, "/projects", {"name": "CSV"})
    marker = "SYNTHETIC_PRIVATE_DATA"
    response = client.post(
        f"/demo-api/projects/{project['id']}/datasets",
        headers=HEADERS,
        json={"content_base64": marker},
    )
    assert response.status_code == 422 and marker not in response.text
    response = client.post(
        "/demo-api/projects", content=b"x" * (8 * 1024 * 1024 + 1), headers=HEADERS
    )
    assert response.status_code == 413


def test_cross_project_references_refused(client):
    first = post(client, "/projects", {"name": "A"})
    second = post(client, "/projects", {"name": "B"})
    data = post(client, f"/projects/{first['id']}/sample")
    response = client.post(
        f"/demo-api/projects/{second['id']}/transformations",
        headers=HEADERS,
        json={
            "name": "x",
            "input_version_id": data["versions"][0]["id"],
            "operation": "drop_missing",
        },
    )
    assert response.status_code == 404


def test_persistence_across_app_restart(tmp_path):
    root = tmp_path / "restart"
    with TestClient(create_app(root), base_url="http://127.0.0.1:18440") as first:
        project = post(first, "/projects", {"name": "Trwały"})
        post(first, f"/projects/{project['id']}/sample")
        state = first.get("/demo-api/state").json()
    with TestClient(create_app(root), base_url="http://127.0.0.1:18440") as second:
        assert second.get("/demo-api/state").json() == state


def test_real_worker_mlflow_and_analysis(client):
    project = post(client, "/projects", {"name": "Prawdziwe ML"})
    dataset = post(client, f"/projects/{project['id']}/sample")
    version = dataset["versions"][0]
    columns = version["summary"]["columns"]
    model = post(
        client,
        f"/projects/{project['id']}/models",
        {
            "name": "Ridge",
            "task": "regression",
            "algorithm": "linear",
            "target": columns[-1],
            "features": columns[:-1],
            "alpha": 1,
        },
    )
    run = post(
        client,
        f"/projects/{project['id']}/runs",
        {
            "model_version_id": model["versions"][0]["id"],
            "dataset_version_id": version["id"],
        },
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = client.get("/demo-api/state").json()
        current = next(item for item in state["runs"] if item["id"] == run["id"])
        if current["status"] in ("failed", "succeeded"):
            break
        time.sleep(0.2)
    assert current["status"] == "succeeded", current
    assert current["result"]["mlflow_run_id"]
    assert set(current["result"]["metrics"]) == {"mae", "rmse", "r2"}
    assert any(item["kind"] == "analysis" for item in state["objects"])
    artifact = client.get(f"/demo-api/runs/{run['id']}/artifacts/model.joblib")
    assert artifact.status_code == 200 and len(artifact.content) > 100
    assert client.get(f"/demo-api/runs/{run['id']}/artifacts/job.json").status_code == 404


def test_formula_export_sanitizes_headers_and_text_but_preserves_numeric(client):
    project = post(client, "/projects", {"name": "CSV formuły"})
    csv = b"=heading,text,number\n=1+1,@cmd,-12\n"
    data = post(
        client,
        f"/projects/{project['id']}/datasets",
        {"name": "Formuły", "format": "csv", "content_base64": base64.b64encode(csv).decode()},
    )
    text = client.get(f"/demo-api/datasets/{data['versions'][0]['id']}/csv").content.decode(
        "utf-8-sig"
    )
    assert "'=heading" in text and "'=1+1" in text and "'@cmd" in text
    assert ",-12.0" in text


def test_failed_run_is_terminal_and_recovery_only_changes_pending(tmp_path):
    from torii_demo.store import Store

    store = Store(tmp_path / "recover")
    project = store.create_project("Restart")
    model = store.create_object(
        project["id"], "model", "m", {"target": "y", "seed": 42, "test_size": 0.25}
    )
    dataset = store.create_object(
        project["id"],
        "dataset",
        "d",
        {},
        {"columns": ["x"], "rows": [], "row_count": 0, "profile": []},
    )
    run = store.create_run(project["id"], model["versions"][0]["id"], dataset["versions"][0]["id"])
    store.recover()
    assert store.run(run["id"])["status"] == "failed"


def test_unrelated_directory_refused(tmp_path):
    (tmp_path / "unrelated.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(RuntimeError, match="empty directory"):
        create_app(tmp_path)
    assert (tmp_path / "unrelated.txt").read_text() == "preserve"


def test_http_obs_text_header_does_not_crash_guard():
    import asyncio

    from torii_demo.app import DemoGuard

    reached = []

    async def downstream(scope, receive, send):
        reached.append(True)

    asyncio.run(
        DemoGuard(downstream)(
            {
                "type": "http",
                "method": "GET",
                "headers": [(b"host", b"127.0.0.1:18440"), (b"x-note", b"\xff")],
            },
            None,
            None,
        )
    )
    assert reached == [True]
