"""SPEC-0020 AC-03: download prior artifacts after service restart."""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from mlflow import MlflowClient


def main() -> None:
    report = json.load(sys.stdin)
    os.environ["MLFLOW_TRACKING_USERNAME"] = "analyst_a"
    os.environ["MLFLOW_TRACKING_PASSWORD"] = (
        Path("/run/secrets/user_a").read_text().strip()
    )
    client = MlflowClient()
    count = 0
    with tempfile.TemporaryDirectory() as directory:
        for run_id, artifacts in report["artifact_digests"].items():
            assert client.get_run(run_id).info.run_id == run_id
            for name, digest in artifacts.items():
                downloaded = client.download_artifacts(run_id, name, directory)
                assert (
                    hashlib.sha256(Path(downloaded).read_bytes()).hexdigest() == digest
                )
                count += 1
    print(
        "TORII_VERIFY_RESULT="
        + json.dumps({"status": "ok", "verified_artifacts": count})
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - safe process boundary for SDK failures
        print('TORII_VERIFY_RESULT={"status":"failed"}')
        raise SystemExit(1) from None
