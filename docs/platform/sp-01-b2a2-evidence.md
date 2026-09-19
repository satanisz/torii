# SP-01 B2a2 — offline JWT i publiczne klucze

2026-09-19. Baseline `4189968`. Zakres:
[SPEC B2a2](../../specs/0001-project-object-version/increment-b2a2.md),
Accepted (delegated) po niezależnym przeglądzie przed kodem.
To odbiór komponentu offline, nie działającego logowania ani całego SP-01.

## Co dostarczono

- `security/oidc_keys.py`: bounded strict UTF-8 JSON/canonical base64url,
  limit byte/depth/node/number-literal, niemutowalny zestaw publicznych kluczy
  powiązany z issuer. Prywatne klucze, duplicate kid, błędne przeznaczenie
  i niekwalifikowane parametry wybranego RSA odrzucane. Bez pobierania URL.
- `security/oidc_tokens.py`: realna weryfikacja RS256 przez PyJWT/cryptography,
  wymagane ścisłe claims, issuer/audience/azp i czas z tolerancją30s.
  ID i access mają oddzielne typy/audience; login sprawdza oba podpisy, wspólny
  czas po ich weryfikacji, nonce z flow i opcjonalny at_hash.
- Wynik Identity nie zawiera grantów/roles i nie jest tworzony z emaila.
  Brak DB calls, nowych routes, zmian zależności, konfiguracji lub migracji.
  `token_key_id` to niezaufany hint lookup, nigdy dowód uwierzytelnienia.
- Błąd credential to ogólne401; zły JWKS/config/clock/provider to bezpieczne503,
  bez ujawniania wartości czy exception context. Stare moduły pozostają bez zmian.

Źródłowy profil przypiętego Keycloak26.7.4 sprawdzono w oficjalnym exact-tag
kodzie oraz metadanych lokalnego obrazu. Spec zawiera bezpośrednie źródła.
Nie mintowano tokenu i nie sprawdzano rzeczywistego stanu realm; ten dowód
nie zastępuje późniejszego Code+PKCE na izolowanym Keycloak.

## Spec-first, testy i review

Przed implementacją agent contract_review sprawdził profil i granice; uściślono
clock, display_name z access, dokładne liczenie węzłów/głębokości i kid hint.
W trakcie self-review parsera wykryto zależność od globalnego limitu liczby cyfr
Pythona. Po osobnym review i zapisie w spec, przed kodem przyjęto limit128
znaków każdego literału liczbowego. Cztery regresje miały RED, potem GREEN.
Nie zmieniano globalnych ustawień interpretera i nie dodawano obejścia Decimal.

Trzy nowe pliki testów najpierw miały RED collection z powodu brakujących
modułów. Jedna próba root fixture została odrzucona przez PyJWT.encode przed
dotarciem do SUT (niepoprawny typ issuer); fixture zmieniono na podpis raw JSON
przez PyJWS.encode. Nie przedstawiamy tego jako znalezionej luki w verifier.

Nowe testy:

| Plik | Wykonany zakres |
|---|---|
| `test_oidc_keys.py` (184) | Granice128/129 liczb,2048 nodes,32 depth,65536 bytes/32 keys; duplicate/Unicode/NaN, kanoniczne pad bits, immutable replacement, RSA2048/4096, prywatne i błędne klucze, provider faults |
| `test_oidc_tokens.py` (83) | Claims/types/skew i dokładne terminy, issuer/aud/azp, konfiguracja i clock, bezpieczne błędy providera, wspólny czas po obu podpisach, no-network/DB import boundary |
| `test_oidc_token_attacks.py` (89) | Podmienione realne podpisy i klucze, none/HMAC confusion, ID-as-access, strict header/compact/JSON, nonce/at_hash/subject i osobne negatywne ID claims |

Klucze RSA i podpisy generowano w RAM z cryptography, nie są mockiem podpisu.
Nie zapisano fixture PEM/JWT/JWKS i nie użyto sekretów firmy lub aktywnego IdP.
Brak claims/grant escalation sprawdzono na wyniku DTO; połączenie verifier
z persistence/HTTP i dowód braku mutacji DB po odmowie są nadal do wykonania.
Końcowy contract_review po zamrożeniu kodu: GREEN, bez pozostałych konkretnych
findings. Reviewer niezależnie uruchomił trzy nowe zestawy: **356 PASS w1.04s**,
z dwoma znanymi deprecation warnings. Jest to review agenta, nie audyt ludzki.

## Końcowa walidacja

Root: `./scripts/check-platform-foundation.ps1 -IncludePostgres` po zamrożeniu
kodu — **PASS, exit0**.

- **885 backend bez DB + 53 real PostgreSQL + 50 frontend PASS**.
  Nowe testy JWT/JWKS356, regresje bez DB529. PG nadal23 B1 +30 B2a1;
  nie traktujemy ich jako nowych testów JWT/OIDC/DB integration.
- PostgreSQL run `3545abbbdb7043cea6562b27453708f4`:53 PASS,88.76s,
  bez skipów.30 deselected to guards już wykonane w grupie bez integracji.
  Własny kontener/sieć usunięto po kontroli ID/etykiet, tmpfs z syntetycznymi
  danymi odrzucono. Dodatkowy odczyt etykiet nie znalazł pozostałych zasobów.
- Ruff/check/format46 plików, strict mypy25 source files, OpenAPI/schema/JCS,
  contract drift, frontend lint/types/build,35 kontroli PowerShell — PASS.
- pip-audit runtime i npm audit: brak znanych podatności. Jawna rekomendacja
  pip-audit dot. hashy eksportowanej listy; frozen uv.lock bez zmian.
  Dwa dotychczasowe deprecation warnings Starlette/httpx/AnyIO pozostają.
- Łączne coverage97%, nowy oidc_tokens100%, oidc_keys99%; to metryka pomocnicza,
  nie dowód pełnego bezpieczeństwa lub poprawności integracji z IdP.
- Windows/Python3.12.12, PyJWT2.14.0/cryptography50.0.1, Docker Desktop
  Linux28.5.2/desktop-linux. Niezmieniony pinned PostgreSQL17 z locka obrazów
  i guarded harness B1, nowa migrowana baza na test, operacje kontem runtime.
  Stary test stack API/identity/database pozostał healthy, ale bez deploy nowego kodu.

## Niewykonane i następny krok

B2a3: osobna spec/review transportu OIDC: discovery i dokładne endpointy,
brak redirect/proxy/SSRF, deadline/body limits, issuer-bound JWKS cache TTL,
single-flight/ograniczenie unknown-kid refresh, atomowe zastąpienie i outage,
code exchange/revocation bez logowania sekretów. Dopiero potem B2b HTTP,
bootstrap i prawdziwe Keycloak + przeglądarki + raw API E2E.

Nie zaliczamy pełnego B2-AC01 tylko na podstawie komponentu offline;
B2-AC02/05/06/07 i pełne callback/session AC pozostają niewykonane.
Nadal brak restart/restore, rate limits/metrics/retention, NFR/obciążenia,
pełnych secrets/images/licenses/SBOM i ręcznego UX/a11y. Zdalne CI niewykonane.
Nie zmieniono root `.env`, legacy ani trwałego stacku `test-abcdef012345`;
bieżący obraz API nie zawiera nowej implementacji. Bez push/PR i release.
SP-01 otwarty; automatyzacja kontynuuje bezpieczny lokalny zakres.
