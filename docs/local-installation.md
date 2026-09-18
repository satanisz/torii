# Local Torii installation — 2026-09-19

Torii now runs the existing FrameML workshop data. The original
`docker-images-ml` containers are stopped and retained. Other Docker projects
were not changed. The application remains the workshop stack; the future Torii
unified GUI has not been implemented yet.

## Daily commands

Run from `C:\Users\stani\Projects\frame-ml\torii`:

```powershell
docker compose up -d
docker compose ps -a
docker compose logs -f workspace
docker compose stop
```

The local `.env` (ignored by Git) sets `COMPOSE_FILE` to `compose.demo.yaml`
plus `compose.legacy-volumes.yaml`, using an explicit comma separator.
It maps all six external volumes and preserves FrameML bucket/model names.
Keep this file when restarting. Explicit `-f` flags override `COMPOSE_FILE`;
always include the legacy override if using explicit files on this machine.

Rebuild after source or Dockerfile changes with `docker compose build`, then
`docker compose up -d`. To enable code-server on this installation:

```powershell
docker compose -f compose.demo.yaml -f compose.legacy-volumes.yaml -f compose.vscode.yaml up -d
```

Port 8080 is currently used by the separate Airflow project. To enable
code-server alongside it, first configure another host port in the override.
The optional code-server image functionality was verified separately on port
18080; the normal running workspace uses JupyterLab.

## Interfaces

| Interface | Address | Local access |
|---|---|---|
| JupyterLab | http://localhost:8888 | token `torii-local-dev` |
| MLflow | http://localhost:5000 | no login |
| MinIO | http://localhost:9001 | `minioadmin` / `minioadmin` |
| DataHub | http://localhost:9002 | `datahub` / `datahub` |

## Storage and history

Physical volume names retain the old prefix to preserve data:

| Torii volume | Existing physical volume |
|---|---|
| torii-postgres | docker-images-ml_frameml-automl-postgres |
| torii-minio | docker-images-ml_frameml-automl-minio |
| torii-workspace | docker-images-ml_frameml-automl-workspace |
| torii-datahub-kafka | docker-images-ml_frameml-datahub-kafka |
| torii-datahub-mysql | docker-images-ml_frameml-datahub-mysql |
| torii-datahub-opensearch | docker-images-ml_frameml-datahub-opensearch |

MLflow retains `frameml-automl-demo`, `frameml-end-to-end-mvp`, 5 existing runs
and versions 1–3 of `frameml-breast-cancer-classifier`. New Torii demo code uses
these names via environment configuration. Data remains in `frameml-data` and
model artifacts in `mlflow`. Original notebooks and all 57 original workspace
files remain byte-for-byte unchanged; the Torii modules were added alongside.

Backup directory:
`C:\Users\stani\Projects\frame-ml\backups\torii-migration-20260919`.
It contains six compressed volume archives and a README with SHA-256 hashes
and recovery notes. Do not start the retained old stack against these same
live volumes. For a rollback to the exact pre-migration state, restore the
archives into separate empty volumes while services are stopped.

## Verified

The running stack's JupyterLab, MLflow, MinIO and DataHub endpoints returned
HTTP 200. Model version 3 reproduced all 569 saved predictions exactly.
Existing DataHub dataset metadata and upstream lineage were readable.
See [validation.md](validation.md) for the complete scope of checks.
