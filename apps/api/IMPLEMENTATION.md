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

### B1: project application service

`application/projects.py` implements persisted project creation/reads, policy
replacement, memberships and audit pages. `storage/receipts.py` and
`storage/transactions.py` contain transactional receipts and safe failure
boundaries; strict input validators remain in the dependency-free domain.
Specification: `specs/0001-project-object-version/increment-b1.md`, accepted
after independent technical review before implementation. Semantics rev0.4
clarifies receipt TTL at the final database timestamp before commit.

Writes use READ COMMITTED, scope locks and fresh permission checks after waiting.
Read-only REPEATABLE READ keeps policy body/ETag consistent. No new HTTP route,
identity bypass, migration or modification of the running legacy/new test stack.

Run real PostgreSQL tests from repo root with
`./deploy/platform/test-projects.ps1`, or the full local gate with
`./scripts/check-platform-foundation.ps1 -IncludePostgres`. The harness creates
new tmpfs-only PostgreSQL and a fresh migrated database per test; fixture seeding
uses the migrator, all business operations use runtime. Ordinary pytest without
the dedicated harness does not count skipped database tests as verification.

B1 does not cover process/database restart, restore, HTTP/OIDC or UI journeys.
See `docs/platform/sp-01-b1-evidence.md` for executed evidence and remaining gates.

### B2a1: internal identity and session persistence

`domain/identity.py`, `security/session_secrets.py` and
`application/identity_store.py` implement the separately reviewed
`specs/0001-project-object-version/increment-b2a1.md`. This selects only the
durable-state subset of B2; the remaining B2 proposal is not accepted by it.

Identity is an internal DTO, **not a verified token**. No caller-facing routes
were added. A future trusted JWT/OIDC adapter must establish issuer/subject
provenance before calling the store. Synthetic fixtures are not an auth bypass.
The runtime uses the existing migration and least-privileged database role.

- Canonical 256-bit credentials; stored hashes and purpose/record-bound Fernet
  ciphertext, redacted result reprs and safe crypto errors.
- Browser-bound, single-use login flows with database-clock expiry and commit
  before returning exchange material; no network calls in the store.
- Unique issuer/subject provisioning without grants or reactivation; atomic
  session creation and rotation, absolute 8h/idle 30min, current local active/grant
  checks, issuer isolation and lock order that avoids auth/login deadlock.
- Local revocation commits before releasing refresh material. Corrupt refresh
  does not block local deletion, but database/commit failures still roll back.
- Bounded expired-state cleanup, at most 100 flows and 100 sessions per call;
  no background job or business-data retention policy introduced.

The local session does not automatically follow federated IdP revocation;
that limitation requires a separate corporate decision before deployment.
No JWT verification, code exchange, HTTP/CSRF, Keycloak login E2E or restart/
restore is proved by this increment. Evidence: `docs/platform/sp-01-b2a1-evidence.md`.

### B2a2: offline token verification

`security/oidc_keys.py` and `security/oidc_tokens.py` implement the separately
reviewed `specs/0001-project-object-version/increment-b2a2.md` profile. A static
issuer-bound public JWKS is parsed with byte/depth/node/numeric limits; only
qualified RSA signing keys are selected. Parsing does not prove key provenance.
The future transport must supply keys from the trusted issuer, never a request.

PyJWT/cryptography verify actual RS256 signatures; Torii enforces strict claim
types and required fields, issuer/audience/azp, clock skew, separate access/ID
types and login nonce/at_hash bindings. The Identity result carries no grants.
`token_key_id` is only an untrusted bounded lookup hint, not authentication.
Errors and reprs do not expose token/key data or exception context.

The test profile was checked against exact-tag Keycloak26.7.4 source and local
image metadata, not a newly issued token. Tests sign synthetic tokens with
ephemeral in-memory RSA keys. No discovery/JWKS fetch/cache, code exchange,
HTTP/session integration, login E2E or deployment is proved by these tests.
B2a3 must implement the separately reviewed network boundary before B2b routes.
Executed evidence and limitations: `docs/platform/sp-01-b2a2-evidence.md`.

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
