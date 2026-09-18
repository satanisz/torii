"""A reproducible tabular AutoML demonstration for Torii workspaces."""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import mlflow
import mlflow.pyfunc
import pandas as pd
from autogluon.tabular import TabularPredictor
from mlflow.models import infer_signature
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split

from torii_project.automl.pyfunc import AutoGluonPyFuncModel
from torii_project.config import RAW_DATA_DIR, REPORTS_DIR

EXPERIMENT_NAME = os.getenv("TORII_DEMO_EXPERIMENT_NAME", "automl-demo")
REGISTERED_MODEL_NAME = os.getenv(
    "TORII_REGISTERED_MODEL_NAME", "automl-breast-cancer-classifier"
)
DATASET_SOURCE = "sklearn.datasets.load_breast_cancer"


def _load_demo_data() -> pd.DataFrame:
    """Load a small built-in dataset so the demo needs no external credentials."""
    dataset = load_breast_cancer(as_frame=True)
    frame = dataset.frame.rename(columns={"target": "malignant"})
    frame["malignant"] = frame["malignant"].astype(int)
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(RAW_DATA_DIR / "breast_cancer.csv", index=False)
    return frame


def run_demo(time_limit: int = 120, preset: str = "medium_quality") -> dict[str, str]:
    """Train, track and register a trusted AutoGluon model in MLflow.

    The ``medium_quality`` preset keeps a local proof of concept short. Use
    ``good_quality`` and a larger time limit for a stronger model comparison.
    """
    frame = _load_demo_data()
    train_data, test_data = train_test_split(
        frame,
        test_size=0.2,
        random_state=42,
        stratify=frame["malignant"],
    )
    features = train_data.drop(columns=["malignant"])
    input_example = test_data.drop(columns=["malignant"]).head(3)

    mlflow.set_experiment(EXPERIMENT_NAME)
    dataset = mlflow.data.from_pandas(
        train_data,
        source=DATASET_SOURCE,
        name="breast-cancer-training",
        targets="malignant",
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="automl-autogluon-") as temporary_directory:
        predictor_path = Path(temporary_directory) / "predictor"
        with mlflow.start_run(run_name="autogluon-tabular-demo") as run:
            mlflow.log_input(dataset, context="training")
            mlflow.log_params(
                {
                    "engine": "autogluon.tabular",
                    "preset": preset,
                    "time_limit_seconds": time_limit,
                    "target": "malignant",
                    "metric": "roc_auc",
                    "split_strategy": "stratified_holdout",
                    "split_random_state": 42,
                    "dataset_source": DATASET_SOURCE,
                }
            )
            mlflow.log_dict(
                {
                    "python": platform.python_version(),
                    "autogluon_tabular": version("autogluon.tabular"),
                    "platform": platform.platform(),
                    "image_profile": "automl-tabular",
                },
                "environment.json",
            )

            predictor = TabularPredictor(
                label="malignant",
                problem_type="binary",
                eval_metric="roc_auc",
                path=str(predictor_path),
            ).fit(
                train_data=train_data,
                presets=preset,
                time_limit=time_limit,
                hyperparameters={
                    "GBM": {},
                    "CAT": {},
                    "RF": {},
                    "XT": {},
                    "NN_TORCH": {},
                },
            )

            evaluation = predictor.evaluate(test_data)
            mlflow.log_metrics({f"test_{key}": float(value) for key, value in evaluation.items()})

            leaderboard = predictor.leaderboard(test_data)
            leaderboard_path = REPORTS_DIR / "autogluon_leaderboard.csv"
            leaderboard.to_csv(leaderboard_path, index=False)
            mlflow.log_artifact(str(leaderboard_path), artifact_path="reports")
            mlflow.log_text(leaderboard.to_markdown(index=False), "reports/leaderboard.md")

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
            mlflow.log_param("model_uri", model_uri)

        registered_version = mlflow.register_model(model_uri, REGISTERED_MODEL_NAME)
        client = mlflow.MlflowClient()
        client.set_registered_model_alias(
            REGISTERED_MODEL_NAME,
            "candidate",
            registered_version.version,
        )

    result = {
        "run_id": run.info.run_id,
        "model_uri": model_uri,
        "registered_model": REGISTERED_MODEL_NAME,
        "registered_version": str(registered_version.version),
        "alias": "candidate",
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    requested_time_limit = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    run_demo(time_limit=requested_time_limit)
