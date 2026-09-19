"""SPEC-0018 D03/D04/D06: real local training/tracking, not fake metrics."""

import json
import os
import subprocess
import sys

import joblib
import numpy as np
import pytest
from mlflow import MlflowClient
from sklearn.model_selection import train_test_split

from torii_demo.data import synthetic_data
from torii_demo.worker import run_job


def make_job(tmp_path, algorithm="linear", suffix="one"):
    directory = tmp_path / "runs" / suffix
    directory.mkdir(parents=True)
    return {
        "data": synthetic_data(),
        "definition": {
            "task": "regression",
            "algorithm": algorithm,
            "target": "target",
            "features": ["x1", "x2", "x3"],
            "alpha": 1,
            "seed": 42,
            "test_size": 0.25,
        },
        "run_dir": str(directory),
        "tracking_uri": "sqlite:///" + (tmp_path / "mlflow.db").as_posix(),
    }


def test_real_ridge_and_dummy_log_metrics_and_artifacts_without_ambient_tracking(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://must-not-be-used.invalid")
    monkeypatch.setenv("MLFLOW_WORKSPACE_STORE_URI", "https://must-not-be-used.invalid")
    monkeypatch.setenv("MLFLOW_ENABLE_ASYNC_LOGGING", "true")
    linear = make_job(tmp_path)
    result = run_job(linear)
    from pathlib import Path

    directory = Path(linear["run_dir"])
    assert result["metrics"]["r2"] > 0.8
    assert len(result["importance"]) == 3
    assert len(result["predictions"]) == 20
    assert result["train_rows"] + result["test_rows"] == linear["data"]["row_count"]
    assert json.loads((directory / "result.json").read_text()) == result
    client = MlflowClient(tracking_uri=linear["tracking_uri"])
    tracked = client.get_run(result["mlflow_run_id"])
    assert tracked.info.status == "FINISHED"
    assert tracked.data.metrics == result["metrics"]
    assert {entry.path for entry in client.list_artifacts(result["mlflow_run_id"])} == {
        "model.joblib",
        "environment.json",
        "result.json",
    }
    pipeline = joblib.load(directory / "model.joblib")
    values = np.array(
        [
            [row[name] for name in linear["definition"]["features"]]
            for row in linear["data"]["rows"]
        ],
        dtype=float,
    )
    train, _ = train_test_split(values, random_state=42, test_size=0.25)
    assert pipeline.named_steps["imputer"].statistics_ == pytest.approx(np.nanmedian(train, axis=0))
    assert pipeline.named_steps["scaler"].mean_ == pytest.approx(
        pipeline.named_steps["imputer"].transform(train).mean(axis=0)
    )
    baseline = run_job(make_job(tmp_path, "dummy", "two"))
    assert baseline["importance"] == []
    assert len({row["predicted"] for row in baseline["predictions"]}) == 1
    assert baseline["metrics"]["rmse"] > result["metrics"]["rmse"]
    repeated = run_job(make_job(tmp_path, "linear", "three"))
    assert repeated["metrics"] == result["metrics"]
    assert repeated["predictions"] == result["predictions"]
    assert repeated["importance"] == result["importance"]


def test_feature_present_only_in_holdout_cannot_fill_missing_training_values(tmp_path):
    job = make_job(tmp_path)
    train, holdout = train_test_split(
        np.arange(len(job["data"]["rows"])), test_size=0.25, random_state=42
    )
    for index in train:
        job["data"]["rows"][index]["x1"] = None
    assert all(job["data"]["rows"][index]["x1"] is not None for index in holdout)
    with pytest.raises(ValueError, match="training feature"):
        run_job(job)


@pytest.mark.parametrize(
    "change",
    ["missing_target", "target_feature", "text_feature", "empty_train", "few_rows", "remote"],
)
def test_invalid_training_or_remote_tracking_is_rejected(tmp_path, change):
    job = make_job(tmp_path)
    if change == "missing_target":
        job["data"]["rows"][0]["target"] = None
    elif change == "target_feature":
        job["definition"]["features"].append("target")
    elif change == "text_feature":
        job["data"]["rows"][0]["x1"] = "text"
    elif change == "empty_train":
        for row in job["data"]["rows"]:
            row["x1"] = None
    elif change == "few_rows":
        job["data"]["rows"] = job["data"]["rows"][:19]
    else:
        job["tracking_uri"] = "https://must-not-be-used.invalid"
    with pytest.raises(ValueError):
        run_job(job)


def test_tracking_failure_is_not_a_success(tmp_path, monkeypatch):
    job = make_job(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC_PROVIDER_FAILURE")

    monkeypatch.setattr(MlflowClient, "log_metric", fail)
    with pytest.raises(ValueError, match="tracking"):
        run_job(job)
    from pathlib import Path

    assert not (Path(job["run_dir"]) / "result.json").exists()


def test_cli_runs_real_job_and_failure_is_nonzero_without_raw_error(tmp_path):
    from pathlib import Path

    job = make_job(tmp_path)
    path = Path(job["run_dir"]) / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    env = os.environ | {"MLFLOW_TRACKING_URI": "https://must-not-be-used.invalid"}
    process = subprocess.run(
        [sys.executable, "-m", "torii_demo.worker", str(path)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert process.returncode == 0
    assert (path.parent / "result.json").exists()
    job["definition"]["algorithm"] = "SYNTHETIC_PRIVATE_BAD_ALGORITHM"
    path.write_text(json.dumps(job), encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, "-m", "torii_demo.worker", str(path)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert failed.returncode != 0
    assert "SYNTHETIC_PRIVATE_BAD_ALGORITHM" not in failed.stdout + failed.stderr
    assert "Traceback" not in failed.stdout + failed.stderr
