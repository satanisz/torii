"""SPEC-0018 D01/D02/D04: local immutable snapshots, no enterprise ACL claims."""

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def timestamp():
    return datetime.now(UTC).isoformat()


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


class NotFound(Exception):
    pass


class Store:
    def __init__(self, root: Path):
        self._lock = threading.RLock()
        self.root = root.resolve()
        marker = self.root / "torii-demo-v1"
        if self.root.exists() and any(self.root.iterdir()) and not marker.is_file():
            raise RuntimeError(
                "Demo requires an empty directory or its own existing data directory"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        marker.touch(exist_ok=True)
        self.database = self.root / "torii.sqlite"
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,
              project_id TEXT REFERENCES projects,
              kind TEXT,name TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,
              object_id TEXT REFERENCES objects,
              number INTEGER,definition TEXT,payload TEXT,sha256 TEXT,created_at TEXT,
              UNIQUE(object_id,number));
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects,
              model_version_id TEXT REFERENCES versions,dataset_version_id TEXT REFERENCES versions,
              status TEXT,result TEXT,error TEXT,created_at TEXT);
            """)

    @contextmanager
    def connection(self):
        with self._lock:
            db = sqlite3.connect(self.database, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                with db:
                    yield db
            finally:
                db.close()

    def project(self, project_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise NotFound()
        return dict(row)

    def create_project(self, name):
        project = {"id": str(uuid4()), "name": name, "created_at": timestamp()}
        with self.connection() as db:
            db.execute("INSERT INTO projects VALUES (:id,:name,:created_at)", project)
        return project

    def version(self, version_id, project_id=None, kind=None):
        with self.connection() as db:
            row = db.execute(
                """SELECT v.*,o.project_id,o.kind,o.name FROM versions v
                JOIN objects o ON o.id=v.object_id WHERE v.id=?""",
                (version_id,),
            ).fetchone()
        if (
            row is None
            or (project_id and row["project_id"] != project_id)
            or (kind and row["kind"] != kind)
        ):
            raise NotFound()
        result = dict(row)
        result["definition"] = json.loads(result["definition"])
        result["payload"] = json.loads(result["payload"])
        return result

    def create_object(self, project_id, kind, name, definition, payload=None, object_id=None):
        self.project(project_id)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if object_id:
                previous = db.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
                if (
                    previous is None
                    or previous["project_id"] != project_id
                    or previous["kind"] != kind
                ):
                    raise NotFound()
            else:
                object_id = str(uuid4())
                db.execute(
                    "INSERT INTO objects VALUES (?,?,?,?,?)",
                    (object_id, project_id, kind, name, timestamp()),
                )
            number = db.execute(
                "SELECT COALESCE(MAX(number),0)+1 FROM versions WHERE object_id=?", (object_id,)
            ).fetchone()[0]
            digest = hashlib.sha256(
                encode({"definition": definition, "payload": payload}).encode()
            ).hexdigest()
            db.execute(
                "INSERT INTO versions VALUES (?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    object_id,
                    number,
                    encode(definition),
                    encode(payload),
                    digest,
                    timestamp(),
                ),
            )
        return self.object(object_id)

    def object(self, object_id):
        with self.connection() as db:
            obj = db.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
            versions = db.execute(
                "SELECT * FROM versions WHERE object_id=? ORDER BY number", (object_id,)
            ).fetchall()
        if obj is None:
            raise NotFound()
        result = dict(obj)
        result["versions"] = []
        for row in versions:
            version = dict(row)
            payload = json.loads(version.pop("payload"))
            version.pop("object_id")
            version["definition"] = json.loads(version["definition"])
            version["summary"] = (
                {
                    "columns": payload["columns"],
                    "row_count": payload["row_count"],
                    "profile": payload["profile"],
                    "preview": payload["rows"][:20],
                }
                if obj["kind"] == "dataset"
                else {}
            )
            result["versions"].append(version)
        return result

    def create_run(self, project_id, model_version_id, dataset_version_id):
        run_id = str(uuid4())
        with self.connection() as db:
            db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    project_id,
                    model_version_id,
                    dataset_version_id,
                    "queued",
                    "{}",
                    None,
                    timestamp(),
                ),
            )
        return self.run(run_id)

    def run(self, run_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise NotFound()
        result = dict(row)
        result["result"] = json.loads(result["result"]) or None
        model = self.version(result["model_version_id"])["definition"]
        result.update({key: model[key] for key in ("target", "seed", "test_size")})
        return result

    def update_run(self, run_id, status, result=None, error=None):
        with self.connection() as db:
            db.execute(
                "UPDATE runs SET status=?,result=?,error=? WHERE id=?",
                (status, encode(result or {}), error, run_id),
            )

    def recover(self):
        with self.connection() as db:
            db.execute(
                "UPDATE runs SET status='failed',error=? WHERE status IN ('queued','running')",
                ("Proces demo został przerwany. Uruchom eksperyment ponownie.",),
            )

    def state(self):
        # A completed run and its earlier-created analysis must be observed together.
        # One local API process; never hold this lock while computing in the worker.
        with self._lock:
            return self._state()

    def _state(self):
        with self.connection() as db:
            projects = [
                dict(row) for row in db.execute("SELECT * FROM projects ORDER BY created_at")
            ]
            objects = [row[0] for row in db.execute("SELECT id FROM objects ORDER BY created_at")]
            runs = [row[0] for row in db.execute("SELECT id FROM runs ORDER BY created_at")]
        return {
            "mode": "local-demo",
            "projects": projects,
            "objects": [self.object(item) for item in objects],
            "runs": [self.run(item) for item in runs],
        }

    def export(self, project_id):
        project = self.project(project_id)
        state = self.state()
        objects = []
        for obj in state["objects"]:
            if obj["project_id"] == project_id:
                objects.append(
                    {
                        **obj,
                        "versions": [
                            {key: value for key, value in version.items() if key != "summary"}
                            for version in obj["versions"]
                        ],
                    }
                )
        runs = [
            {
                **run,
                "result": {
                    key: value
                    for key, value in (run["result"] or {}).items()
                    if key
                    in {
                        "metrics",
                        "environment",
                        "mlflow_run_id",
                        "algorithm",
                        "train_rows",
                        "test_rows",
                    }
                },
            }
            for run in state["runs"]
            if run["project_id"] == project_id
        ]
        return {
            "format": "torii-demo-manifest-v1",
            "project": project,
            "objects": objects,
            "runs": runs,
            "note": "Definicje i metryki; bez danych i modeli. Nie jest pełnym replay bundle.",
        }
