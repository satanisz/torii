# B1 — kontrakt i dowody efemerycznego harnessu PostgreSQL

2026-09-19. SPEC-0001 [B1](../../specs/0001-project-object-version/increment-b1.md),
punkt 5. Plan zaakceptowany technicznie przez integratora przed implementacją.

## Zapis przed kodem

- `test-projects.ps1` tworzy nowy PostgreSQL 17 przypięty istniejącym digestem,
  własną sieć/etykietę run UUID, tmpfs PGDATA i losowy loopback port Docker.
- Losowe hasła admin/migrator/runtime tylko w środowisku procesu potomnego;
  brak sekretów w argv, repo, logach i wymiany przez istniejące `.env`.
- Wymiana z pytest: `TORII_B1_RUN_ID`, `TORII_B1_CONTAINER_ID`, `TORII_B1_PORT`,
  `TORII_B1_DOCKER_CONTEXT`,
  `TORII_B1_ADMIN_PASSWORD`, `TORII_B1_MIGRATOR_PASSWORD`, `TORII_B1_RUNTIME_PASSWORD`.
- Fixture `db_pair` ma scope function i zwraca `.runtime` / `.migrator` engines.
  Seed org/actor należy do testu aplikacji, nie ukrytego bootstrapu fixture.
- Każdy test: osobna nowa DB, owner migrator, pełny Alembic upgrade jako migrator,
  runtime z ograniczonymi grantami nadanymi przez migrację, bez DDL.
  Rzeczywiste transakcje i równoległe połączenia.
- Fixture sprawdza exact container ID, etykiety, pinned image i loopback binding
  przed połączeniem, a przed DROP dodatkowo nazwę/owner/run marker nowej DB.
  Nie przyjmuje zewnętrznego DSN. Kontener jest usuwany tylko po kontroli ID/etykiet.
- Brak całego środowiska: integration fixture skip; częściowe/błędne: fail closed.
  Wrapper wyłącza pytest addopts/--showlocals; dodatkowe argumenty są tablicą,
  nigdy poleceniem shell. Błąd bootstrap/migracji nie wypisuje surowego diagnostyku.
- Pierwotne process env jest odtwarzane w finally; lokalne/legacy bazy oraz
  test-abcdef012345 pozostają nietknięte. Brak wolumenów wymagających cleanup.

## Plan weryfikacji

Ruff/typowanie helperów, skip bez env, odmowa częściowego env, real migration
i current_user/runtime grants, commit i odczyt drugim połączeniem, izolacja
per test, następnie testy ProjectService root. Po runie brak kontenera/sieci
z zapisanym run ID.

## Wykonane kontrole harnessu

- Ruff oraz `mypy --strict --follow-untyped-imports` dla conftest: PASS.
- Niezależny przegląd techniczny `contract_review`: brak blokujących uwag;
  doprecyzowano opis ograniczonych praw runtime. Nie jest to audyt ludzki.
- Parsowanie PowerShell przez native Parser: PASS.
- Niezależny syntetyczny mini-smoke (ignorowany `.local/b1-harness-smoke`):
  bez harness env 2 SKIP; z częściowym env 2 oczekiwane odmowy setupu, bez DSN.
- Nowy run `64f0a2aec3dd4f91b165e165c842f8e8`: 2 testy real PostgreSQL PASS
  (migracja/runtime/no-DDL, commit fixture i odczyt runtime, kolejny test pusty).
  Python 3.12.12, pytest 9.1.1, PG17 przypięty jak w locku. Ostrzeżenie marker
  w tym mini-smoke wyeliminowano przez jawne `pytest -c apps/api/pyproject.toml`.
- Po runie nie pozostał kontener ani sieć z etykietą b1-integration. Baza
  test-abcdef012345 i legacy nie były używane. Dane tmpfs testu odrzucono.

## Pełne testy ProjectService

Polecenie: `./deploy/platform/test-projects.ps1 -TestArgs @('tests/integration/test_projects.py')`.
Run `71ec55bed5e948f4a250bb943f5d1d96`: **11 PASS w 13.93 s**. Każdy test miał
świeżą bazę i wykonaną migrację. Tylko 2 znane ostrzeżenia deprecation
Starlette/httpx oraz anyio; nie ukrywano ich w konfiguracji.
Guarded cleanup usunął nowy kontener/sieć i dane tmpfs. Nie pozostały zasoby
z etykietą b1-integration ani zmienne TORII_B1_* w procesie wywołującym.
Standardowe uruchomienie tego pliku pytest bez wrappera: **11 SKIP**.

Te dowody obejmują usługę PostgreSQL i harness, nie OIDC/HTTP, UI/E2E,
restart/restore ani cały SP-01. Lista scenariuszy leży w testach/root evidence.

## Regresje granicy celu po niezależnym przeglądzie

Przed poprawką, reviewer `frontend` wskazał wpływ odziedziczonych zmiennych
libpq (np. PGHOSTADDR) oraz zdalnego kontekstu Docker. Integrator zaakceptował
fail-closed przed dalszym odbiorem: odrzucenie wszystkich process env `PG*`
(case-insensitive) i obecności DOCKER_HOST, bez odbijania nazw/wartości w błędzie.
Jawnie rozwiązany kontekst Docker musi mieć lokalny named pipe lub Unix socket;
zostaje przypięty przez `--context`, przekazany fixture jako
`TORII_B1_DOCKER_CONTEXT` i niezależnie zweryfikowany przed inspect/DB.
Wrapper przywraca także pierwotny DOCKER_CONTEXT. Pure negative tests nie
uruchamiają połączeń ani zasobów.

Po poprawce: **30 pure pytest PASS**, **20 pure PowerShell checks PASS**,
Ruff oraz strict mypy conftest PASS. Reviewer `frontend` niezależnie powtórzył
te kontrole oraz parser 3 plików PowerShell; brak dalszych blokujących uwag
w zakresie harnessu. Testy obejmują puste/mieszanej wielkości nazwy PG*,
DOCKER_HOST, odrzucenie TCP/SSH/zdalnego named pipe/niejednoznacznego Unix URI,
brak wywołania inspect przy zakazanym env oraz przypięty kontekst inspect.

Nowy pełny run `7b57bfc6cec341969ff3a8e423c34dfb`: **23 real PostgreSQL tests
PASS w 36.93 s**, 2 uprzednio wskazane ostrzeżenia deprecation. Kontener/sieć
usunięte po weryfikacji własności; testowy tmpfs odrzucony. Nie użyto
istniejącej bazy, kontekstu zdalnego ani danych legacy.
