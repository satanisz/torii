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

## 2026-09-19 — B1: transakcje projektów (heartbeat)

Commit **`27df731`**: trwały ProjectService, polityka dostępu, membership/audit,
idempotency receipts, blokady i bezpieczna granica transakcji. Spec B1 została
przyjęta po niezależnym review przed kodem; semantics SPEC-0001 rev0.4, wire0.2.0.
Brak nowego HTTP/auth bypass, migracji i wdrożenia na uruchomionym stosie.

Końcowa bramka `./scripts/check-platform-foundation.ps1 -IncludePostgres` PASS:
**273 backend bez DB + 23 real PostgreSQL + 50 frontend**. Kontrakty, Ruff,
format, strict mypy, lint/types/build, audyty zależności i 35 kontroli PowerShell
PASS. Wszystkie testy PostgreSQL wykonane na nowych efemerycznych zasobach,
osobna migrowana baza na test, biznesowe operacje kontem runtime. Nie jest to
mock ani test na danych firmy. Zdalny workflow pozostaje niewykonany.

Dowody obejmują równoległy create/retry, rollback audit/receipt i błąd commit,
brak wycieku projektów, odmowę po revoke w trakcie czekania na lock, last-owner
race, snapshot policy/ETag, timeout503 i stronicowanie z powtarzającym się czasem.
Przeglądy agentów domknięte; wykryte PG*/remote-Docker ryzyka harnessu naprawiono
i sprawdzono testami negatywnymi. To review techniczne, nie audyt człowieka.

Szczegóły: [raport B1](sp-01-b1-evidence.md) oraz
`deploy/platform/evidence-harness-b1.md`. Dane jednorazowych testów tmpfs
odrzucono po kontrolowanym cleanup; legacy, root `.env` i trwała nowa baza
`test-abcdef012345` pozostały nienaruszone. Nie wykonano push ani PR.

### Następny krok — nie powtarzać B1

SP-01 nadal **w realizacji**, cały SPEC-0001/0002/0017 bez statusu Verified.

1. B2: doprecyzować i przejrzeć spec adaptera OIDC/JWT/sesji, potem implementacja
   i testy. Użyć istniejących tabel sessions/oidc_flows i rzeczywistego
   lokalnego Keycloak, bez hardcoded identity ani nadawania create na login.
   [Propozycja B2](../../specs/0001-project-object-version/increment-b2.md)
   jest już zapisana i przeczytana przez integratora, lecz pozostaje **Proposed**:
   B2-D01–06 wymagają rozstrzygnięcia/review przed odpowiednim kodem. Rozdziela
   B2a adapters/storage od B2b HTTP/E2E; nie jest akceptacją własną autora.
2. Następnie połączyć ProjectService z FastAPI i istniejącym React UI;
   przetestować realne logowanie wielu użytkowników oraz surowe API/CSRF/revoke.
3. Wciąż brak restart/restore, rate limiting/metrics/retention, zasobów/NFR,
   pełnych skanów secrets/images/licenses/SBOM oraz ręcznego UX/a11y.
4. Nie przechodzić do SP-02 przed obowiązkowymi bramkami SP-01. Firma nie jest
   potrzebna do następnego lokalnego przyrostu, lecz pozostaje warunkiem
   odbioru enterprise. Automatyzacja kontynuacji pozostaje aktywna.
