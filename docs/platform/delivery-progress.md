# Dziennik realizacji Torii

## 2026-09-19 — start mandatu autonomicznego

Baseline planu: `a7b19a5`. SP-00: kontrakty OpenAPI/JSON Schema i specyfikacje
przygotowane, walidator kontraktów PASS. Mandat w `delivery-mandate.md` pozwala
rozpocząć SP-01. Opcjonalne warianty logo i przyszłe próby runner/storage/MLflow
nie blokują fundamentu projektów; pozostają przed zależnymi sprintami.

Aktualny sprint: **SP-01, w realizacji**. SPEC-0001/0002/0017 nie są Verified.
Następne zadania: izolowany szkielet FastAPI, testy, frontend projektów,
środowisko dev/test; następnie OIDC, PostgreSQL, kontrola dostępu i E2E.

Nie wykonano push ani zmian starej instalacji. Stan początkowy powyżej;
bieżące dowody pierwszego przyrostu poniżej. Nie ma odbioru całego SP-01.

## SP-01 — pierwszy fundament (zweryfikowany w ograniczonym zakresie)

Commit baseline/kontraktów/logo i mandatu: `7328e1c`. Kod fundamentu:
**`8051a85`**, po domknięciu przeglądu i bramek. Nie zmieniono legacy.

- `apps/api`: osobny Python 3.12/FastAPI, frozen uv.lock, konfiguracja fail-closed,
  bezpieczna obwiednia HTTP, czyste reguły ról/ETag/JSON/cursorów, health i Alembic.
  **89 testów PASS**, Ruff i strict mypy PASS; pip-audit runtime: brak znanych
  podatności. To nie testy rzeczywistego uwierzytelniania czy projektowych transakcji.
- `apps/web`: React/TypeScript i widoki login/projects/access/audit przeciwko
  kontraktowi; 50 testów PASS, lint/types/contract drift/build/audit PASS.
  Jeszcze nie zintegrowane z prawdziwymi endpointami produktu.
- `deploy/platform`: odizolowany stos, pinned image digests, osobne role DB,
  nowe sekrety w ignorowanym `.local`, brak modyfikacji root `.env`.
- Alembic `0001_projects` uruchomione na nowej syntetycznej bazie; API health PASS.
  Rzeczywisty smoke konta runtime: SELECT wymaganych tabel, brak DDL,
  brak UPDATE/DELETE audytu, brak INSERT globalnych grantów/organizacji,
  brak CONNECT do bazy IdP — PASS.
- Niezależny agent przejrzał kontrakty i backend; znalezione problemy poprawiono
  z regresjami. To przegląd techniczny, nie ludzki audyt enterprise.
- CI foundation przygotowane lokalnie, akcje pinned SHA; **nie uruchomiono
  zdalnego workflow** i nie skonfigurowano branch protection.

Przebieg szczegółowy: `apps/api/IMPLEMENTATION.md`, `apps/web/IMPLEMENTATION.md`,
`deploy/platform/evidence.md`. Wersje SPEC: 0001 semantyka0.3/wire0.2.0,
0002 rev0.2, 0017 rev0.1. Dokumenty szczegółowe rozstrzygają niespełnione AC.

Pełna lokalna bramka `scripts/check-platform-foundation.ps1` PASS. Infra:
15 testów narzędzi, 26 topologii, 10 discovery prawdziwego Keycloak,
6 HTTPS gateway i redakcja logów PASS. [Raport](sp-01-foundation-evidence.md).
Usunięto wyłącznie efemeryczne kontenery/sieci własnych testów gateway;
utrwalone dane platformy, stare dane i stosy pozostają nienaruszone.

### Stan lokalny do kontynuacji

Nowy test stack: `torii-platform-test-abcdef012345`, port planowany19443,
sekrety `deploy/platform/.local/test-abcdef012345` (ignorowane, nie wypisuj).
DB/IdP/API zdrowe; migrator exit0. Nie publikuj sesji/secrets i nie uruchamiaj
gołego root `docker compose`: wybrałoby historyczny stos.
Lifecycle: `deploy/platform/platform.ps1 -Profile test -RunId abcdef012345`.
Budowa/uruchomienie zawsze explicitCompose/project/env, bez runtime pobierania
pakietów (`uv run --frozen --no-sync` w zbudowanym kontenerze).

### Następne obowiązkowe kroki

1. Fundament zacommitowany i zweryfikowany — nie powtarzać jego implementacji.
2. Increment B: repozytoria/transakcje projektów, membership, audit i receipt;
   OIDC code+PKCE/state/nonce z cookie inicjującej przeglądarki, sesje i Bearer.
   Brak żadnego hardcoded identity, bypass auth ani in-memory fallback.
3. Podłączyć prawdziwe API do UI; realne wieloosobowe E2E i raw API odmowy,
   CSRF/revocation/last-owner race/idempotency/audit rollback, restart+restore.
4. Brakujące SP-01 bramki: rate limiting, bounded metrics, czasowa retencja,
   pełne skany sekretów/obrazów/licencji+SBOM, baseline zasobów i ręczne UX/a11y.
5. Dopiero po wszystkich obowiązkowych AC przejść do SP-02; kolejne SPEC przed
   implementacją według roadmapy. Firma będzie potrzebna przed kwalifikacją,
   lecz to nie blokuje lokalnych przyrostów i syntetycznych testów.

Kontynuacja w tym zadaniu: heartbeat `torii-realizacja-sprint-w`, co 30 minut.
Wymaga działającej aplikacji i komputera. Po ukończeniu możliwego lokalnie zakresu
lub rzeczywistej blokadzie wymagającej użytkownika wstrzymać automatyzację i
raportować stan; nie deklarować fikcyjnego odbioru enterprise.
