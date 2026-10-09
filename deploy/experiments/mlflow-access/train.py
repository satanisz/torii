"""SPEC-0020 AC-02/03: isolated synthetic forecasting worker, not bank modelling.

Only the worker loads its own just-uploaded model, after checking its digest.
The manifest records provided inputs; it is not observed-read lineage or WORM.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import io
import json
import logging
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
from contextlib import suppress
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TRACKING_URI = "http://mlflow:5000"
RESULT_PREFIX = "TORII_TRAIN_RESULT="
TRAIN_FRACTION = 0.8
GAP_ROWS = 1
FEATURES = [
    "profit_current",
    "profit_lag_1",
    "profit_rolling_3",
    "net_interest_current",
    "fees_current",
    "expenses_current",
    "credit_loss_current",
    "next_month_sin",
    "next_month_cos",
]
TARGET = "accounting_profit_next"


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def csv_bytes(frame: pd.DataFrame) -> bytes:
    # 17 significant digits and round_trip reading preserve float64 inputs.
    return frame.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode(
        "utf-8"
    )


def generate_monthly_data(seed: int) -> pd.DataFrame:
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("invalid_seed")
    rng = np.random.default_rng(seed)
    t = np.arange(120, dtype=float)
    shock = np.empty(len(t))
    previous = 0.0
    for i in range(len(t)):
        previous = 0.65 * previous + rng.normal(0, 8)
        shock[i] = previous
    season = np.sin(2 * np.pi * t / 12)
    interest_income = 700 + 2.8 * t + 70 * season + shock
    interest_expense = 210 + 0.9 * t + 12 * season + rng.normal(0, 3, len(t))
    fees = 140 + 0.5 * t + 25 * np.cos(2 * np.pi * t / 12) + rng.normal(0, 3, len(t))
    expenses = 330 + 0.7 * t + rng.normal(0, 5, len(t))
    credit_loss = 40 + 0.1 * t + rng.normal(0, 3, len(t))
    frame = pd.DataFrame(
        {
            "month": pd.date_range("2016-01-01", periods=len(t), freq="MS").strftime(
                "%Y-%m"
            ),
            "interest_income": interest_income,
            "interest_expense": interest_expense,
            "fee_income": fees,
            "operating_expense": expenses,
            "credit_loss": credit_loss,
        }
    )
    # This is a synthetic accounting-style aggregate, not NII or statutory net profit.
    frame["accounting_profit"] = (
        frame["interest_income"]
        - frame["interest_expense"]
        + frame["fee_income"]
        - frame["operating_expense"]
        - frame["credit_loss"]
    )
    return frame


def build_supervised(raw: pd.DataFrame) -> pd.DataFrame:
    """Forecast at the END of month t, after its synthetic accounts are available.

    Features use observations through t only. The label is profit in t+1.
    The next month's calendar is known in advance; its financial values are not.
    """
    months = pd.to_datetime(raw["month"], format="%Y-%m", errors="raise")
    if not months.is_monotonic_increasing or months.duplicated().any():
        raise ValueError("unordered_months")
    expected = pd.date_range(months.iloc[0], periods=len(months), freq="MS")
    if not np.array_equal(months.to_numpy(), expected.to_numpy()):
        raise ValueError("non_contiguous_months")
    next_month = months + pd.offsets.MonthBegin(1)
    frame = (
        pd.DataFrame(
            {
                "origin_month": raw["month"],
                "target_month": next_month.dt.strftime("%Y-%m"),
                "profit_current": raw["accounting_profit"],
                "profit_lag_1": raw["accounting_profit"].shift(1),
                "profit_rolling_3": raw["accounting_profit"]
                .rolling(3, min_periods=3)
                .mean(),
                "net_interest_current": raw["interest_income"]
                - raw["interest_expense"],
                "fees_current": raw["fee_income"],
                "expenses_current": raw["operating_expense"],
                "credit_loss_current": raw["credit_loss"],
                "next_month_sin": np.sin(2 * np.pi * next_month.dt.month / 12),
                "next_month_cos": np.cos(2 * np.pi * next_month.dt.month / 12),
                "accounting_profit_next": raw["accounting_profit"].shift(-1),
            }
        )
        .iloc[2:-1]
        .reset_index(drop=True)
    )
    if (
        len(frame) < 30
        or not np.isfinite(frame[FEATURES + ["accounting_profit_next"]]).all().all()
    ):
        raise ValueError("invalid_supervised_data")
    return frame


def chronological_split(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    train_count = int(len(frame) * TRAIN_FRACTION)
    train = frame.iloc[:train_count].copy()
    test = frame.iloc[train_count + GAP_ROWS :].copy()
    if (
        len(train) < 20
        or len(test) < 2
        or train["target_month"].max() >= test["origin_month"].min()
    ):
        raise ValueError("invalid_temporal_split")
    split = {
        "method": "chronological_holdout",
        "train_fraction": TRAIN_FRACTION,
        "gap_rows": GAP_ROWS,
        "shuffle": False,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_origin_months": train["origin_month"].tolist(),
        "test_origin_months": test["origin_month"].tolist(),
        "excluded_gap_origins": frame.iloc[train_count : train_count + GAP_ROWS][
            "origin_month"
        ].tolist(),
        "training_cutoff_target_month": train["target_month"].max(),
        "test_first_origin_month": test["origin_month"].min(),
        "feature_available_at": "end_of_origin_month_after_accounts_close",
        "label_horizon_months": 1,
        "evaluation": "fixed_model_one_step_ahead_at_each_month_end",
        "test_usage": "evaluation_only_no_hyperparameter_selection",
    }
    return train, test, split


def fit_candidates(
    train: pd.DataFrame, test: pd.DataFrame
) -> dict[str, dict[str, Any]]:
    candidates = {
        "dummy": Pipeline([("model", DummyRegressor(strategy="mean"))]),
        "ridge": Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))]),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, model in candidates.items():
        model.fit(train[FEATURES], train[TARGET])
        prediction = model.predict(test[FEATURES])
        metrics = {
            "mae": float(mean_absolute_error(test[TARGET], prediction)),
            "rmse": float(root_mean_squared_error(test[TARGET], prediction)),
            "r2": float(r2_score(test[TARGET], prediction)),
        }
        if not np.isfinite(prediction).all() or not all(
            map(math.isfinite, metrics.values())
        ):
            raise ValueError("non_finite_result")
        predictions = test[["origin_month", "target_month"]].copy()
        predictions["actual"] = test[TARGET].to_numpy()
        predictions["predicted"] = prediction
        result[name] = {"model": model, "metrics": metrics, "predictions": predictions}
    return result


def transform_source() -> bytes:
    preamble = (
        '"""Exact feature/split functions; complete worker also logged as code/train.py."""\n'
        "from typing import Any\nimport numpy as np\nimport pandas as pd\n"
        f"FEATURES = {FEATURES!r}\nTRAIN_FRACTION = {TRAIN_FRACTION!r}\nGAP_ROWS = {GAP_ROWS!r}\n\n"
    )
    return (
        preamble
        + inspect.getsource(build_supervised)
        + "\n"
        + inspect.getsource(chronological_split)
    ).encode()


def environment_provenance(image_id: str) -> tuple[bytes, bytes]:
    frozen = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        capture_output=True,
        check=True,
        timeout=30,
        text=True,
    ).stdout
    lines = sorted(line.strip() for line in frozen.splitlines() if line.strip())
    # Refuse URL/editable credentials or host paths in a purported frozen package list.
    if not lines or any(
        not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.!+\-]+", line) for line in lines
    ):
        raise ValueError("unsupported_environment_provenance")
    environment = {
        "image_id": image_id,
        "python": platform.python_version(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "packages": {
            name: version(name)
            for name in ("mlflow", "scikit-learn", "pandas", "numpy", "joblib")
        },
        "reproducibility_scope": "same_pinned_image_and_inputs_predictions_and_metrics",
        "model_serialization_bitwise_reproducibility": "not_claimed",
    }
    return json_bytes(environment), ("\n".join(lines) + "\n").encode()


def proxy_artifact_uri(uri: str) -> bool:
    parsed = urlsplit(uri)
    return (
        parsed.scheme == "mlflow-artifacts"
        and parsed.netloc in ("", "mlflow:5000")
        and bool(parsed.path)
    )


def authenticate_worker() -> str:
    if os.environ.get("MLFLOW_TRACKING_URI") != TRACKING_URI:
        raise ValueError("unexpected_tracking_uri")
    image_id = os.environ.get("TORII_IMAGE_ID", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("missing_image_identity")
    if any(
        os.environ.get(key)
        for key in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "MLFLOW_S3_ENDPOINT_URL",
        )
    ):
        raise ValueError("worker_received_storage_credentials")
    password = Path("/run/secrets/user_a").read_text(encoding="utf-8").strip()
    if not 16 <= len(password) <= 8192 or any(
        ord(ch) < 33 or ord(ch) > 126 for ch in password
    ):
        raise ValueError("invalid_worker_secret")
    os.environ["MLFLOW_TRACKING_USERNAME"] = "analyst_a"
    os.environ["MLFLOW_TRACKING_PASSWORD"] = password
    os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    os.environ["MLFLOW_ENABLE_ASYNC_LOGGING"] = "false"
    os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] = "30"
    return image_id


def write_files(directory: Path, content: dict[str, bytes]) -> dict[str, str]:
    hashes = {}
    for name, payload in content.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        hashes[name] = digest(payload)
    return hashes


def artifact_ref(kind: str, run_id: str, path: str, sha256: str) -> dict[str, str]:
    return {
        "kind": kind,
        "id": f"{kind}:{sha256}",
        "run_id": run_id,
        "artifact_path": path,
        "sha256": sha256,
    }


def log_verified_run(
    client: Any,
    experiment_id: str,
    root: Path,
    name: str,
    content: dict[str, bytes],
    params: dict[str, Any],
    provided_inputs: list[dict[str, str]],
    outputs: dict[str, str],
    image_id: str,
    metrics: dict[str, float] | None = None,
    model: Pipeline | None = None,
    test: pd.DataFrame | None = None,
) -> tuple[str, dict[str, str]]:
    run = client.create_run(
        experiment_id,
        tags={
            "mlflow.runName": name,
            "torii.spec": "SPEC-0020",
            "torii.mode": "exp03a",
            "torii.lineage": "provided_inputs",
        },
    )
    run_id = run.info.run_id
    try:
        if not proxy_artifact_uri(run.info.artifact_uri):
            raise ValueError("artifact_proxy_required")
        directory = root / run_id
        directory.mkdir()
        hashes = write_files(directory, content)
        if model is not None:
            joblib.dump(model, directory / "model.joblib")
            hashes["model.joblib"] = digest((directory / "model.joblib").read_bytes())
        output_refs = [
            artifact_ref(kind, run_id, path, hashes[path])
            for path, kind in outputs.items()
        ]
        # Code/environment are supplied to the computation, not produced by fitting.
        provided_inputs = [
            *provided_inputs,
            *[
                artifact_ref(kind, run_id, path, hashes[path])
                for path, kind in (
                    ("code/train.py", "SourceCodeVersion"),
                    ("code/transform.py", "TransformationVersion"),
                    ("environment.json", "EnvironmentVersion"),
                    ("pip-freeze.txt", "DependencyLock"),
                )
            ],
        ]
        manifest = {
            "schema_version": 1,
            "spec": "SPEC-0020",
            "run_id": run_id,
            "run_kind": name,
            "image_id": image_id,
            "parameters": params,
            "metrics": metrics or {},
            "provided_inputs": provided_inputs,
            "outputs": output_refs,
            "edges": [
                {
                    "type": "provided_input",
                    "source": ref["id"],
                    "target": f"Run:{run_id}",
                    "kind": ref["kind"],
                }
                for ref in provided_inputs
            ]
            + [
                {
                    "type": "produced",
                    "source": f"Run:{run_id}",
                    "target": ref["id"],
                    "kind": ref["kind"],
                }
                for ref in output_refs
            ],
            "artifact_digests": dict(hashes),
            "assurance": {
                "lineage": "provided_inputs",
                "observed_reads": "not_collected",
                "snapshot_immutability": "not_qualified",
                "financial_use": "synthetic_exercise_only",
            },
        }
        hashes.update(write_files(directory, {"manifest.json": json_bytes(manifest)}))
        for key, value in params.items():
            client.log_param(run_id, key, value, synchronous=True)
        for key, value in (metrics or {}).items():
            client.log_metric(run_id, key, value, synchronous=True)
        for artifact_name in sorted(hashes):
            parent = Path(artifact_name).parent.as_posix()
            client.log_artifact(
                run_id,
                str(directory / artifact_name),
                artifact_path=None if parent == "." else parent,
            )
        downloaded = root / (run_id + "-download")
        downloaded.mkdir()
        paths = {}
        for artifact_name, expected in hashes.items():
            actual = Path(
                client.download_artifacts(run_id, artifact_name, str(downloaded))
            ).resolve()
            if (
                not actual.is_relative_to(downloaded.resolve())
                or digest(actual.read_bytes()) != expected
            ):
                raise ValueError("artifact_verification_failed")
            paths[artifact_name] = actual
        if model is not None:
            if test is None:
                raise ValueError("missing_model_verification_input")
            # Only OUR artifact, retrieved through the authenticated proxy and digest-checked.
            restored = joblib.load(paths["model.joblib"])
            np.testing.assert_allclose(
                restored.predict(test[FEATURES]),
                model.predict(test[FEATURES]),
                rtol=0,
                atol=0,
            )
        client.set_terminated(run_id, status="FINISHED")
        return run_id, hashes
    except Exception:
        with suppress(Exception):
            client.set_terminated(run_id, status="FAILED")
        raise


def execute(seed: int, experiment_name: str) -> dict[str, Any]:
    image_id = authenticate_worker()
    from mlflow import MlflowClient

    client = MlflowClient(
        tracking_uri=TRACKING_URI,
        registry_uri=TRACKING_URI,
        workspace_store_uri=TRACKING_URI,
    )
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        experiment_id = client.create_experiment(experiment_name)
        experiment = client.get_experiment(experiment_id)
    if experiment.lifecycle_stage != "active" or not proxy_artifact_uri(
        experiment.artifact_location
    ):
        raise ValueError("unexpected_experiment_storage")
    experiment_id = experiment.experiment_id
    raw_bytes = csv_bytes(generate_monthly_data(seed))
    # The exact bytes recorded as the input are read back before transformations.
    raw = pd.read_csv(io.BytesIO(raw_bytes), float_precision="round_trip")
    supervised = build_supervised(raw)
    train, test, split = chronological_split(supervised)
    candidates = fit_candidates(train, test)
    code = Path(__file__).read_bytes()
    transform = transform_source()
    environment, frozen = environment_provenance(image_id)
    feature_bytes, split_bytes = csv_bytes(supervised), json_bytes(split)
    common = {
        "code/train.py": code,
        "code/transform.py": transform,
        "environment.json": environment,
        "pip-freeze.txt": frozen,
    }
    hashes = {
        "data_digest": digest(raw_bytes),
        "feature_digest": digest(feature_bytes),
        "split_digest": digest(split_bytes),
        "source_digest": digest(code),
        "transform_digest": digest(transform),
    }
    params = {
        "seed": seed,
        "target": TARGET,
        "feature_names": json.dumps(FEATURES),
        "horizon_months": 1,
        "image_id": image_id,
        **hashes,
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "ok",
        "seed": seed,
        "image_id": image_id,
        "experiment_id": experiment_id,
        **hashes,
        "run_ids": {},
        "provenance_run_ids": {},
        "prediction_digests": {},
        "metrics": {},
        "artifact_digests": {},
    }
    with tempfile.TemporaryDirectory(prefix="torii-training-") as temporary:
        root = Path(temporary)
        data_id, artifacts = log_verified_run(
            client,
            experiment_id,
            root,
            "synthetic-dataset",
            {**common, "data/monthly.csv": raw_bytes},
            params,
            [],
            {"data/monthly.csv": "DatasetVersion"},
            image_id,
        )
        result["provenance_run_ids"]["dataset"] = data_id
        result["artifact_digests"][data_id] = artifacts
        data_ref = artifact_ref(
            "DatasetVersion", data_id, "data/monthly.csv", hashes["data_digest"]
        )
        transform_id, artifacts = log_verified_run(
            client,
            experiment_id,
            root,
            "feature-transformation",
            {
                **common,
                "data/monthly.csv": raw_bytes,
                "data/supervised.csv": feature_bytes,
                "split.json": split_bytes,
            },
            params,
            [data_ref],
            {
                "data/supervised.csv": "FeatureDatasetVersion",
                "split.json": "SplitVersion",
            },
            image_id,
        )
        result["provenance_run_ids"]["transformation"] = transform_id
        result["artifact_digests"][transform_id] = artifacts
        inputs = [
            data_ref,
            artifact_ref(
                "FeatureDatasetVersion",
                transform_id,
                "data/supervised.csv",
                hashes["feature_digest"],
            ),
            artifact_ref(
                "SplitVersion", transform_id, "split.json", hashes["split_digest"]
            ),
            artifact_ref(
                "TransformationVersion",
                transform_id,
                "code/transform.py",
                hashes["transform_digest"],
            ),
        ]
        for name, candidate in candidates.items():
            prediction_bytes = csv_bytes(candidate["predictions"])
            model_params = {
                **params,
                "algorithm": name,
                "train_rows": len(train),
                "test_rows": len(test),
                "gap_rows": GAP_ROWS,
                "prediction_digest": digest(prediction_bytes),
                "baseline_strategy" if name == "dummy" else "ridge_alpha": "mean"
                if name == "dummy"
                else 1.0,
            }
            run_id, artifacts = log_verified_run(
                client,
                experiment_id,
                root,
                name,
                {
                    **common,
                    "data/monthly.csv": raw_bytes,
                    "data/supervised.csv": feature_bytes,
                    "split.json": split_bytes,
                    "predictions.csv": prediction_bytes,
                    "metrics.json": json_bytes(candidate["metrics"]),
                },
                model_params,
                inputs,
                {
                    "model.joblib": "ModelVersion",
                    "predictions.csv": "PredictionDatasetVersion",
                    "metrics.json": "EvaluationResult",
                },
                image_id,
                metrics=candidate["metrics"],
                model=candidate["model"],
                test=test,
            )
            result["run_ids"][name] = run_id
            result["artifact_digests"][run_id] = artifacts
            result["prediction_digests"][name] = digest(prediction_bytes)
            result["metrics"][name] = candidate["metrics"]
    result["verification"] = {"artifact_downloads": True, "model_predictions": True}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SPEC-0020 synthetic next-month forecast worker"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--experiment-name", default="finance-forecast")
    args = parser.parse_args()
    # Dedicated short-lived worker: SDK diagnostic records are not provenance artifacts.
    logging.disable(logging.CRITICAL)
    try:
        if not 0 <= args.seed <= 2**32 - 1 or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.experiment_name
        ):
            raise ValueError("invalid_worker_arguments")
        result = execute(args.seed, args.experiment_name)
    except Exception:  # noqa: BLE001 - CLI boundary must never print SDK exceptions with credentials.
        print(
            RESULT_PREFIX
            + json_bytes(
                {
                    "schema_version": 1,
                    "status": "failed",
                    "error": "training_or_tracking_failed",
                }
            )
            .decode()
            .strip()
        )
        return 1
    print(RESULT_PREFIX + json_bytes(result).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
