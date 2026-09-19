# Torii web — SP-01 foundation

React/TypeScript/Vite frontend for SPEC-0001, SPEC-0002 and SPEC-0017.
Delivered scope and exact evidence: [IMPLEMENTATION.md](IMPLEMENTATION.md).
This is a developer distribution, visibly labelled DEV.

## Checks

Run from `apps/web` with Node 24.15.0 (tested patch) and npm 11:

```powershell
npm ci --ignore-scripts
npm run api:check
npm run typecheck
npm run lint
npm test
npm run build
npm audit --audit-level=low
```

`npm run api:generate` regenerates TypeScript types from the canonical
`specs/0001-project-object-version/contracts/openapi.json`; commit generated
changes only alongside their reviewed source contract. `api:check` fails drift.

## Runtime boundary

Serve `dist/` through the platform gateway with same-origin `/api/v1/*` and
`/auth/*`, HTTPS, and SPA fallback for the client routes. No API URL, credential,
Bearer token, project fixture, telemetry endpoint, external font or mock API is
injected into the build. Tests alone use fixtures. The frontend is not a proxy
to the legacy AutoML stack and does not connect to its data.

`npm run dev` and `npm run preview` bind only to loopback. They do not provide
an API or identity service; standalone rendering is not proof of login working.
Use the separately configured platform gateway for genuine integration. Never
disable TLS/issuer checks or embed a token to make a screenshot work.

Routes in this increment: `/login`, `/projects`, `/projects/:id`,
`/projects/:id/access`, `/projects/:id/audit`. Other product modules are not
offered as nonfunctional navigation. Browser mutations use current session CSRF,
conditional ETags and operation-scoped idempotency keys. The server always
rechecks rights; visible buttons are not authorization.

The Docker build has an isolated `apps/web` context plus the public contract
context for `api:check`; it must not copy the repository's legacy `.env`.
`public/torii-logo.jpg` is a byte-for-byte copy of the repository's user-provided
logo reference, not a redesigned or relicensed asset.
