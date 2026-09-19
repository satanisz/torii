# SP-01 backend increments — SPEC-0001 / SPEC-0002

Status: implementing under the recorded delivery mandate. This is not a
claim that SP-01 or any end-to-end acceptance criterion is complete.

## Increment A: tested foundation

- Independent Python 3.12 package, FastAPI HTTP adapter, domain package free
  of HTTP/SQL/ML imports. Frozen dependencies, Ruff, strict mypy, pytest.
- Configuration fails closed without database/OIDC/cryptographic secrets.
  Secret files are supported; configuration repr never exposes credentials.
- HTTP envelope: server-generated request ID, no-store, uniform Problem Details,
  bounded strict JSON (duplicate keys, invalid UTF-8/constants/surrogates, depth,
  Content-Type), rejects bodies where the contract has none. No echo of inputs.
- Pure domain tests for role capabilities, names, strong ETags, policy invariants,
  canonical fingerprints and signed actor/scope/filter-bound pagination cursors.
- Liveness independent of database. Readiness requires reachable PostgreSQL and
  exact migration head. No create_all, in-memory fallback, fabricated principal,
  or successful readiness when migrations are missing.

Evidence maps to parts of SPEC-0001 AC-08/10/14, SPEC-0002 AC-03/04/05.
Pure tests do NOT prove authorization, PostgreSQL transactions or login.

## Increment B: durable project services

Migration creates org/principal/grants/project/membership/audit/receipt/session
relations. Separate runtime/migrator roles, append-only audit. Add PostgreSQL
transaction tests and OIDC/session integration before connecting the production
HTTP routes. Tests must cover denial, last-owner race, idempotent replay under
revoked grants, audit-failure rollback, lock timeout, restart and restore.

## Increment C: integrated journey

Connect frontend and isolated Keycloak/DB stack, validate real multiple-user
journeys and raw API, failure states, scans, resource baseline and recovery.
Each missing gate stays visible in delivery-progress, not replaced by a mock.

## Configuration contract with infrastructure

`TORII_DATABASE_URL_FILE`, `TORII_SESSION_KEY_FILE` (Fernet),
`TORII_CURSOR_KEY_FILE` (random >=32 bytes text), `TORII_OIDC_CLIENT_SECRET_FILE`.
Direct env equivalents are allowed only with explicit TORII_PROFILE=test;
both configured at once is invalid. `TORII_PUBLIC_URL`, `TORII_OIDC_ISSUER`,
`TORII_OIDC_BACKCHANNEL_URL`, `TORII_OIDC_CLIENT_ID`, `TORII_OIDC_AUDIENCE`.
No credentials in CLI arguments. API factory `torii_api.app:create_app`, port8000;
health `/health/live`, `/health/ready`. Alembic from apps/api, `upgrade head`.

Rollback: stop new API, retain new database; no legacy changes. New incomplete
routes remain absent rather than bypassing authentication to demonstrate UI.

## Technical review, 2026-09-19

Independent review agent approved Increment A scope before code. Two review
rounds found and root fixed numeric overflow/decimal exponent edge cases,
unsafe configuration exception chaining, PostgreSQL U+0000, migration audit
vocabulary/display-name bounds. Regressions include HTTP timeout cancellation,
duplicate/framing headers and full-collection cursor binding. SPEC-0001 0.3
records browser-bound login/replay ACL semantics before those routes exist.
This is agent technical review, not independent human enterprise sign-off.
