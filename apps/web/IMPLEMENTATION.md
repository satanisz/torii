# SP-01 — frontend foundation

Date: 2026-09-19. Scope approved under the delivery mandate; implementation is
not acceptance of the enterprise release. References: SPEC-0001 revision 0.2,
SPEC-0002 revision 0.1, SPEC-0017 revision 0.1.

## Bounded increment (recorded before code)

Build a React/strict TypeScript SPA with Vite and a pinned npm lock. Implement
OIDC entry (no password form), session/logout, project list/filter/pagination,
project creation/detail, owner-only access policy, and audit pagination.
Use same-origin `/api/v1` cookie requests, no browser token persistence, explicit
CSRF for writes, one idempotency key per attempted mutation, and the API's
ETag for conditional access-policy replacement. Refreshing a conflict never
silently force-saves. No object/Flow/model buttons until those features exist.

The environment marker says DEV because this distribution is the isolated
developer build, not a detected or certified production environment. The logo
is copied byte-for-byte from the user-provided repository original. No derived
brand asset, external font, telemetry, demo data or mock backend enters the build.

## Technical review and constraints

- Read the normative API/schema and accepted delivery mandate before coding.
- Server remains the authority: role-based UI is only an ergonomic affordance.
  A 401 clears the session; 403/404 clears the current project content. Fresh
  project authorization precedes access-policy conflict comparison. Requests
  are abortable, and stale responses cannot restore a discarded view.
- Safe reads have bounded retry for 429/503 and honor Retry-After; mutations
  are not retried automatically. Uncertain writes reuse the same key and body.
- Editing stays in memory. Unsaved navigation/close warns. Authentication
  changes discard drafts, never replay them under another identity.
- Error text is localized and does not echo arbitrary server messages, inputs,
  response bodies, or SQL. Display a validated request ID and field error codes.
- API TypeScript types are generated from canonical OpenAPI. Build validation
  checks drift; runtime response validation rejects malformed response shapes.
- Root integrates API/infrastructure and performs a separate technical review.
  Component tests are evidence about UI behavior, not real OIDC/API E2E.

## Acceptance mapping and planned checks

| Scope | SPEC/AC | Planned evidence |
|---|---|---|
| Session/projects and role-based navigation | 0017 AC-01/02; 0001 AC-01/03/14 | Component/API client tests; real E2E still required |
| Conditional access-policy update/conflict | 0001 AC-09/10; 0017 AC-04/08 | Headers, conflict/revocation and identity-change tests |
| Error fields and request ID | 0017 AC-04 | Component/API client tests |
| Keyboard/semantic controls/contrast | 0017 AC-05/06 | Component focus/label tests, token contrast; manual 200%/browser review still required |
| Honest delivered scope | 0017 AC-07 | No future-module actions; explicit SP-01 scope |
| No persistence, discard on logout/denial | 0017 AC-08 | Negative tests and source review |
| Locked reproducible frontend build | 0002 AC-01/04/05 (part) | npm ci, typecheck, lint, tests, build, audit |

SP-02 object forms/version history and its draft conflict AC are not implemented
by this increment. No whole SPEC or sprint is marked Verified by these checks.

## Verification

Implemented SP-01 browser views listed above, with no mock backend in the runtime
bundle. Worktree evidence collected 2026-09-19 on base commit
`7328e1cbb2efb3835eb7e328b42f019ae83af4b4` (the integrator records the final
delivery commit). Windows, Node 24.15.0, npm 11.12.1. Dependency versions are in
package.json/package-lock.json; TypeScript 5.9.3 satisfies openapi-typescript's
current peer contract. The npm engine range is >=11 <12 because no 11.12-specific
feature is used; Node remains >=24.15.0 <25 and engine-strict is enabled.

| Command | Observed result |
|---|---|
| `npm ci --ignore-scripts` | PASS; 263 installed packages; no lifecycle scripts needed |
| `npm run api:check` | PASS against current canonical OpenAPI, including description update |
| `npm run typecheck` | PASS; strict, noUncheckedIndexedAccess, exactOptionalPropertyTypes |
| `npm run lint` | PASS; zero errors/warnings |
| `npm run test -- --reporter=dot` | PASS; 50 tests across 3 files |
| `npm run build` | PASS; 32 modules; JS 345.95 kB / gzip 108.95 kB; CSS 9.01 kB / gzip 2.75 kB |
| `npm audit --audit-level=low` | PASS; 0 reported vulnerabilities at inspection time |
| `git diff --check -- .` | PASS for tracked diff; new source checked by lint/build |

Behavioral tests cover cookie/CSRF/idempotency/ETag headers, unauthorized and
cross-role UI, unsafe error text, uncertain write replay, 412 comparison,
revoked grants and pending retry, dirty navigation/logout, cache removal, and
response parsing deadlines. The per-attempt 15 s client deadline now covers
headers **and** the full stream body, is abortable, and bounds SP-01 responses
to 1 MiB (25-record pages). Reads retry at most twice; a longer Retry-After is
shown instead of shortened. Mutation cooldown state updates independently of
form edits.

Technical review identified three regressions before integration: a parent
retry button could remain disabled after Retry-After, a denied project could
briefly reappear before reauthorization, and a body read outlived its request
deadline. All were fixed with dedicated tests. A control-border contrast of
2.94:1 was increased to 3.51:1; declared text/focus/notice token checks pass.
These are agent technical checks, not a human security/accessibility audit.

Independent agent technical review on 2026-09-19: GREEN for this bounded
foundation. Reviewer re-read all three fixes and independently repeated
50 tests, lint, typecheck and api:check successfully. No remaining actionable
blocker was reported within SP-01 frontend scope; real-service E2E remains open.

Logo copy SHA-256:
`ced80ee91284360fbe0fc98507d03093edb802107f6dc0039c41f936603c6b95`.

Lock metadata lists MIT, MIT-0, Apache-2.0, ISC, BSD-2-Clause, BSD-3-Clause,
BlueOak-1.0.0, Python-2.0, CC-BY-4.0, MPL-2.0, CC0-1.0 and MIT/CC0 dual-license
entries (including dev and optional dependencies). This inventory is not a
corporate license-policy approval; distributor notices/legal review remain a
release gate. No package install or asset copy establishes rights to the logo.

## Remaining acceptance work

- Real backend/PostgreSQL/OIDC/browser integration and API permission parity:
  **not run** by these component tests. Login cannot be claimed functional
  until the IdP and backend are wired and verified.
- Manual keyboard/reader/zoom-200% walkthrough and real-browser visual QA:
  **not run**. Semantic labels, focus rules and token tests are partial evidence.
- Object/draft/version routes (SP-02), including draft AC-03: **out of this
  bounded increment**, not implemented or passed.
- Session encryption/CSRF enforcement/authorization/audit durability/server
  rate limits: backend responsibilities, **not proven by UI mocks**.
- No production release, push, deployment, enterprise SLA, security sign-off,
  or whole-sprint/whole-SPEC Verified claim is made by this handoff.
