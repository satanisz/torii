"""SPEC-0020: provision only the two technical accounts of this isolated trial."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests
from mlflow.exceptions import MlflowException
from mlflow.server import get_app_client

import mlflow


def main() -> int:
    logging.disable(logging.CRITICAL)
    report: dict[str, Any] = {"spec": "SPEC-0020", "status": "FAIL", "accounts": []}
    try:
        if mlflow.__version__ != "3.14.0":
            raise ValueError("version")
        uri = os.environ["MLFLOW_TRACKING_URI"].rstrip("/")
        if uri != "http://mlflow:5000":
            raise ValueError("isolated_endpoint")
        secret_dir = Path("/run/secrets")
        password = (secret_dir / "admin_password").read_text().strip()
        if not password or password == "password1234":
            raise ValueError("admin_secret")
        os.environ["MLFLOW_TRACKING_USERNAME"] = "admin"
        os.environ["MLFLOW_TRACKING_PASSWORD"] = password
        os.environ.pop("MLFLOW_TRACKING_TOKEN", None)
        os.environ.pop("MLFLOW_WORKSPACE", None)
        auth = get_app_client("basic-auth", tracking_uri=uri)
        with requests.Session() as session:
            session.trust_env = False
            for username, filename in (
                ("analyst_a", "user_a"),
                ("analyst_b", "user_b"),
            ):
                user_password = (secret_dir / filename).read_text().strip()
                if not user_password:
                    raise ValueError("user_secret")
                try:
                    user = auth.get_user(username)
                    created = False
                except MlflowException as exc:
                    if exc.error_code != "RESOURCE_DOES_NOT_EXIST":
                        raise
                    user = auth.create_user(username, user_password)
                    created = True
                if user.is_admin:
                    raise ValueError("unexpected_admin")
                # Existing accounts must match their instance secret; never silently reset them.
                response = session.get(
                    uri + "/api/2.0/mlflow/users/current",
                    auth=(username, user_password),
                    timeout=15,
                    allow_redirects=False,
                )
                if (
                    response.status_code != 200
                    or response.json().get("user", {}).get("username") != username
                ):
                    raise ValueError("credential_verification")
                report["accounts"].append({"username": username, "created": created})
        report["status"] = "PASS"
        result = 0
    except Exception:  # noqa: BLE001 - safe CLI boundary, never prints exceptions
        # Never echo response bodies, connection strings, or exception messages with secrets.
        report["error"] = (
            "Bootstrap failed; inspect isolated service readiness and configuration."
        )
        result = 1
    print("TORII_BOOTSTRAP_RESULT=" + json.dumps(report, separators=(",", ":")))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
