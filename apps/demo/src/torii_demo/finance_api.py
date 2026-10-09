"""SPEC-0019 F01/F05: local finance history and a bounded, fixed-module worker.

The subprocess separates computation from the API; it is not a sandbox.
Immutable input envelopes are committed before dispatch and survive failures.
"""

import json
import os
import sqlite3
import subprocess
import sys
import threading
from contextlib import contextmanager
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from torii_demo.finance_engine import build_manifest, synthetic_snapshot
from torii_demo.store import NotFound, encode, timestamp

FAILED = "Analiza finansowa nie powiodła się. Uruchom ją ponownie."
INTERRUPTED = "Proces demo został przerwany. Uruchom analizę finansową ponownie."
TIMED_OUT = "Analiza finansowa przekroczyła limit 30 sekund. Uruchom ją ponownie."


class FinanceRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    shock_bps: int = Field(default=100, ge=-300, le=300)
    deposit_beta: float = Field(default=0.35, ge=0, le=1)
    inject_issues: bool = False


class _ReportValue(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class _Totals(_ReportValue):
    income_base_pln: float
    expense_base_pln: float
    nii_base_pln: float
    income_scenario_pln: float
    expense_scenario_pln: float
    nii_scenario_pln: float
    delta_nii_pln: float


class _Month(_Totals):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class _PositionMonth(_ReportValue):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    base_rate: float
    scenario_rate: float
    base_interest_pln: float
    scenario_interest_pln: float


class _Contribution(_ReportValue):
    position_id: str
    name: str
    side: Literal["asset", "liability"]
    balance_pln: float
    rate_type: Literal["fixed", "floating"]
    repricing_month: int = Field(ge=1, le=12)
    base_interest_pln: float
    scenario_interest_pln: float
    delta_nii_pln: float
    monthly: list[_PositionMonth] = Field(min_length=12, max_length=12)


class _Reconciliation(_ReportValue):
    gl_account: str
    side: Literal["asset", "liability"]
    portfolio_pln: float
    ledger_pln: float
    difference_pln: float
    status: Literal["matched", "mismatch"]


class _Anomaly(_ReportValue):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    nii_pln: float
    baseline_pln: float
    threshold_pln: float
    deviation_pln: float


class _Report(_ReportValue):
    # Exact immutable envelope equality is checked separately. The body schema
    # protects consumers from truncated or malformed worker output without
    # calculating any financial values in the API process.
    snapshot: dict[str, Any]
    scenario: FinanceRunInput
    manifest: dict[str, str]
    assumptions: list[str] = Field(min_length=1)
    quality_status: Literal["passed", "blocked"]
    reconciliation: list[_Reconciliation] = Field(min_length=1, max_length=200)
    anomalies: list[_Anomaly] = Field(max_length=6)
    monthly: list[_Month] = Field(min_length=12, max_length=12)
    contributions: list[_Contribution] = Field(min_length=1, max_length=100)
    totals: _Totals


class FinanceStore:
    """Independent demo database; project existence belongs to the parent store."""

    def __init__(self, parent):
        self.parent = parent
        self.root = parent.root / "finance"
        if self.root.is_symlink():
            raise ValueError("Finance storage must be an internal directory")
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "finance.sqlite"
        if self.database.is_symlink():
            raise ValueError("Finance database must be an internal file")
        self._lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS finance_runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
                    created_at TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    manifest TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    CHECK ((status = 'succeeded' AND result IS NOT NULL AND error IS NULL)
                        OR (status = 'failed' AND result IS NULL AND error IS NOT NULL)
                        OR (status IN ('queued','running') AND result IS NULL AND error IS NULL))
                );
                CREATE INDEX IF NOT EXISTS finance_runs_project_created
                    ON finance_runs(project_id, created_at DESC);
            """)

    @contextmanager
    def connection(self):
        with self._lock:
            db = sqlite3.connect(self.database, timeout=15)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()

    @staticmethod
    def _decode(row):
        item = dict(row)
        for field in ("snapshot", "scenario", "manifest", "result"):
            item[field] = json.loads(item[field]) if item[field] is not None else None
        return item

    def create_run(self, project_id, snapshot, scenario, manifest):
        self.parent.project(project_id)
        run_id = str(uuid4())
        with self.connection() as db:
            db.execute(
                """INSERT INTO finance_runs
                   (id,project_id,status,created_at,snapshot,scenario,manifest)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    run_id,
                    project_id,
                    "queued",
                    timestamp(),
                    encode(snapshot),
                    encode(scenario),
                    encode(manifest),
                ),
            )
        return self.run(project_id, run_id)

    def run(self, project_id, run_id):
        self.parent.project(project_id)
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM finance_runs WHERE id=? AND project_id=?",
                (run_id, project_id),
            ).fetchone()
        if row is None:
            raise NotFound()
        return self._decode(row)

    def runs(self, project_id):
        self.parent.project(project_id)
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM finance_runs WHERE project_id=? "
                "ORDER BY created_at DESC, rowid DESC",
                (project_id,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def start(self, run_id):
        with self.connection() as db:
            return bool(
                db.execute(
                    "UPDATE finance_runs SET status='running' WHERE id=? AND status='queued'",
                    (run_id,),
                ).rowcount
            )

    def finish(self, run_id, result=None, error=None):
        if (result is None) == (error is None):
            raise ValueError("Exactly one terminal outcome is required")
        with self.connection() as db:
            return bool(
                db.execute(
                    """UPDATE finance_runs SET status=?,result=?,error=?
                   WHERE id=? AND status IN ('queued','running')""",
                    (
                        "succeeded" if result is not None else "failed",
                        encode(result) if result is not None else None,
                        error,
                        run_id,
                    ),
                ).rowcount
            )

    def recover(self):
        with self.connection() as db:
            db.execute(
                """UPDATE finance_runs SET status='failed',result=NULL,error=?
                   WHERE status IN ('queued','running')""",
                (INTERRUPTED,),
            )


def _worker_environment():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
        }
    }
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "MLFLOW_DISABLE_TELEMETRY": "true",
        }
    )
    return environment


def register_finance(app, store, gate, pool):
    """Register finance routes on the guarded demo app and return startup recovery."""
    finance = FinanceStore(store)
    app.state.finance_store = finance

    def execute(run):
        try:
            if not finance.start(run["id"]):
                return
            run_dir = finance.root / "runs" / run["id"]
            run_dir.mkdir(parents=True, exist_ok=False)
            output_path = run_dir / "result.json"
            job_path = run_dir / "job.json"
            with job_path.open("x", encoding="utf-8") as job_file:
                job_file.write(
                    encode(
                        {
                            "snapshot": run["snapshot"],
                            "scenario": run["scenario"],
                            "output_path": str(output_path),
                        }
                    )
                )
            completed = subprocess.run(
                [sys.executable, "-m", "torii_demo.finance_engine", str(job_path)],
                cwd=store.root,
                env=_worker_environment(),
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode:
                raise RuntimeError("Finance worker failed")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            _Report.model_validate(result)
            # The exact queued inputs and code identity must match the process output.
            # Canonical encoding also rejects non-finite JSON numbers in any result.
            encode(result)
            for field in ("snapshot", "scenario", "manifest"):
                if encode(result[field]) != encode(run[field]):
                    raise ValueError("Finance result does not match its immutable envelope")
            finance.finish(run["id"], result=result)
        except subprocess.TimeoutExpired:
            finance.finish(run["id"], error=TIMED_OUT)
        except Exception:
            finance.finish(run["id"], error=FAILED)
        finally:
            gate.release()

    @app.get("/demo-api/finance/sample")
    def sample():
        return synthetic_snapshot()

    @app.get("/demo-api/projects/{project_id}/finance/runs")
    def runs(project_id: UUID):
        return finance.runs(str(project_id))

    @app.post("/demo-api/projects/{project_id}/finance/runs", status_code=202)
    def create_run(project_id: UUID, body: FinanceRunInput):
        project_id = str(project_id)
        store.project(project_id)
        if not gate.acquire(blocking=False):
            raise HTTPException(409, "Jedno wykonanie już trwa. Poczekaj na wynik.")
        run = None
        try:
            scenario = body.model_dump()
            snapshot = synthetic_snapshot(inject_issues=body.inject_issues)
            manifest = build_manifest(snapshot, scenario)
            run = finance.create_run(project_id, snapshot, scenario, manifest)
            pool.submit(execute, run)
        except Exception:
            try:
                if run is None:
                    raise
                finance.finish(run["id"], error=FAILED)
                return finance.run(project_id, run["id"])
            finally:
                gate.release()
        return run

    @app.get("/demo-api/projects/{project_id}/finance/runs/{run_id}")
    def run(project_id: UUID, run_id: UUID):
        return finance.run(str(project_id), str(run_id))

    @app.get("/demo-api/projects/{project_id}/finance/runs/{run_id}/export")
    def export(project_id: UUID, run_id: UUID):
        current = finance.run(str(project_id), str(run_id))
        if current["status"] != "succeeded":
            raise NotFound()
        return JSONResponse(
            current,
            headers={"Content-Disposition": f'attachment; filename="torii-finance-{run_id}.json"'},
        )

    return finance.recover
