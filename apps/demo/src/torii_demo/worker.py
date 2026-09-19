"""SPEC-0018 D03/D04: fixed regression worker, never user-supplied Python.

Only server-created jobs with explicit local SQLite and local artifact paths.
This subprocess is resource separation, not a sandbox or enterprise executor.
"""

import json
import math
import os
import platform
import sys
from contextlib import suppress
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from torii_demo.data import snapshot


def _definition(data: dict[str, Any], definition: dict[str, Any]) -> tuple[list[str], str]:
    features, target = definition.get("features"), definition.get("target")
    alpha = definition.get("alpha", 1)
    if (
        definition.get("task") != "regression"
        or definition.get("algorithm") not in ("linear", "dummy")
        or type(features) is not list
        or not features
        or any(type(name) is not str or name not in data["columns"] for name in features)
        or len(set(features)) != len(features)
        or target not in data["columns"]
        or target in features
        or type(alpha) not in (int, float)
        or not math.isfinite(alpha)
        or not 0 <= alpha <= 100
        or type(definition.get("seed", 42)) is not int
        or definition.get("seed", 42) != 42
        or type(definition.get("test_size", 0.25)) is not float
        or definition.get("test_size", 0.25) != 0.25
    ):
        raise ValueError("Invalid regression definition or selected columns")
    if len(data["rows"]) < 20:
        raise ValueError("Training requires at least 20 rows")
    for row in data["rows"]:
        if type(row[target]) not in (int, float):
            raise ValueError("Target must be numeric and have no missing values")
        if any(row[name] is not None and type(row[name]) not in (int, float) for name in features):
            raise ValueError("Features must be numeric")
    return features, target


def _paths(job: dict[str, Any]) -> tuple[Path, str, Path]:
    directory = Path(job["run_dir"])
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("Invalid internal run directory")
    directory = directory.resolve()
    tracking = job.get("tracking_uri")
    if type(tracking) is not str or not tracking.startswith("sqlite:///"):
        raise ValueError("Tracking requires an explicit local SQLite database")
    database = Path(tracking[len("sqlite:///") :])
    if (
        not database.is_absolute()
        or any(char in tracking for char in ("?", "#", "\x00"))
        or database.is_symlink()
        or str(database).startswith(("\\\\", "//"))
        or not database.resolve().is_relative_to(directory.parent.parent)
    ):
        raise ValueError("Invalid local tracking database")
    artifacts = directory.parent / "mlflow-artifacts"
    if artifacts.is_symlink() or artifacts.resolve().parent != directory.parent:
        raise ValueError("Invalid local artifact directory")
    for name in ("model.joblib", "environment.json", "result.json"):
        if (directory / name).exists():
            raise ValueError("Run artifacts already exist")
    return directory, tracking, artifacts


def _write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _local_tracking_client(tracking: str) -> Any:
    # This module runs in a dedicated demo process. Set before the lazy import,
    # including direct CLI runs that did not inherit the launcher's safe env.
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    from mlflow import MlflowClient

    return MlflowClient(tracking_uri=tracking, registry_uri=tracking, workspace_store_uri=tracking)


def run_job(job: dict[str, Any]) -> dict[str, Any]:
    directory, tracking, artifacts = _paths(job)
    data = snapshot(job["data"]["columns"], job["data"]["rows"])
    definition = job["definition"]
    features, target = _definition(data, definition)
    x = np.array([[row[name] for name in features] for row in data["rows"]], dtype=float)
    y = np.array([row[target] for row in data["rows"]], dtype=float)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.25, random_state=42)
    if np.isnan(x_train).all(axis=0).any():
        raise ValueError("A training feature contains only missing values")
    algorithm = definition["algorithm"]
    estimator = (
        Ridge(alpha=definition.get("alpha", 1))
        if algorithm == "linear"
        else DummyRegressor(strategy="mean")
    )
    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", estimator),
        ]
    )
    try:
        pipeline.fit(x_train, y_train)
        predicted = pipeline.predict(x_test)
        metrics = {
            "mae": float(mean_absolute_error(y_test, predicted)),
            "rmse": float(root_mean_squared_error(y_test, predicted)),
            "r2": float(r2_score(y_test, predicted)),
        }
        if (
            not all(math.isfinite(value) for value in metrics.values())
            or not np.isfinite(predicted).all()
        ):
            raise ValueError("Non-finite model output")
    except (ValueError, FloatingPointError, OverflowError):
        raise ValueError("Training failed; check numeric values and target") from None
    environment = {
        "python": platform.python_version(),
        "platform": platform.system(),
        **{name: version(name) for name in ("scikit-learn", "numpy", "mlflow-skinny", "joblib")},
    }
    importance = (
        [
            {"feature": name, "value": float(value)}
            for name, value in zip(features, pipeline.named_steps["model"].coef_, strict=True)
        ]
        if algorithm == "linear"
        else []
    )
    if not all(math.isfinite(item["value"]) for item in importance):
        raise ValueError("Training produced non-finite coefficients")
    result: dict[str, Any] = {
        "algorithm": algorithm,
        "metrics": metrics,
        "importance": importance,
        "predictions": [
            {"actual": float(actual), "predicted": float(estimate)}
            for actual, estimate in list(zip(y_test, predicted, strict=True))[:20]
        ],
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "environment": environment,
    }
    client = None
    run_id = None
    try:
        # Never use fluent/ambient tracking defaults or arbitrary artifact plugins.
        client = _local_tracking_client(tracking)
        artifacts.mkdir(exist_ok=True)
        artifact_uri = artifacts.as_uri()
        experiment = client.get_experiment_by_name("Torii local demo")
        if experiment is None:
            experiment_id = client.create_experiment(
                "Torii local demo", artifact_location=artifact_uri
            )
        else:
            if experiment.artifact_location != artifact_uri:
                raise ValueError("Unexpected experiment artifact location")
            experiment_id = experiment.experiment_id
        run = client.create_run(
            experiment_id, tags={"torii.mode": "local-demo", "mlflow.runName": algorithm}
        )
        run_id = run.info.run_id
        if not run.info.artifact_uri.startswith(artifact_uri + "/"):
            raise ValueError("Unexpected run artifact location")
        result["mlflow_run_id"] = run_id
        for name, value in {
            "algorithm": algorithm,
            "target": target,
            "features": json.dumps(features),
            "alpha": definition.get("alpha", 1),
            "seed": 42,
            "test_size": 0.25,
        }.items():
            client.log_param(run_id, name, value, synchronous=True)
        for name, value in metrics.items():
            client.log_metric(run_id, name, value, synchronous=True)
        joblib.dump(pipeline, directory / "model.joblib")
        _write_json(directory / "environment.json", environment)
        # Publish the success result only after all tracking calls have succeeded.
        staged = directory / "result.pending.json"
        _write_json(staged, result)
        client.log_artifact(run_id, str(directory / "model.joblib"))
        client.log_artifact(run_id, str(directory / "environment.json"))
        # MLflow preserves source filenames: stage result in a private subdirectory.
        export = directory / "tracking-result"
        export.mkdir()
        _write_json(export / "result.json", result)
        client.log_artifact(run_id, str(export / "result.json"))
        client.set_terminated(run_id, status="FINISHED")
        staged.rename(directory / "result.json")
        return result
    except Exception:
        if client is not None and run_id is not None:
            with suppress(Exception):
                client.set_terminated(run_id, status="FAILED")
        raise ValueError("Local MLflow tracking or artifact storage failed") from None


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("One internal job file is required")
        path = Path(sys.argv[1]).resolve(strict=True)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Internal job is too large")
        job = json.loads(path.read_text(encoding="utf-8"))
        if Path(job["run_dir"]).resolve() != path.parent:
            raise ValueError("Internal job directory mismatch")
        run_job(job)
        return 0
    except Exception:
        print(
            "Local demo training failed; check dataset, model and local tracking.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
