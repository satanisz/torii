"""SPEC-0020 AC-01: fixed endpoints, file secrets, no credentials in argv."""

import logging
import os
import time
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def secret(name: str) -> str:
    value = Path("/run/secrets", name).read_text().strip()
    if not value or not all(c in "0123456789abcdef" for c in value):
        raise ValueError("Invalid provisioned secret")
    return value


def main() -> None:
    logging.getLogger("botocore").setLevel(logging.ERROR)
    os.environ.update(
        {
            "MLFLOW_BACKEND_STORE_URI": (
                f"postgresql+psycopg2://mlflow_tracking:{secret('postgres_tracking')}"
                "@database:5432/mlflow_tracking"
            ),
            "MLFLOW_AUTH_CONFIG_PATH": "/run/secrets/auth_config",
            "MLFLOW_FLASK_SERVER_SECRET_KEY": secret("flask_key"),
            "AWS_ACCESS_KEY_ID": secret("s3_access"),
            "AWS_SECRET_ACCESS_KEY": secret("s3_secret"),
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_EC2_METADATA_DISABLED": "true",
            "MLFLOW_S3_ENDPOINT_URL": "http://storage:8333",
            "MLFLOW_S3_ADDRESSING_STYLE": "path",
            "MLFLOW_ENABLE_WORKSPACES": "false",
        }
    )
    client = boto3.client(
        "s3",
        endpoint_url="http://storage:8333",
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            retries={"max_attempts": 0},
            s3={"addressing_style": "path"},
        ),
    )
    deadline = time.monotonic() + 100
    while True:
        try:
            client.head_bucket(Bucket="torii-artifacts")
            break
        except ClientError as error:
            if error.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                client.create_bucket(Bucket="torii-artifacts")
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("S3 bootstrap failed") from None
        except BotoCoreError:
            if time.monotonic() >= deadline:
                raise RuntimeError("S3 unavailable") from None
        time.sleep(2)
    client.close()
    os.execvp(
        "mlflow",
        [
            "mlflow",
            "server",
            "--app-name",
            "basic-auth",
            "--host",
            "0.0.0.0",
            "--port",
            "5000",
            "--workers",
            "1",
            "--serve-artifacts",
            "--artifacts-destination",
            "s3://torii-artifacts",
            "--gunicorn-opts",
            "--access-logfile /dev/null --error-logfile -",
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - process boundary must not emit credentials
        print("MLflow trial startup failed; no credentials emitted.", flush=True)
        raise SystemExit(1) from None
