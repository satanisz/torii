"""End-to-end AutoML MVP: data, validation, AutoML, registry and catalog."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import tempfile
from importlib.metadata import version
from pathlib import Path

import boto3
import pandas as pd
import pandera.pandas as pa
from pandera import Check
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split

from torii_project.config import PROJECT_ROOT, REPORTS_DIR

EXPERIMENT_NAME = os.getenv("TORII_EXPERIMENT_NAME", "automl-end-to-end-mvp")
REGISTERED_MODEL_NAME = os.getenv(
    "TORII_REGISTERED_MODEL_NAME", "automl-breast-cancer-classifier"
)
TARGET = "is_benign"
ROW_ID = "row_id"


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://minio:9000"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )


def _upload_bytes(key: str, content: bytes, content_type: str) -> str:
    bucket = os.getenv("TORII_DATA_BUCKET", os.getenv("AUTOML_DATA_BUCKET", "automl-data"))
    _s3_client().put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)
    return f"s3://{bucket}/{key}"


def _normalise_column(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def prepare_data() -> tuple[pd.DataFrame, dict[str, object]]:
    """Create an immutable raw snapshot, validate it and write transformed Parquet."""
    source = load_breast_cancer(as_frame=True).frame.rename(columns={"target": TARGET})
    source.insert(0, ROW_ID, range(len(source)))
    source[TARGET] = source[TARGET].astype(int)

    raw_bytes = source.to_csv(index=False).encode("utf-8")
    raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    raw_key = f"raw/breast-cancer/sha256={raw_hash[:12]}/data.csv"
    raw_uri = _upload_bytes(raw_key, raw_bytes, "text/csv")

    feature_columns = [column for column in source.columns if column not in {ROW_ID, TARGET}]
    schema_columns: dict[str, pa.Column] = {
        ROW_ID: pa.Column(int, nullable=False, unique=True, coerce=True),
        TARGET: pa.Column(int, Check.isin([0, 1]), nullable=False, coerce=True),
    }
    schema_columns.update(
        {column: pa.Column(float, nullable=False, coerce=True) for column in feature_columns}
    )
    validated = pa.DataFrameSchema(schema_columns, strict=True).validate(source)

    processed = validated.rename(
        columns={column: _normalise_column(column) for column in validated}
    )
    processed = (
        processed.drop_duplicates(subset=[ROW_ID]).sort_values(ROW_ID).reset_index(drop=True)
    )
    parquet_buffer = io.BytesIO()
    processed.to_parquet(parquet_buffer, index=False)
    processed_bytes = parquet_buffer.getvalue()
    processed_hash = hashlib.sha256(processed_bytes).hexdigest()
    processed_key = f"processed/breast-cancer/sha256={processed_hash[:12]}/data.parquet"
    processed_uri = _upload_bytes(processed_key, processed_bytes, "application/vnd.apache.parquet")

    report: dict[str, object] = {
        "source": "sklearn.datasets.load_breast_cancer",
        "target_semantics": "is_benign: 0 = malignant, 1 = benign",
        "raw_uri": raw_uri,
        "raw_sha256": raw_hash,
        "processed_uri": processed_uri,
        "processed_sha256": processed_hash,
        "rows": len(processed),
        "columns": len(processed.columns),
        "null_cells": int(processed.isna().sum().sum()),
        "duplicate_row_ids": int(processed[ROW_ID].duplicated().sum()),
        "target_values": sorted(processed[TARGET].unique().tolist()),
        "validation": "passed",
        "transformations": [
            "validate types, nullability, target domain and row-id uniqueness",
            "normalise column names to snake_case",
            "remove duplicate row ids and sort deterministically",
            "serialize the training snapshot as Parquet",
        ],
    }
    manifest_bytes = json.dumps(report, indent=2).encode("utf-8")
    manifest_key = processed_key.rsplit("/", 1)[0] + "/manifest.json"
    report["manifest_uri"] = _upload_bytes(manifest_key, manifest_bytes, "application/json")
    return processed, report


def train_and_register(
    processed: pd.DataFrame,
    manifest: dict[str, object],
    *,
    time_limit: int,
    preset: str,
) -> dict[str, str]:
    """Train an AutoGluon model, track it and register a candidate version."""
    import mlflow
    import mlflow.pyfunc
    from autogluon.tabular import TabularPredictor
    from mlflow.models import infer_signature

    from torii_project.automl.pyfunc import AutoGluonPyFuncModel

    modelling_data = processed.drop(columns=[ROW_ID])
    train_data, test_data = train_test_split(
        modelling_data,
        test_size=0.2,
        random_state=42,
        stratify=modelling_data[TARGET],
    )
    features = train_data.drop(columns=[TARGET])
    input_example = test_data.drop(columns=[TARGET]).head(3)
    mlflow.set_experiment(EXPERIMENT_NAME)
    dataset = mlflow.data.from_pandas(
        train_data,
        source=str(manifest["processed_uri"]),
        name="breast-cancer-validated-training-snapshot",
        targets=TARGET,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="automl-autogluon-") as temporary_directory:
        predictor_path = Path(temporary_directory) / "predictor"
        with mlflow.start_run(run_name="autogluon-candidate-training") as run:
            mlflow.log_input(dataset, context="training")
            mlflow.log_params(
                {
                    "engine": "autogluon.tabular",
                    "preset": preset,
                    "time_limit_seconds": time_limit,
                    "target": TARGET,
                    "metric": "roc_auc",
                    "data_snapshot_uri": manifest["processed_uri"],
                    "data_snapshot_sha256": manifest["processed_sha256"],
                    "validation": manifest["validation"],
                }
            )
            mlflow.log_dict(manifest, "data/manifest.json")
            mlflow.log_metrics(
                {
                    "data_rows": float(manifest["rows"]),
                    "data_null_cells": float(manifest["null_cells"]),
                    "data_duplicate_row_ids": float(manifest["duplicate_row_ids"]),
                }
            )
            mlflow.log_dict(
                {
                    "python": platform.python_version(),
                    "autogluon_tabular": version("autogluon.tabular"),
                    "image_profile": os.getenv(
                        "TORII_PROFILE", os.getenv("AUTOML_PROFILE", "automl-tabular")
                    ),
                },
                "environment.json",
            )
            predictor = TabularPredictor(
                label=TARGET,
                problem_type="binary",
                eval_metric="roc_auc",
                path=str(predictor_path),
            ).fit(
                train_data=train_data,
                presets=preset,
                time_limit=time_limit,
                hyperparameters={"GBM": {}, "CAT": {}, "RF": {}, "XT": {}, "NN_TORCH": {}},
            )
            evaluation = predictor.evaluate(test_data)
            mlflow.log_metrics({f"test_{key}": float(value) for key, value in evaluation.items()})
            leaderboard = predictor.leaderboard(test_data)
            leaderboard_path = REPORTS_DIR / "mvp_leaderboard.csv"
            leaderboard.to_csv(leaderboard_path, index=False)
            mlflow.log_artifact(str(leaderboard_path), artifact_path="reports")
            signature = infer_signature(features, predictor.predict(features.head(10)))
            mlflow.pyfunc.log_model(
                name="model",
                python_model=AutoGluonPyFuncModel(),
                artifacts={"predictor": str(predictor_path)},
                signature=signature,
                input_example=input_example,
                pip_requirements=[
                    "mlflow==3.14.0",
                    "autogluon.tabular[lightgbm,catboost]==1.5.0",
                    "pandas>=2,<3",
                ],
            )
            model_uri = f"runs:/{run.info.run_id}/model"

        registered = mlflow.register_model(model_uri, REGISTERED_MODEL_NAME)
        mlflow.MlflowClient().set_registered_model_alias(
            REGISTERED_MODEL_NAME, "candidate", registered.version
        )

    return {
        "run_id": run.info.run_id,
        "model_uri": model_uri,
        "registered_model": REGISTERED_MODEL_NAME,
        "registered_version": str(registered.version),
        "alias": "candidate",
    }


def run_batch_inference(processed: pd.DataFrame, training: dict[str, str]) -> str:
    """Load the registered alias in a fresh MLflow API call and persist predictions."""
    import mlflow
    import mlflow.pyfunc

    model = mlflow.pyfunc.load_model(f"models:/{REGISTERED_MODEL_NAME}@candidate")
    features = processed.drop(columns=[ROW_ID, TARGET])
    predictions = model.predict(features)
    output = processed[[ROW_ID, TARGET]].copy()
    output["prediction"] = predictions["prediction"].to_numpy()
    buffer = io.BytesIO()
    output.to_parquet(buffer, index=False)
    key = f"predictions/breast-cancer/run_id={training['run_id']}/predictions.parquet"
    predictions_uri = _upload_bytes(key, buffer.getvalue(), "application/vnd.apache.parquet")
    with mlflow.start_run(run_name="candidate-batch-inference"):
        mlflow.log_params(
            {
                "registered_model": REGISTERED_MODEL_NAME,
                "model_alias": "candidate",
                "training_run_id": training["run_id"],
                "predictions_uri": predictions_uri,
            }
        )
        mlflow.log_metrics(
            {
                "prediction_rows": float(len(output)),
                "prediction_positive_rate": float(output["prediction"].mean()),
            }
        )
    return predictions_uri


def run_mvp(time_limit: int = 120, preset: str = "medium_quality", catalog: bool = True):
    processed, manifest = prepare_data()
    training = train_and_register(processed, manifest, time_limit=time_limit, preset=preset)
    predictions_uri = run_batch_inference(processed, training)
    if catalog:
        from torii_project.automl.catalog import ingest_catalog, publish_lineage

        publish_lineage(
            raw_uri=str(manifest["raw_uri"]),
            processed_uri=str(manifest["processed_uri"]),
            predictions_uri=predictions_uri,
            run_id=training["run_id"],
        )
        ingest_catalog(PROJECT_ROOT / "config" / "datahub")
    result = {
        **training,
        "raw_uri": str(manifest["raw_uri"]),
        "processed_uri": str(manifest["processed_uri"]),
        "predictions_uri": predictions_uri,
        "datahub_catalogued": str(catalog).lower(),
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("time_limit", type=int, nargs="?", default=120)
    parser.add_argument("--preset", default="medium_quality")
    parser.add_argument("--skip-catalog", action="store_true")
    arguments = parser.parse_args()
    run_mvp(
        time_limit=arguments.time_limit,
        preset=arguments.preset,
        catalog=not arguments.skip_catalog,
    )
