# Architecture and review notes

## Purpose and boundary

This repository is a portable proof of concept, not a production-approved
bank image. It deliberately starts from public sources so the image behavior
can be reviewed independently of Jenkins, Kubernetes and private registries.

The later corporate adaptation should replace image and package sources,
provide certificates and credentials only at build time, generate per-Python
locks, scan/sign the outputs and run them under the platform security policy.

## Why one Dockerfile creates 12 images

An image is the output of a build, not the Dockerfile itself. Python and profile
are explicit build arguments. Each pair receives a separate immutable tag, while
the common operating-system, IDE and security logic remains in one place.

Duplicating 12 Dockerfiles would make review easy at first but would require the
same security change to be repeated 12 times. The included `docker-bake.hcl`
makes the complete output matrix visible without that maintenance risk.

## Profile policy

`vanilla` is the smallest interactive baseline. `ml-standard` is the proposed
starting point for typical tabular ML and statistical work. `ml-max` is generated
from `docker/requirements/catalogs` by package name; where both constrained and
unconstrained forms exist, the constrained form wins. These catalogs are the
sanitized, repository-owned inputs; archival source material remains outside the
project repository.

The profile manifests contain direct dependencies, not fully reproducible
transitive locks. Before production, resolve and review one lock per profile and
Python minor version. That produces 12 lock files and makes rebuild behavior
auditable even when public/private package indexes change.

CPU-only PyTorch is installed first from the official PyTorch CPU index. The
remaining dependencies are then installed from PyPI. This ordering also stops a
package such as `stable-baselines3` from introducing a CUDA-enabled Linux wheel
as a transitive dependency. The build asserts `torch.version.cuda is None`.
The PyTorch family is constrained to official compatible release sets: 2.8 for
Python 3.9 and 2.11 for Python 3.10-3.12. `ml-max` additionally verifies that
TorchAudio and PyTorch have the same release version.
The Linux `xgboost` requirement is fulfilled by the official `xgboost-cpu`
distribution (the Python import remains `xgboost`) to avoid its NCCL dependency.
The build also rejects any installed distribution whose name starts with
`nvidia-`.

Python 3.9 constrains NumPy below 2. Local testing found that its compatible
PyTables wheel otherwise passes metadata checks but fails at import time due to
a NumPy ABI mismatch. The build therefore performs a real PyTables import when
that package is requested.

Some names collected from conda have a different PyPI distribution name. The
generator keeps explicit aliases; currently `jupyterlab-variableinspector` maps
to `lckr-jupyterlab-variableinspector`.

## Workspace lifecycle

The scaffold source lives at `/opt/torii/scaffold`, outside the persistent
workspace. Initialization is intentionally conservative:

- marker present with the requested version: do nothing;
- marker present with another explicitly requested version: add missing files
  without overwriting user files;
- workspace contains a user file: do nothing;
- workspace is empty: copy the scaffold without replacement;
- interrupted copy marker present: resume missing files, never replace files.

This lets Kubernetes mount a new PVC at `/workspace` without hiding the template
and protects an existing project from file replacement during an image upgrade.
The requested `SCAFFOLD_VERSION` controls additive migration. Compose version `3`
adds the Torii package; the historical marker filename remains compatible.

## Runtime and security defaults

- process runs as UID/GID `1001`, not root;
- JupyterLab retains its built-in token locally;
- code-server uses a generated or explicitly supplied password;
- disabling IDE authentication is explicit and intended only behind an
  authenticating reverse proxy;
- `uv` remains available and `/opt/venv` is owned by the runtime user;
- build credentials are not needed in this public concept and must never be
  copied into a later corporate image.

## Known limitations for review

- `ml-max` is very large and is likely inappropriate as the default image.
- Python 3.9 receives older compatible package releases and has a shorter useful
  lifecycle than 3.11/3.12.
- exact base-image digests and dependency locks are intentionally deferred until
  the first successful compatibility builds.
- GPU support is out of scope until CUDA version, driver contract, node type and
  Kubernetes GPU runtime are confirmed.
- the repository does not choose a software license on behalf of the owning
  organization.
- local validation currently covers Linux/amd64; multi-architecture images have
  not yet been tested.

## Upstream references

- [Docker Official Image for Python](https://hub.docker.com/_/python)
- [uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/)
- [uv with PyTorch](https://docs.astral.sh/uv/guides/integration/pytorch/)
- [PyTorch previous versions and CPU wheels](https://pytorch.org/get-started/previous-versions/)
- [code-server releases](https://github.com/coder/code-server/releases)
- [XGBoost installation variants](https://xgboost.readthedocs.io/en/stable/install.html)
- [Cookiecutter Data Science documentation](https://cookiecutter-data-science.drivendata.org/)
