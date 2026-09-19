# SP-01 B2a1 — trwały stan tożsamości i sesji

2026-09-19. Baseline `9faf8ca`; kod/spec/testy: **`baa09bd`**. Zakres:
[SPEC B2a1](../../specs/0001-project-object-version/increment-b2a1.md),
Accepted (delegated) po niezależnym review przed implementacją.
Odbiór obejmuje wyłącznie wewnętrzne wartości i persistence, nie logowanie
OIDC/JWT/HTTP ani status Verified całego SPEC-0001/SP-01.

## Zaimplementowany zakres

- Wewnętrzny Identity DTO z dokładnym issuer/subject i normalizacją nazwy
  wyświetlanej. Nazwa ani email nie nadają tożsamości lub praw.
- Niezależne 256-bitowe credentials, kanoniczne hashe ASCII, Fernet envelope
  związane z przeznaczeniem i rekordem, ograniczenia rozmiaru i bezpieczne błędy.
- Trwałe browser-bound flows, TTL 5min, jednokrotne consume z commit przed
  zwróceniem verifier/nonce hash. Store nie wykonuje I/O sieciowego.
- Atomowy provisioning i rotacja sesji; brak automatycznych grantów oraz
  reaktywacji principal. Absolute 8h/idle 30min, zegar DB po oczekiwaniu na lock,
  bieżący lokalny status i globalny grant, izolacja zaufanego issuer.
- Revoke lokalny z commit przed zwrotem refresh do przyszłej revocation;
  corrupt refresh nie blokuje DELETE, awaria providera lub commit nadal blokuje.
- Cleanup max 100 flows i 100 sessions na wywołanie, SKIP LOCKED, bez zmiany
  danych biznesowych. Nie włączono joba ani polityki retencji audytu.

Wykorzystano istniejącą migrację 0001 i uprawnienia runtime. Nie zmieniono
schematu, konfiguracji, zależności, tras FastAPI ani frontendu. Uruchomiony
stack nie został przebudowany/wdrożony; dotychczasowe health nie dowodzi B2a1.

## Spec-first i przegląd

Agent `contract_review` przed kodem wskazał kolejność blokad, świeży czas DB
po lock wait i rozdzielenie corrupt refresh od awarii transakcji. Uściślenia
przyjęto w spec przed implementacją. Testy wartości i boundary najpierw były
RED z powodu brakujących modułów; dopiero potem dodano kod.

Po implementacji niezależny review wykrył i zamknięto z regresjami:

1. Store dla issuerB mógł zaakceptować starą sesję issuerA w tej samej bazie.
   Odczyt aktywnego principal wymaga teraz skonfigurowanego issuer, bez touch
   przy odmowie. Wewnętrzny revoke nie jest fasadą autoryzacji HTTP.
2. Zbyt szeroki handler codec łączył awarię providera decrypt z uszkodzeniem
   ciphertext i nie normalizował OSError. Oddzielono decrypt od parsing;
   TypeError/ValueError/OSError to bezpieczny zwykły503, tylko InvalidToken
   i błędy envelope to SecretDecodeError. Trzy pure regresje najpierw RED,
   następnie GREEN. PG regresja została dodana przed testem, ale jej RED nie
   wykonano przed poprawką — nie przypisujemy jej niewykonanego przebiegu.

Końcowy reviewer niezależnie powtórzył 251 pure values + 5 boundary tests:
**256 PASS**. Brak pozostałych findings w przeglądanym zakresie; to review
agenta, nie audyt ludzki ani dowód pełnego bezpieczeństwa.

## Dowody PostgreSQL

Nowe testy korzystają z niezmienionego
[guarded harnessu B1](../../deploy/platform/evidence-harness-b1.md):
osobny tmpfs PostgreSQL 17, nowa migrowana baza na test, fixtures/fault injection
kontem migratora, wszystkie operacje store kontem runtime.

- Jednokrotne consume przy współbieżności, brak zużycia przez złą przeglądarkę,
  TTL po lock wait i brak wyniku przy deferred commit failure.
- Równoległy provisioning -> jeden principal, brak nowych praw, odmowy
  inactive/foreign issuer/brak organizacji; atomowy rollback utworzenia
  principal i rotacji starej sesji.
- Absolute/idle expiry podczas oczekiwania; touch nie przedłuża absolute;
  aktualny grant, dezaktywacja, nowa instancja store odczytuje tę samą sesję.
  To NIE jest restart procesu lub bazy.
- Auth/revoke w obu kolejnościach nie wskrzesza sesji; auth vs login nie
  odwraca kolejności principal/session locks; pozostałe urządzenia zachowane.
- Zły klucz/purpose/record/ciphertext odmawia; corrupt refresh usuwa sesję
  lokalnie, chyba że commit zawiedzie. Operacyjna awaria decrypt pozostawia
  pełny rekord bez zmian i nie ujawnia markerów w błędzie/chaining.
- Cleanup pomija zablokowane rekordy, ma stabilną kolejność i granicę 100
  sprawdzoną na 101 rekordach każdego typu. Aktywne sesje/flows i niepuste
  organizacje/principals/grants/projekty/memberships/audit/receipts zachowane.

Pierwszy agent run `fd8175026757432a98d146c8d93bce89`: 27 PASS, 45.27s.
Interim root fullgate run `942ccbe3f66043709fe6e3520fef48a8`: 50 PG PASS
(23 B1 + 27 B2a1), 82.09s, 526 unit + 50 frontend PASS. Ten przebieg poprzedza
końcowe regresje provider failure i nie stanowi ich dowodu.
Zasoby obu runów usunięto po kontroli ID/etykiet; dane tmpfs odrzucone.
Agent regresja decrypt: `4b1d3df007c14d78b83d94cbb53a7a18`, 3 PASS, 4.58s,
27 deselected; własny kontener/sieć usunięte, syntetyczny tmpfs odrzucony.

## Końcowa bramka

Root wykonał po zamrożeniu kodu i review
`./scripts/check-platform-foundation.ps1 -IncludePostgres`: **PASS**, exit0.

- **529 backend bez DB + 53 real PostgreSQL + 50 frontend PASS**.
  53 PG = 23 regresje B1 + 30 B2a1. Żaden test PostgreSQL nie został pominięty;
  30 deselected to guards uruchomione już w grupie bez integracji.
- Run `03b28a5965ea4ec9954dc89734c1aea9`: 53 PASS, 86.04s. Po runie kontrolowany
  cleanup usunął własny kontener/sieć i jednorazowe dane tmpfs; dodatkowy odczyt
  etykiet nie znalazł pozostałych kontenerów/sieci b1-integration.
- Ruff/check/format (41 plików), strict mypy (23 source files), OpenAPI/schema/
  golden JCS, API contract drift, lint/TypeScript/build i 35 kontroli PowerShell
  PASS. Semantyka główna SPEC-0001 pozostaje0.4, wire OpenAPI0.2.0.
- pip-audit runtime i npm audit: brak znanych podatności w tym przebiegu.
  pip-audit zgłosił rekomendację pełnych hashy w eksportowanej liście; istniejący
  frozen uv.lock nie został zmieniony. To nie pełny skan obrazów/licencji/SBOM.
- Dwa istniejące ostrzeżenia deprecation Starlette/httpx i AnyIO pozostały jawne.
- Łączne coverage linii/gałęzi:96%, identity store95%, values/codec100%.
  Pokrycie jest pomocniczą metryką, nie dowodem pełnego bezpieczeństwa.
- Windows/Python3.12.12, Docker Desktop Linux28.5.2, lokalny kontekst
  `desktop-linux`, PostgreSQL17 pinned digest
  `sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`.
  Frozen toolchain z repo; zdalnego workflow nie uruchamiano.
- Kontrola staged przed commitem:13 znanych lokalnych wartości sekretów nie
  występuje w diff, brak prywatnych ścieżek `.env`/`.local` i wybranych wzorców
  credentials; wartości nie były wypisywane. Nie jest to pełny skan repo/historii.

## Granice i następny krok

Nie wdrożono adaptera discovery/JWKS/JWT/code exchange, tras auth/projektów,
CSRF/Origin, Bearer, bootstrapu E2E ani połączenia UI z realnym API.
Nie zaliczono całych B2-AC03/04: store-only consume/provisioning to częściowy
dowód, nie callback/exchange. B2-AC01/02/05/06/07 nadal niewykonane.
Lokalna sesja nie podlega natychmiastowemu federacyjnemu revoke z IdP;
ta jawna decyzja dev/test wymaga oddzielnej kwalifikacji przed użyciem w firmie.

Następnie B2a2: spec i review weryfikatora JWT oraz ograniczonego transportu
OIDC/JWKS, bez rozszerzania zaakceptowanego B2a1 przez domysł. B2-D02 i odpowiednia
część D06 z propozycji B2 pozostają do przyjęcia. Potem B2b HTTP/Keycloak/UI.
Restart/restore, limiter/metryki/retencja, NFR/obciążenie, skany obrazów/sekretów/
licencji/SBOM, zdalny workflow i ręczne UX/a11y nadal są oddzielnymi bramkami.
SP-01 jest w realizacji; nie przechodzimy do SP-02 na podstawie tego raportu.

Nie wykonano push/PR, zmian root `.env`, legacy wolumenów, firmowych zasobów
ani trwałej nowej bazy `test-abcdef012345`. Automatyzacja kontynuacji pozostaje
aktywna; bezpieczny kolejny lokalny przyrost nie wymaga decyzji użytkownika.
