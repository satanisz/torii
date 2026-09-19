# Torii FastAPI control plane

SPEC-0001 and SPEC-0002. This initial increment provides configuration, HTTP
envelope, pure domain rules, health checks and a PostgreSQL migration. Product
routes (OIDC/session/projects) are intentionally not yet connected; no fake
identity or in-memory data store stands in for them.

Run from this directory with uv 0.11.19 and Python 3.12:

```powershell
uv sync --frozen
uv run --frozen ruff check src tests migrations
uv run --frozen ruff format --check src tests migrations
uv run --frozen mypy
uv run --frozen pytest -q --cov
```

Use the [isolated infrastructure](../../deploy/platform/README.md) to start
containers. Do not use the legacy root `.env`. Secrets come from mounted files;
there are no default passwords or global CA changes. Required variables and
staged acceptance boundaries are in [IMPLEMENTATION.md](IMPLEMENTATION.md).

The migration role runs `uv run --frozen alembic upgrade head`. Application
startup never performs DDL. Destructive downgrade is unsupported: retain the
database and restore into a new instance when necessary.

`tests/integration/check_database.py` is an executable smoke check using the
real API runtime role. Pipe the script into `python -` inside the **new test**
API container; it reads mounted credentials without printing them. It rolls
back all attempted forbidden statements. It does not prove business transaction
atomicity, authentication, backup/restore or end-to-end authorization.

Evidence and remaining gates: [delivery progress](../../docs/platform/delivery-progress.md).
