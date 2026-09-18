"""Publish the MVP's datasets and lineage to the local DataHub instance."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

from datahub.emitter.mce_builder import make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    DatasetLineageTypeClass,
    DatasetPropertiesClass,
    UpstreamClass,
    UpstreamLineageClass,
)


def wait_for_datahub(timeout_seconds: int = 180) -> str:
    """Wait until GMS is ready and return its URL."""
    gms_url = os.getenv("DATAHUB_GMS_URL", "http://datahub-gms:8080").rstrip("/")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{gms_url}/health", timeout=3) as response:
                if response.status == 200:
                    return gms_url
        except OSError:
            time.sleep(3)
    raise TimeoutError(f"DataHub did not become ready at {gms_url}")


def _dataset_urn(uri: str) -> str:
    # DataHub's S3 connector uses ``bucket/key`` as its dataset name. Reuse
    # that convention so descriptions and lineage enrich the connector-created
    # entity instead of creating a second dataset whose name starts with s3://.
    return make_dataset_urn(platform="s3", name=uri.removeprefix("s3://"), env="PROD")


def publish_lineage(
    *,
    raw_uri: str,
    processed_uri: str,
    predictions_uri: str,
    run_id: str,
) -> None:
    """Create searchable dataset descriptions and raw -> processed -> output lineage."""
    emitter = DatahubRestEmitter(gms_server=wait_for_datahub())
    entities = [
        (
            raw_uri,
            "AutoML raw breast-cancer snapshot",
            "Immutable source snapshot generated from scikit-learn for the local MVP.",
            None,
        ),
        (
            processed_uri,
            "AutoML validated training dataset",
            "Validated and normalized dataset used by the AutoGluon training run.",
            raw_uri,
        ),
        (
            predictions_uri,
            "AutoML batch predictions",
            "Predictions created by the MLflow candidate model.",
            processed_uri,
        ),
    ]
    for uri, name, description, upstream_uri in entities:
        urn = _dataset_urn(uri)
        emitter.emit(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=DatasetPropertiesClass(
                    name=name,
                    description=description,
                    customProperties={"storage_uri": uri, "mlflow_training_run_id": run_id},
                ),
            )
        )
        if upstream_uri:
            emitter.emit(
                MetadataChangeProposalWrapper(
                    entityUrn=urn,
                    aspect=UpstreamLineageClass(
                        upstreams=[
                            UpstreamClass(
                                dataset=_dataset_urn(upstream_uri),
                                type=DatasetLineageTypeClass.TRANSFORMED,
                            )
                        ]
                    ),
                )
            )


def ingest_catalog(recipe_directory: Path) -> None:
    """Run official DataHub connectors for MinIO/S3 and MLflow metadata."""
    commands = (
        ("datahub", "minio.yml"),
        ("/opt/datahub-mlflow-venv/bin/datahub", "mlflow.yml"),
    )
    for executable, recipe_name in commands:
        subprocess.run(
            [executable, "ingest", "-c", str(recipe_directory / recipe_name)],
            check=True,
            timeout=300,
        )
