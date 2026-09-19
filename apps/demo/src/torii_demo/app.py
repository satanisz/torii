"""SPEC-0018: local-only concept API. Not an authentication mode of torii_api."""

import base64
import binascii
import csv
import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from torii_demo.data import parse_csv, synthetic_data, transform
from torii_demo.store import NotFound, Store, encode

REPO = Path(__file__).resolve().parents[4]
LIMIT = 8 * 1024 * 1024
HOSTS = {"127.0.0.1:18440", "localhost:18440"}
ORIGINS = {"http://" + host for host in HOSTS}


class DemoGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope["headers"]
        }
        status, message = None, None
        if headers.get("host") not in HOSTS:
            status, message = 400, "Demo jest dostępne wyłącznie lokalnie."
        elif scope["method"] not in ("GET", "HEAD") and (
            headers.get("x-torii-demo") != "1"
            or ("origin" in headers and headers["origin"] not in ORIGINS)
        ):
            status, message = 403, "Niedozwolone źródło żądania demo."
        if status:
            return await JSONResponse({"detail": message}, status)(scope, receive, send)
        body = bytearray()
        if scope["method"] not in ("GET", "HEAD"):
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                body.extend(chunk.get("body", b""))
                if len(body) > LIMIT:
                    return await JSONResponse({"detail": "Plik przekracza limit8MiB."}, 413)(
                        scope, receive, send
                    )
                if not chunk.get("more_body"):
                    break

        async def buffered():
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        async def protected_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; "
                        b"style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        b"connect-src 'self'; object-src 'none'; frame-ancestors 'none'",
                    ),
                ]
            await send(message)

        await self.app(
            scope, buffered if scope["method"] not in ("GET", "HEAD") else receive, protected_send
        )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Named(StrictModel):
    name: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def meaningful_name(self):
        if not self.name.strip() or any(ord(char) < 32 for char in self.name):
            raise ValueError("invalid name")
        return self


class DatasetInput(Named):
    format: Literal["csv"]
    content_base64: str = Field(max_length=LIMIT)
    object_id: UUID | None = None


class TransformationInput(Named):
    input_version_id: UUID
    operation: Literal["drop_missing", "drop_duplicates", "select_columns", "filter_numeric"]
    columns: list[str] | None = Field(default=None, max_length=50)
    column: str | None = Field(default=None, max_length=100)
    operator: Literal["gte", "lte"] | None = None
    value: float | None = None


class ModelInput(Named):
    task: Literal["regression"]
    algorithm: Literal["linear", "dummy"]
    target: str = Field(min_length=1, max_length=100)
    features: list[str] = Field(min_length=1, max_length=50)
    alpha: float = Field(default=1, ge=0, le=100)

    @model_validator(mode="after")
    def distinct_features(self):
        if (
            len(set(self.features)) != len(self.features)
            or self.target in self.features
            or any(not feature or len(feature) > 100 for feature in self.features)
        ):
            raise ValueError("invalid features")
        return self


class RunInput(StrictModel):
    model_version_id: UUID
    dataset_version_id: UUID


def create_app(data_dir: Path, web_dir: Path | None = None):
    store = Store(data_dir)
    gate = threading.Lock()
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="torii-demo")

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        pool.shutdown(wait=True)

    app = FastAPI(
        title="Torii local concept demo",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/demo-api/openapi.json",
    )
    app.add_middleware(DemoGuard)
    app.state.store = store

    @app.exception_handler(NotFound)
    async def not_found(request, exc):
        return JSONResponse({"detail": "Nie znaleziono obiektu w tym projekcie."}, 404)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse(
            {"detail": "Niepoprawny formularz. Sprawdź wymagane pola i limity."}, 422
        )

    @app.exception_handler(ValueError)
    async def invalid_data(request, exc):
        return JSONResponse(
            {
                "detail": "Niepoprawne dane lub parametry transformacji. "
                "CSV: UTF-8, przecinek, unikalne kolumny, maks.5000 wierszy."
            },
            422,
        )

    @app.get("/demo-api/state")
    def state():
        return store.state()

    @app.post("/demo-api/projects", status_code=201)
    def projects(body: Named):
        return store.create_project(body.name)

    @app.post("/demo-api/projects/{project_id}/sample", status_code=201)
    def sample(project_id: UUID):
        return store.create_object(
            str(project_id),
            "dataset",
            "Dane syntetyczne — regresja",
            {"source": "synthetic"},
            synthetic_data(),
        )

    @app.post("/demo-api/projects/{project_id}/datasets", status_code=201)
    def datasets(project_id: UUID, body: DatasetInput):
        store.project(str(project_id))
        try:
            content = base64.b64decode(body.content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "Niepoprawny plik CSV.") from None
        return store.create_object(
            str(project_id),
            "dataset",
            body.name,
            {"source": "csv"},
            parse_csv(content),
            str(body.object_id) if body.object_id else None,
        )

    @app.post("/demo-api/projects/{project_id}/transformations", status_code=201)
    def transformations(project_id: UUID, body: TransformationInput):
        source = store.version(str(body.input_version_id), str(project_id), "dataset")
        definition = body.model_dump(mode="json", exclude={"name"}, exclude_none=True)
        transform(source["payload"], definition)  # Fail before persisting an unusable definition.
        return store.create_object(str(project_id), "transformation", body.name, definition)

    @app.post("/demo-api/transformations/{version_id}/execute", status_code=201)
    def execute_transform(version_id: UUID, body: StrictModel):
        transformation = store.version(str(version_id), kind="transformation")
        source = store.version(
            transformation["definition"]["input_version_id"],
            transformation["project_id"],
            "dataset",
        )
        output = transform(source["payload"], transformation["definition"])
        return store.create_object(
            transformation["project_id"],
            "dataset",
            transformation["name"] + " — wynik",
            {
                "source": "transformation",
                "input_version_id": source["id"],
                "transformation_version_id": str(version_id),
            },
            output,
        )

    @app.post("/demo-api/projects/{project_id}/models", status_code=201)
    def models(project_id: UUID, body: ModelInput):
        definition = body.model_dump(exclude={"name"}) | {"seed": 42, "test_size": 0.25}
        return store.create_object(str(project_id), "model", body.name, definition)

    def train(run_id, data, definition):
        try:
            store.update_run(run_id, "running")
            run_dir = store.root / "runs" / run_id
            run_dir.mkdir(parents=True)
            job = {
                "data": data,
                "definition": definition,
                "run_dir": str(run_dir),
                "tracking_uri": "sqlite:///" + (store.root / "mlflow.sqlite").as_posix(),
            }
            job_path = run_dir / "job.json"
            job_path.write_text(encode(job), encoding="utf-8")
            env = {
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
            env.update(
                {
                    "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "MLFLOW_DISABLE_TELEMETRY": "true",
                }
            )
            completed = subprocess.run(
                [sys.executable, "-m", "torii_demo.worker", str(job_path)],
                cwd=store.root,
                env=env,
                timeout=120,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode:
                raise RuntimeError("worker failed")
            result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            run = store.run(run_id)
            store.create_object(
                run["project_id"],
                "analysis",
                "Analiza " + run_id[:8],
                {
                    "run_id": run_id,
                    "input_version_id": run["dataset_version_id"],
                    "model_version_id": run["model_version_id"],
                },
            )
            store.update_run(run_id, "succeeded", result)
        except Exception:
            store.update_run(
                run_id,
                "failed",
                error="Eksperyment nie powiódł się. "
                "Wymagane: co najmniej 20 wierszy, liczbowe cechy i pełna kolumna celu; "
                "czas obliczeń do 120 s. Sprawdź też dostępność lokalnego magazynu MLflow.",
            )
        finally:
            gate.release()

    @app.post("/demo-api/projects/{project_id}/runs", status_code=202)
    def runs(project_id: UUID, body: RunInput):
        model = store.version(str(body.model_version_id), str(project_id), "model")
        dataset = store.version(str(body.dataset_version_id), str(project_id), "dataset")
        if not gate.acquire(blocking=False):
            raise HTTPException(409, "Jedno wykonanie już trwa. Poczekaj na wynik.")
        try:
            run = store.create_run(str(project_id), model["id"], dataset["id"])
            pool.submit(train, run["id"], dataset["payload"], model["definition"])
            return run
        except Exception:
            gate.release()
            raise

    @app.get("/demo-api/runs/{run_id}/artifacts/{name}")
    def artifact(run_id: UUID, name: str):
        run = store.run(str(run_id))
        if (
            name not in {"model.joblib", "result.json", "environment.json"}
            or run["status"] != "succeeded"
        ):
            raise NotFound()
        path = store.root / "runs" / str(run_id) / name
        if not path.is_file():
            raise NotFound()
        return FileResponse(path, media_type="application/octet-stream", filename=name)

    @app.get("/demo-api/datasets/{version_id}/csv")
    def download_csv(version_id: UUID):
        data = store.version(str(version_id), kind="dataset")["payload"]

        def safe(value):
            if isinstance(value, str) and value.lstrip().startswith(
                ("=", "+", "-", "@", "\t", "\r")
            ):
                return "'" + value
            return value

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow([safe(column) for column in data["columns"]])
        writer.writerows([safe(row[column]) for column in data["columns"]] for row in data["rows"])
        return Response(
            output.getvalue().encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="dataset.csv"'},
        )

    @app.get("/demo-api/projects/{project_id}/export")
    def export(project_id: UUID):
        return JSONResponse(
            store.export(str(project_id)),
            headers={"Content-Disposition": 'attachment; filename="torii-manifest.json"'},
        )

    static = web_dir or REPO / "apps" / "web" / "dist"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/torii-logo.jpg")
    def logo():
        return FileResponse(REPO / "apps" / "web" / "public" / "torii-logo.jpg")

    @app.get("/")
    @app.get("/demo.html")
    def index():
        if not (static / "demo.html").is_file():
            raise HTTPException(503, "Najpierw zbuduj frontend: npm run build w apps/web.")
        return FileResponse(static / "demo.html")

    return app
