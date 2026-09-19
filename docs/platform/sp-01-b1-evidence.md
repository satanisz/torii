# SP-01 B1 — trwała usługa projektów

2026-09-19. Zakres: [SPEC B1](../../specs/0001-project-object-version/increment-b1.md).
Baseline `b442d18`; kod i dowody przyrostu: **`27df731`**.
B1 zweryfikowany w opisanej granicy usługi aplikacyjnej;
nie jest to ukończony SP-01 ani status Verified całego SPEC-0001.

## Co zaimplementowano

- Create/list/get project, owner-only polityka dostępu, listy membership/audit.
- Transakcja project + owner + audit + receipt; row/advisory locks, ponowna
  kontrola uprawnień po oczekiwaniu; atomowe zastąpienie ACL i no-op.
- Receipt 24 h, replay wyłącznie po sprawdzeniu aktualnych praw; konflikt
  fingerprint, stary ETag i brak właściciela mają odrębne bezpieczne odmowy.
- Literalne filtrowanie i podpisane cursory; spójny snapshot policy/ETag.
- Izolowany harness: przypięty PostgreSQL17, tmpfs bez wolumenu, runtime
  bez praw migratora, osobna migrowana baza na każdy test, kontrolowany cleanup.
- Workflow CI zapisany lokalnie; jednostkowe testy oddzielone od obowiązkowej
  warstwy PostgreSQL. Lokalna bramka ma jawne `-IncludePostgres`.

Brak nowych endpointów HTTP, zmian uruchomionej aplikacji i migracji schematu.
Nie zmieniono root `.env`, danych legacy ani bazy `test-abcdef012345`.

## Przegląd przed kodem i regresje

Agent `contract_review` zaakceptował spec przed implementacją po uściśleniu
TTL receipt, UUID zgodnego z polem, READ COMMITTED dla mutacji i REPEATABLE READ
dla odczytów. Canonical semantics rev0.4; OpenAPI nadal0.2.0. Po kodzie ten
agent nie znalazł blokujących błędów usług i wskazał brakujące testy stronicowania
oraz timeoutu. Root dodał te testy przed odbiorem.

Niezależny przegląd harnessu przez agenta `frontend` wykrył ryzyko wpływu
odziedziczonych PG* i zdalnego kontekstu Dockera na cel testu. Naprawa dodała
odmowy przed połączeniem/utworzeniem zasobów oraz przypięcia lokalnego kontekstu.
Nie wykonywano testów na zdalnym Dockerze ani z obcym PGHOSTADDR. Negatywne
przypadki używają czystych helperów/mocków i sprawdzają brak wywołań połączenia.
Reviewer niezależnie powtórzył 30 Python + 20 PowerShell guard checks: GREEN.

## Przebiegi kontrolne

- Pierwszy pełny przebieg: 11 PostgreSQL PASS, run
  `71ec55bed5e948f4a250bb943f5d1d96`, 13.93 s.
- Rozszerzony przebieg root: **19 PostgreSQL PASS**, run
  `42b78e6be0424f76a03043faf7f72b3a`, 25.33 s. Dowodzi także rollbacku ACL,
  commit-time failure, rzeczywistego timeoutu blokady, revoke podczas czekania
  oraz interleaving spójnego odczytu. Każdy używał świeżej bazy i runtime role.
- `scripts/check-platform-foundation.ps1`: 243 testy backend bez integracji,
  50 frontend, Ruff/format/strict mypy, contract drift/build, 15 infra guards,
  pip-audit i npm audit PASS. Audyty zależności: brak znanych podatności;
  nie oznacza pełnego audytu bezpieczeństwa ani skanu obrazów.
- Dwie istniejące deprecation warnings Starlette/httpx i AnyIO pozostają jawne.
- Zasoby powyższych przebiegów usunięto po sprawdzeniu dokładnego ID/etykiet;
  ich syntetyczne dane tmpfs są jednorazowe. Bazy trwałe pozostały nienaruszone.

### Końcowa bramka po poprawkach — PASS

Root wykonał `./scripts/check-platform-foundation.ps1 -IncludePostgres`:

- **273 backend bez bazy + 23 real PostgreSQL + 50 frontend PASS**.
- Ruff, format, strict mypy (20 plików źródłowych), kontrakty/API drift,
  TypeScript/lint/build, oba audyty zależności, 15 lifecycle + 20 environment
  guards PASS. Testy PostgreSQL nie zostały pominięte.
- Końcowy run `fac8e3b673fb4329a52cec2a569fdc1c`: 23 PASS w 37.49 s,
  po poprawkach granicy celu, z nową bazą per test. Scope runtime był rzeczywisty.
- Pokrycie łączne linii/gałęzi narzędzia coverage: 96%; B1 service/receipts/
  transactions/input validators: 100%. To metryka pomocnicza, nie dowód
  kompletności bezpieczeństwa ani zastępstwo scenariuszy negatywnych.
- Windows, Python3.12.12, Docker Desktop Linux28.5.2, PostgreSQL17 pinned digest,
  lokalny kontekst `desktop-linux` / named pipe. Zdalne CI nie było uruchamiane.
- Kontener/sieć końcowego runu usunięto po kontroli ID i etykiet; dane tmpfs
  były wyłącznie syntetyczne i zostały odrzucone. Nie dotyczy to żadnych danych
  trwałych. Niezależny wcześniejszy przebieg infraagenta też dał 23 PASS.

## Nadal niezaliczone

OIDC/session/Bearer, endpointy HTTP i ich CSRF/order/auth tests, rzeczywiste UI/API
E2E, restart procesu/bazy i restore, rate limiting/metrics/retention, benchmark,
skany obrazów/sekretów/licencji/SBOM oraz ręczne UX/a11y. Nowa instancja usługi
nie jest testem restartu PostgreSQL. Nie uruchomiono workflow zdalnie; po jego
pierwszym uruchomieniu potwierdzić zgodność runnera i dostępne zasoby.

Następny przyrost: spec-first adapter tożsamości, sesje OIDC i Bearer, następnie
wpięcie ProjectService do FastAPI i istniejącego React UI. Bez hardcoded identity.
Przed odbiorem enterprise nadal wymagany niezależny ludzki review i środowisko firmy.
