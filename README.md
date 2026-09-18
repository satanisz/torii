# Torii

Torii is the product name for the planned modular data, analytics and model
platform. This repository currently contains its working AutoML workshop
foundation; the unified UI and object-management API are not implemented yet.
The repository is https://github.com/satanisz/torii.

**Upgrading an existing installation?** Read
[the Torii rename and Docker migration guide](docs/torii-migration.md) before
starting Compose. A new `torii` Compose project uses new volumes by default;
the optional migration override reuses explicitly selected existing volumes.

On the migrated workstation, the ignored `.env` selects the demo and external
volumes automatically. Use `docker compose up -d` / `docker compose ps` there;
see [local installation](docs/local-installation.md). Explicit `-f` arguments
override that selection and must include the legacy-volume override.

The current foundation provides reproducible Python and AutoML workspaces with
JupyterLab, code-server, `uv`, MLflow, PostgreSQL, MinIO and a data-science
project scaffold. It uses only public images and package repositories, so it
can be reviewed and built on a normal developer laptop before corporate
registry integration begins.

## Image matrix

One canonical Dockerfile produces 12 standard workspace images:

| Python | `vanilla` | `ml-standard` | `ml-max` |
|---|---:|---:|---:|
| 3.9 | `py3.9-vanilla` | `py3.9-ml-standard` | `py3.9-ml-max` |
| 3.10 | `py3.10-vanilla` | `py3.10-ml-standard` | `py3.10-ml-max` |
| 3.11 | `py3.11-vanilla` | `py3.11-ml-standard` | `py3.11-ml-max` |
| 3.12 | `py3.12-vanilla` | `py3.12-ml-standard` | `py3.12-ml-max` |

Profiles are defined in `docker/requirements`:

- `vanilla`: JupyterLab and a Python kernel;
- `ml-standard`: practical CPU stack for tabular ML, statistics, visualization,
  tracking, ONNX and CPU-only PyTorch;
- `automl-tabular`: AutoGluon, MLflow and the dependencies required for the
  local AutoML demonstration; supported on Python 3.10-3.12;
- `ml-max`: deduplicated union of every package listed in
  `docker/requirements/catalogs`.

The files in `docker/requirements/catalogs` are the repository-owned source
catalogs used to regenerate `ml-max.txt`. External notes and archived source
material are intentionally kept outside this repository.

`ml-max` is intentionally broad. It is useful for compatibility experiments,
but it should not automatically become the bank-wide default: it will be large,
slower to patch and more likely to contain packages irrelevant to most users.

## Build one image

Windows PowerShell:

```powershell
.\scripts\build-matrix.ps1 -PythonVersion 3.12 -Profile ml-standard
```

Linux/macOS/Git Bash:

```bash
PYTHON_VERSION=3.12 PROFILE=ml-standard ./scripts/build-matrix.sh
```

Equivalent direct command:

```bash
docker build -f docker/Dockerfile \
  --build-arg PYTHON_VERSION=3.12 \
  --build-arg PROFILE=ml-standard \
  -t torii/workspace:py3.12-ml-standard .
```

Build all 12 images sequentially on a normal laptop:

```powershell
.\scripts\build-matrix.ps1 -All
```

Docker Bake can build the matrix concurrently on stronger CI infrastructure:

```bash
docker buildx bake
```

Build only one profile across all Python versions with `docker buildx bake
vanilla`, `docker buildx bake ml-standard` or `docker buildx bake ml-max`.

For a laptop, the sequential PowerShell script is recommended because the ML
profiles download large, Python-specific binary wheels.

## Run locally

JupyterLab uses its normal token authentication and prints the URL in the
container log:

```bash
docker run --rm -p 8888:8888 \
  -v torii-workspace:/workspace \
  torii/workspace:py3.12-ml-standard
```

code-server generates a one-time password and prints it in the log:

```bash
docker run --rm -p 8080:8080 \
  -e WORKSPACE_IDE=code-server \
  -v torii-workspace:/workspace \
  torii/workspace:py3.12-ml-standard
```

For a fixed local code-server password, also pass
`-e WORKSPACE_AUTH_MODE=password -e PASSWORD=<value>`. Authentication can be
disabled with `WORKSPACE_AUTH_MODE=external` only when a trusted platform proxy
already authenticates every request.

Docker Compose provides the same default setup:

```bash
docker compose up --build
```

## Safe scaffold initialization

The template is stored read-only at `/opt/torii/scaffold`. On container start:

1. an empty `/workspace` receives the project structure;
2. a non-empty, unmarked `/workspace` is left untouched;
3. a version marker makes later starts idempotent;
4. an interrupted first copy is resumed without overwriting existing files;
5. an explicitly increased scaffold version adds missing files to a marked
   workspace, preserving existing files. Compose uses version `3` to add the
   `torii_project` package to older AutoML workspaces.

The structure follows the useful ideas from Cookiecutter Data Science—separate
raw/interim/processed data, notebooks, reusable `src`, models, reports and
tests—but it is deliberately smaller and deterministic. It does not ask
interactive Cookiecutter questions when a pod starts.

## Package changes inside a container

The virtual environment is writable by the non-root user (`1001:1001`):

```bash
uv pip uninstall pandas
uv pip install pandas
```

Those changes live only as long as the container unless `/opt/venv` is mounted
separately. Project dependencies should normally be declared in the generated
`pyproject.toml` and persisted with the workspace.

## Validation

```bash
python scripts/generate-ml-max.py --check
bash tests/test-scaffold.sh
bash tests/smoke-test.sh torii/workspace:py3.12-ml-standard
```

Windows service test:

```powershell
.\tests\test-services.ps1 -Image torii/workspace:py3.12-vanilla
```

See `docs/validation.md` for the local test report and `docs/architecture.md`
for design choices, limitations and the path toward private registries, locked
dependencies and Kubernetes.

## Local AutoML and model-management MVP

From this directory, start the complete local stack:

```powershell
docker compose -f compose.demo.yaml up --build
```

It starts a Torii JupyterLab workspace, MLflow, PostgreSQL, MinIO and DataHub.
The local DataHub backend also includes MySQL, OpenSearch, Kafka and Schema
Registry; these supporting services are not exposed on host ports.

### Local services

| Service | Address | Local access |
|---|---|---|
| JupyterLab | <http://localhost:8888> | token `torii-local-dev` |
| MLflow | <http://localhost:5000> | no login |
| MinIO console | <http://localhost:9001> | `minioadmin` / `minioadmin` |
| DataHub | <http://localhost:9002> | `datahub` / `datahub` |
| DataHub health API | <http://localhost:8081/health> | no login in the local MVP |

The initialization containers `create-bucket` and `datahub-system-update` end
with `Exited (0)` after their work is complete. That is the expected state, not
a failure. The public application endpoints should return HTTP 200 after the
stack becomes ready.

### What is validated by the reference run

The end-to-end MVP has been checked with an AutoGluon training run that:

- compares tabular-model candidates and registers
  `automl-breast-cancer-classifier` in MLflow;
- assigns the newest registered version the `candidate` alias and reloads it in
  a separate batch-inference step;
- stores a raw CSV snapshot, processed Parquet snapshot, transformation manifest
  and prediction output in MinIO;
- catalogs datasets, MLflow runs and model versions in DataHub;
- records lineage `raw -> processed -> predictions`;
- verifies the Compose configuration, scaffold initialization, Python
  compilation and linting of the MVP modules.

The exact model-version number changes with every new run. In the initial
reference validation, version `3` was `READY` and assigned alias `candidate`.

### Persistent services and their roles

| Element | Role |
|---|---|
| PostgreSQL | MLflow experiments, metrics and Model Registry metadata |
| MinIO | Data snapshots, artifacts and model packages |
| MySQL | DataHub source-of-truth catalog metadata |
| OpenSearch | DataHub search and lineage graph index |
| Kafka | DataHub metadata-change events |
| Schema Registry | Schemas for Kafka metadata events |
| Docker workspace volume | Notebooks, source code and reports in `/workspace` |

Transformations do not need a separate database. The Torii Python pipeline
performs them, stores the resulting dataset and manifest in MinIO, logs the data
reference in MLflow, and publishes the data relationship to DataHub.

Open JupyterLab, then execute the end-to-end data validation, transformation,
AutoML, registry, batch-inference and catalog pipeline in a Jupyter terminal:

```bash
python -m torii_project.automl.mvp 120
```

Open MLflow to inspect the run and registered `candidate` model, MinIO to inspect
data and artifacts, and DataHub to inspect catalog metadata and lineage.

See [docs/automl-mvp.md](docs/automl-mvp.md) for prerequisites, the architecture,
startup instructions and an exact map of what to inspect in each interface.
The hands-on Polish workshop guide is available in
[docs/automl-workshops.md](docs/automl-workshops.md).

To use the same workspace with code-server rather than JupyterLab, use the
optional override and open `http://localhost:8080` with password
`torii-local-dev`:

```powershell
docker compose -f compose.demo.yaml -f compose.vscode.yaml up --build
```

This is a local development stack only. Replace the default credentials before
sharing it or exposing any port outside the development machine.
