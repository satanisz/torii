# AutoML to Torii

The product and repository are now named **Torii**. The current application
remains the AutoML workshop foundation. This rename does not implement the
planned catalog of objects, GUI, Git integration or production deployment flow.

## New names

| Element | Current name |
|---|---|
| Repository | `https://github.com/satanisz/torii` |
| Compose project | `torii` (explicit in both base Compose files) |
| Complete demo | `compose.demo.yaml` |
| Optional code-server override | `compose.vscode.yaml` |
| Workspace images | `torii/workspace:py<version>-<profile>` |
| Container user and scaffold | `torii`, `/opt/torii/scaffold` |
| Scaffold Python package | `torii_project` |
| Environment metadata | `TORII_PROFILE`, `TORII_PYTHON`, `TORII_DATA_BUCKET` |

`automl-tabular` is still the profile name: it describes the AutoML capability.
Likewise, the `automl` Python subpackage, notebook names and workshop filenames
still describe that feature, not the product name.

The old `automl_project` namespace is provided for compatibility with notebook
imports and saved Python model references. Existing workspace files are never
overwritten. Compose requests scaffold version `3`, which adds missing Torii
files to previously initialized workspaces. Existing notebooks can continue to
use their old imports; new examples use `torii_project`.

## Persistent identifiers retained intentionally

The MinIO bucket `automl-data`, MLflow experiments `automl-demo` and
`automl-end-to-end-mvp`, and registry model `automl-breast-cancer-classifier`
retain their names. Renaming them would split history or invalidate stored URIs.
The `.automl-scaffold-version` / `.automl-scaffold-in-progress` marker filenames
and the local DataHub token salt also retain their existing values.

The Docker image still exposes `AUTOML_PROFILE` and `AUTOML_PYTHON` alongside the
new variables. Demo Compose also sets `AUTOML_DATA_BUCKET` for old workspace
code. The new Python code accepts the legacy variable names as fallbacks.
UID/GID remain `1001:1001`, preserving file ownership compatibility.

## Fresh installation

```powershell
docker compose -f compose.demo.yaml up --build -d
docker compose -f compose.demo.yaml exec workspace python -m torii_project.automl.mvp 120
```

The default Jupyter token and code-server password are now `torii-local-dev`.
Existing environment overrides for these credentials still take precedence.
New volumes have the `torii_` project prefix. The simple `compose.yaml` and
complete demo use the same project name and workspace volume; use one mode at
a time. Rebuild the image to apply the package and container-user rename.

## Existing Docker data

Changing a folder, Git repository, image tag or container name does not rename
Docker volumes. Do not use `down -v` or prune volumes during this migration.

First inspect the actual old project and storage:

```powershell
docker compose ls --all
docker ps -a --format '{{.Names}}'
docker volume ls
docker inspect OLD_WORKSPACE_CONTAINER --format '{{json .Mounts}}'
```

Inspect mounts of the old PostgreSQL, MinIO, Kafka, MySQL and OpenSearch
containers too. Do not infer volume names from the new folder name. Historical
installations may have used `automl`, `docker-images-ml`, or an explicit `-p`.
Before switching, stop the identified old stack and back up its state. Old and
new database containers must not use the same data volumes concurrently.

Copy the template below to a local `.env` file and replace **every value** with
the exact existing volume name obtained above. `.env` is ignored by Git.

```dotenv
TORII_LEGACY_POSTGRES_VOLUME=REPLACE_WITH_EXISTING_POSTGRES_VOLUME
TORII_LEGACY_MINIO_VOLUME=REPLACE_WITH_EXISTING_MINIO_VOLUME
TORII_LEGACY_WORKSPACE_VOLUME=REPLACE_WITH_EXISTING_WORKSPACE_VOLUME
TORII_LEGACY_KAFKA_VOLUME=REPLACE_WITH_EXISTING_KAFKA_VOLUME
TORII_LEGACY_MYSQL_VOLUME=REPLACE_WITH_EXISTING_MYSQL_VOLUME
TORII_LEGACY_OPENSEARCH_VOLUME=REPLACE_WITH_EXISTING_OPENSEARCH_VOLUME
```

Then validate and start Torii using both files:

```powershell
docker compose -f compose.demo.yaml -f compose.legacy-volumes.yaml config --quiet
docker compose -f compose.demo.yaml -f compose.legacy-volumes.yaml up --build -d
```

Keep using both files for subsequent `up`, `down`, `ps`, and `exec` commands.
The override declares external volumes: missing names fail instead of creating
empty replacement storage. Existing physical volume names remain unchanged;
the containers and network belong to the new Torii Compose project.

If the previous installation only used the simple workspace Compose file,
set `TORII_LEGACY_WORKSPACE_VOLUME` and use the workspace-only override:

```powershell
docker compose -f compose.yaml -f compose.legacy-workspace.yaml up --build -d
```

Inspect the old mount before selecting it and stop its old container first.

After starting, verify the historical MLflow runs, MinIO objects, DataHub
catalog and user workspace files.

## FrameML installations

The initializer also recognizes `.frameml-scaffold-version` and adds the new
Torii files without replacing existing FrameML code or metadata. Preserve the
old `frameml_project` package in that workspace: existing saved models can
reference its classes.

Set the following local environment values to retain FrameML history:

```dotenv
TORII_DATA_BUCKET=frameml-data
TORII_EXPERIMENT_NAME=frameml-end-to-end-mvp
TORII_DEMO_EXPERIMENT_NAME=frameml-automl-demo
TORII_REGISTERED_MODEL_NAME=frameml-breast-cancer-classifier
DATAHUB_TOKEN_SERVICE_SALT=frameml-local-datahub-salt
```

The bucket-creation step and new DataHub recipe use `TORII_DATA_BUCKET`. The
old FrameML code receives `FRAME_ML_DATA_BUCKET` and `FRAME_ML_PROFILE` too.
These names are installation compatibility settings, not renames of historical
datasets or experiments. The completed local migration is documented in
[local-installation.md](local-installation.md).

## Local verification

The following checks do not need a running Docker engine:

```powershell
docker compose -f compose.demo.yaml config --quiet
docker compose -f compose.demo.yaml -f compose.vscode.yaml config --quiet
docker buildx bake --print
python scripts/generate-ml-max.py --check
python -m unittest discover -s tests -p 'test_compatibility.py'
```

In a Linux shell (or Git Bash with compatible coreutils), also run
`bash tests/test-scaffold.sh`. Building images, smoke tests, service tests and
checking existing volumes require a running Docker engine.
