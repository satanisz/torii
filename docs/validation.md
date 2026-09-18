# Local validation report

## Torii rename — 2026-09-19

The renamed base/demo/IDE Compose configurations and all 12 Bake image tags
were validated without a Docker engine. Legacy-volume overrides were checked
for explicit external-volume mappings and rejection of missing configuration.
Python 3.12 scaffold and compatibility tests passed (3 tests, 4 subtests).
Git Bash scaffold tests passed, including an AutoML v2 to Torii v3 upgrade
that preserves existing user code and project metadata.

The first attempt was blocked by Docker Desktop startup. After the user started
the engine, migration and runtime validation completed on the same date:

- Built `torii/workspace:py3.12-automl-tabular` and `torii-mlflow:latest`.
- Fixed CRLF handling in dependency manifests: the Linux build now normalizes
  line endings before matching the CPU-only PyTorch requirements.
- Verified PyTorch `2.11.0+cpu`, no CUDA, and dependency consistency.
- Backed up all six existing FrameML volumes while the old stack was stopped;
  all six gzip/tar archives were readable and SHA-256 hashes recorded.
- Started the `torii` Compose project using those exact external volumes.
- Preserved 3 MLflow experiments, 5 runs and model versions 1, 2, 3 (READY).
- Loaded the existing version 3 model and reproduced all 569 saved predictions
  exactly, without training or registering another model.
- Compared all 57 original workspace files with the backup: contents unchanged.
- Confirmed the existing DataHub processed dataset and its upstream lineage.
- JupyterLab, MLflow, MinIO console, DataHub UI and DataHub health returned 200.
- Fresh-image smoke tests and both Jupyter/code-server HTTP tests passed with
  UID 1001. Temporary test containers were removed by the test script.

Only the Python 3.12 AutoML profile was rebuilt; the report below describes the
original full matrix, not a new validation of every Torii image profile.
See [this workstation's configuration](local-installation.md) for commands and
the backup location.

## Original image validation

Validation date: 2026-08-05

Platform: Docker Desktop, Linux/amd64 containers on Windows

## Result

All 12 image tags were built locally:

- Python 3.9, 3.10, 3.11 and 3.12;
- `vanilla`, `ml-standard` and `ml-max` for every Python version.

Every tag passed the scaffold and tool smoke test. Both IDEs were also started
as real containers: authenticated JupyterLab returned HTTP 200 and code-server
returned HTTP 200 from its health endpoint. Both services ran as UID 1001.

Approximate logical compressed sizes reported by `docker image inspect` for
Python 3.12 were 447 MB (`vanilla`), 1.23 GB (`ml-standard`) and 1.51 GB
(`ml-max`). Other Python tags are in a similar range.

The ML tests verified:

- CPU-only PyTorch (`torch.version.cuda is None`);
- no installed distribution whose name starts with `nvidia-`;
- Torch, Torchvision and, in `ml-max`, Torchaudio compatibility;
- imports for XGBoost, pandas, scikit-learn, statsmodels, Transformers,
  Stable-Baselines3, QuantLib and PyTables.

The persistent workspace test confirmed that a user-modified file is not
overwritten on a later container start. An ephemeral container also confirmed
that UID 1001 can uninstall a package from `/opt/venv`.

## Compatibility discovered by testing

Python 3.9 uses PyTorch 2.8, while Python 3.10-3.12 use PyTorch 2.11. Python 3.9
also constrains NumPy below 2 because the compatible PyTables wheel otherwise
loads against an incompatible NumPy ABI. The Docker build performs a real
PyTables import so this cannot pass unnoticed.

Package versions can differ between Python tags because the manifests are
ranges rather than production lock files. The next production-hardening step
is to generate and review 12 locks: one per Python/profile pair.

## Reproduce

```powershell
.\scripts\build-matrix.ps1 -PythonVersion 3.12 -Profile ml-standard
bash .\tests\smoke-test.sh torii/workspace:py3.12-ml-standard
.\tests\test-services.ps1 -Image torii/workspace:py3.12-vanilla
```

For a laptop, build images sequentially with `build-matrix.ps1`. A parallel
`docker buildx bake` is faster on capable CI infrastructure but may create
several simultaneous large downloads from the PyTorch index.
