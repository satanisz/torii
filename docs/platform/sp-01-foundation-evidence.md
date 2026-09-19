# SP-01 — evidence for the first foundation increment

Date: 2026-09-19. Integration base: `7328e1c`; the implementation commit will
be recorded after the reviewed changes are committed. **SP-01 remains open.**

## Scope and interpretation

This increment adds FastAPI/configuration/HTTP/domain foundations, an initial
PostgreSQL schema, React project screens and isolated developer infrastructure.
There are no product API routes for OIDC/session/projects yet. A frontend test
fixture is not evidence that real authorization or persistence works end to end.

Review: separate agents reviewed contracts, backend and frontend; root integrated
and re-ran gates. This is not an independent human security audit or enterprise
release. No push, remote workflow run or branch-protection mutation occurred.

## Backend evidence

Windows, Python3.12.12, uv0.11.19; FastAPI0.141.1 and complete hash-pinned uv.lock.
Runtime container Python3.12.14 (base image digest in infrastructure lock).

| Command / check | Observed result | Boundary |
|---|---|---|
| SPEC-0001 `validate_contracts.py` | PASS:21 operations,18 definition fixtures,8 requests,2 JCS vectors | Specification, not server conformance |
| `uv sync --frozen` | PASS | Local Windows toolchain |
| `uv run --frozen ruff check src tests migrations` | PASS | Static lint |
| `uv run --frozen ruff format --check src tests migrations` | PASS,26 files | Format |
| `uv run --frozen mypy` | PASS,15 source files | Strict application types |
| `uv run --frozen pytest -q --cov` | PASS,89 tests;93% combined branch/statement coverage | Unit/ASGI foundations only |
| `pip-audit==2.10.1` on frozen exported runtime requirements | No known vulnerabilities found | Registry advisory snapshot, not security proof |
| `alembic upgrade head` in isolated migrator | PASS,0001_projects | New empty schema only; not restore/migration-from-old-release |
| `tests/integration/check_database.py` in real API container | PASS | Exact schema, grants, denied audit writes/DDL, no IdP DB connection |

Two upstream test-tool deprecation warnings remain: Starlette recommends httpx2
and references the older anyio BlockingPortal alias. Warnings were not hidden;
tests did not fail. Track an explicitly tested tooling update separately.

The database check ran as `torii_runtime` against only the newly created test
database. Forbidden operations were always rolled back. No business fixture or
legacy data was modified. Readiness does not bypass a missing migration.

## Findings fixed before acceptance of this increment

- OIDC state also needs a browser-binding cookie; createProject receipt replay
  must check current project visibility. Semantics recorded in SPEC-0001 0.3
  before implementation of those future routes.
- Configuration exception chains could expose a malformed DSN: suppressed
  unsafe causes and regression-tested the rendered traceback.
- Numeric overflow and extreme decimal exponents could become infinity/500:
  strict bounded numeric decoding and regressions. Exact fractions cannot be
  rounded into an allowed integer; U+0000 rejected before PostgreSQL persistence.
- Audit outcome/display-name storage aligned with the wire contract before the
  first migration. ASGI framing/timeout and full-collection cursors tested.
- Frontend and infrastructure findings/results are recorded in their own
  implementation/evidence documents; completion must follow their final gates.

## Remaining sprint gates

OIDC login/logout/Bearer/session CSRF, project/ACL/audit endpoints and current
authorization, transactional receipts/concurrency/fault injection, real UI/API
E2E, restart and backup/restore, rate limiting/metrics/time retention, image and
secret/license scans/SBOM, manual browser/keyboard/zoom validation, performance
baseline. SP-02 object/version behavior is not claimed by this increment.

Prepared CI workflow covers only current foundation gates. Required integration
and release checks must be added with subsequent increments, not silently
represented by a green unit job. Required checks are not configured remotely.

Supporting evidence: [infrastructure](../../deploy/platform/evidence.md),
[frontend](../../apps/web/IMPLEMENTATION.md), [ongoing delivery](delivery-progress.md).

## Integrated foundation gate (final run)

`./scripts/check-platform-foundation.ps1` — PASS after review fixes. Root repeated
the complete contract/backend/frontend gate from frozen installations, including
89 backend tests, 50 frontend tests, lint/types, OpenAPI drift, UI build, npm audit
(0 findings), Python runtime audit (0 known findings), 15 infrastructure helper
tests and whitespace checks. A preceding run correctly stopped on a new test's
lint error; it was corrected before the final full PASS.

Independent reviewer repeated frontend tests/lint/types/contract check and gave
GREEN for the bounded foundation. No product API/E2E acceptance was inferred.

Infrastructure agent executed 26 topology checks, 10 real Keycloak discovery checks,
6 real HTTPS gateway checks (error format/UUID/no-store, upstream 401 preservation,
262144-byte accepted boundary and 262145-byte 413), plus synthetic log-redaction
checks. DB/IdP/API run; full web/gateway application stack is not yet started.
The dedicated gateway test used only disposable synthetic resources and explicit
local CA trust; no machine-wide CA installation. Agent evidence documents the
Docker Desktop internal-network publish limitation and reviewed ingress bridge.

Logo hashes match the unmodified original. Changed/new Markdown documents had
valid local links when checked. Generated credentials, virtual environments and
build outputs are ignored. This does not substitute for a full secret scanner.
