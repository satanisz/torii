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

## 2026-09-19 — B2a1: trwały stan sesji (heartbeat)

Commit **`baa09bd`**: wewnętrzny Identity DTO, canonical credentials i związane
z rekordem szyfrowanie Fernet, trwały IdentityStore nad istniejącą migracją0001.
Spec B2a1 przyjęta po technicznym review przed kodem, osobno od nadal Proposed
reszty B2. Nie dodano JWT verifier, endpointów HTTP, auth bypass ani deploy.

Zaimplementowano jednokrotne browser-bound flows, provisioning bez grantów,
atomową rotację sesji, absolute8h/idle30min liczone zegarem DB po lockach,
biezący status/grant principal, lokalny revoke i bounded cleanup. Zaufany
issuer sprawdzany również przy sesji. Lokalny profil nie realizuje jeszcze
natychmiastowego federacyjnego revoke z IdP; to jawna granica, nie obietnica.

Root końcowo wykonał `./scripts/check-platform-foundation.ps1 -IncludePostgres`:
**529 backend bez DB + 53 real PostgreSQL + 50 frontend PASS**. PostgreSQL:
23 B1 +30 B2a1, run `03b28a5965ea4ec9954dc89734c1aea9`,86.04s, bez skipów.
Ruff/format/strict mypy, kontrakty, lint/types/build, oba audyty zależności,
35 kontroli PowerShell oraz staged diff check PASS. Dwa znane ostrzeżenia
deprecation pozostały jawne. Zdalnego CI nie uruchamiano.

Review zamknął dwa konkretne problemy: obcy trusted issuer przy starej sesji
oraz mylenie operacyjnej awarii decrypt z corrupt ciphertext. Testy pure i PG
potwierdzają fail-closed/no-touch, rollback i brak sekretów w błędach. Reviewer
niezależnie powtórzył256 testów wartości/boundary. To przegląd agenta, nie audyt
ludzki. Szczegółowy zakres i dowody: [raport B2a1](sp-01-b2a1-evidence.md).

Własne efemeryczne kontenery/sieci usunięto po kontroli ID/etykiet; tmpfs z
danymi syntetycznymi odrzucono. Nie zmieniono root `.env`, legacy wolumenów,
trwałego stacku `test-abcdef012345`, zdalnego repo ani zasobów firmowych.
Nie wykonano push/PR. Kontrola13 znanych lokalnych sekretów w staged diff PASS;
nie zastępuje to pełnego skanu sekretów/historii. Testowy API nadal jest starym
obrazem fundamentu; jego health nie potwierdza wdrożenia B1/B2a1.

### Następny krok — nie powtarzać B1 ani B2a1

SP-01 nadal **w realizacji**, SPEC-0001/0002/0017 bez pełnego Verified.

1. B2a2: wydzielić i niezależnie przejrzeć spec JWT/OIDC transportu z planu B2:
   D02 (profil tokenów przypiętego Keycloak), pozostałe limity D06, discovery/
   JWKS/rotation, signature/audience/nonce/at_hash i code exchange. Dopiero po
   review implementacja. Użyć B2a1 jako persistence; Identity jest DTO, a nie
   dowodem sprawdzenia tokenu. Żadnych raw claims z requestów do store.
2. B2b: osobne doprecyzowanie HTTP/callback/logout/CSRF, projekty FastAPI,
   izolowany bootstrap oraz wieloużytkownikowy Keycloak/UI/raw API E2E.
   Nie traktować mocka JWT, session store ani discovery health jako loginu.
3. B2-AC03/04 mają dowód częściowy persistence, nie pełny callback/exchange;
   B2-AC01/02/05/06/07 nadal niewykonane. Restart/restore, rate limits/metrics/
   retencja, NFR, pełne skany images/licenses/secrets/SBOM, ręczne UX/a11y
   pozostają obowiązkowe przed zamknięciem SP-01. Bez przejścia do SP-02.
4. Kontynuacja lokalna nie wymaga obecnie decyzji użytkownika; automatyzacja
   pozostaje aktywna. Nie markować całej roadmapy ani enterprise jako gotowych.

## 2026-09-19 — B2a2: offline JWT/JWKS (heartbeat)

Commit **`826479f`**: weryfikacja podpisów i claims JWT, oddzielne ścieżki
access oraz login ID+access, niemutowalny publiczny zestaw kluczy związany
z issuer. Przed kodem przyjęto spec B2a2 po niezależnym review; lokalny profil
D02 sprawdzono w exact-tag źródłach Keycloak26.7.4 i metadanych obrazu.
Nie jest to obserwacja tokenu ani dowód runtime konfiguracji IdP.

Nowy kod korzysta z istniejącego PyJWT/cryptography i nie dodaje zależności,
HTTP, DB writes, transportu sieciowego lub deploy. Bounded parsing odrzuca
duplicate JSON/niekanoniczne base64, złe klucze i header extensions. Access/ID
mają rozłączne reguły, nonce/at_hash i sprawdzanie czasu; wynik nie nadaje praw.
Limit128 znaków literału liczbowego zapisano i przejrzano przed poprawką parsera;
regresje najpierw RED. Nie zmieniano globalnych limitów Pythona.

Root `./scripts/check-platform-foundation.ps1 -IncludePostgres`: **PASS**:
**885 backend bez DB + 53 real PostgreSQL + 50 frontend**. Nowe testy offline356;
PG to niezmienione23 B1 +30 B2a1, nie dowód integracji JWT z DB. Run
`3545abbbdb7043cea6562b27453708f4`:53 PASS,88.76s, bez skipów. Ruff/format46
plików, strict mypy25 source files, kontrakty/JCS/API drift, frontend lint/
types/build, audyty zależności i35 PowerShell checks PASS. Dwa znane deprecation
warnings i rekomendacja pip-audit dot. hashy pozostają jawne.

Reviewer niezależnie uruchomił356 nowych testów: PASS; końcowy review GREEN,
bez pozostałych findings dla zakresu offline. Klucze/prywatne materiały fixture
tylko w RAM. To review agenta i realna kryptografia syntetycznych tokenów,
nie audyt człowieka ani E2E. [Pełne dowody](sp-01-b2a2-evidence.md).

Własny kontener/sieć runu usunięto po guardach, syntetyczny tmpfs odrzucono;
brak pozostawionych zasobów b1-integration. Stary stack zdrowy i niezmieniony.
Root `.env`, legacy/trwałe wolumeny, zasoby firmy i remote nienaruszone;
brak push/PR. Scoped staged check13 znanych lokalnych sekretów PASS, nie jest
pełnym skanem historii. API nadal działa na starszym obrazie fundamentu.

### Następny krok — B2a3, bez powtarzania ukończonych komponentów

1. Wydzielić z Proposed B2 spec transportu discovery/JWKS/code exchange,
   review przed kodem. D06: dokładne origin/realm endpoints, brak redirectów/
   proxy env i URL z JWT, bounded body/deadline, brak automatycznego retry POST.
2. Zdefiniować cache per issuer/proces: TTL monotoniczny<=5min, single-flight,
   unknown-kid refresh<=1/30s także po awarii, atomowe zastąpienie kluczy,
   fail-closed bez ważnego cache; testy rotacji/removal/outage i storm.
   Wykorzystać B2a2 SigningKeys/TokenVerifier, nie implementować ich ponownie.
3. Code exchange/revocation: konsumowany B2a1 flow commit PRZED siecią,
   wspólny deadline, nonce/at_hash verification, brak sekretów w błędach/logach.
   Callback/provisioning/sesja i HTTP B2b później po własnych kontraktach;
   nie podłączać niezweryfikowanych raw claims do IdentityStore.
4. Wciąż brak full B2-AC01 (łączenie z persistence), B2-AC02/05/06/07,
   prawdziwego Keycloak/UI/raw API E2E i pozostałych bramek SP-01 (DR, NFR,
   limiter/metryki/retencja, pełne skany/SBOM i ręczne UX/a11y). Nie zaliczać
   loginu na podstawie offline podpisów, discovery czy zdrowego kontenera.
5. SP-01 w realizacji, cały SPEC-0001/0002/0017 nie Verified, SP-02 jeszcze
   nie rozpoczynać. Lokalny następny przyrost nie wymaga decyzji firmy;
   automatyzacja kontynuacji pozostaje aktywna, bez udawania odbioru enterprise.

## 2026-09-19 — B2a3: ograniczony transport metadanych i cache OIDC

Commit **`21bc4f0`**: GET discovery/JWKS do ustalonych endpointów, publiczne
klucze z B2a2, cache per issuer/loop, TTL300s, single-flight i cooldown30s także
po awarii/anulowaniu. Brak redirect/proxy env/provider cookies, bounded raw
stream bez dekompresji, fail-closed i atomowa wymiana snapshotu. Bez nowych
routes, DB writes, konfiguracji, zależności, migracji lub wdrożenia.

Spec przyjęto po niezależnym review przed implementacją. Testy rozpoczęły RED.
Review zamknął InvalidURL poza safe boundary, nieograniczony cleanup oraz
pomylenie obsłużonego cancellation callera z anulowaniem nowej operacji.
Zapisano granicę runtime CPython dla inherited caller context; provider chain
nadal odrzucany, brak markera w formatted traceback i brak pozornego sukcesu.
Cleanup ma osobny cooperative limit1s, który przyszły callback MUSI zarezerwować
w końcowym budżecie; nie ma detached tasks ani obietnicy hard realtime.

Finalna walidacja root `./scripts/check-platform-foundation.ps1 -IncludePostgres`:
**1086 backend +53 real PostgreSQL +50 frontend PASS**, exit0. Nowe testy201;
PG to regresja istniejącego B1/B2a1, nie integracja OIDC z persistence.
Run `594c5b19a12743cf999f1e241d85382e`:53 PASS,88.35s; zasoby usunięte po guardach,
tmpfs odrzucony, brak pozostawionych kontenerów/sieci b1-integration.
Ruff/format52, mypy28, kontrakty/JCS, FE lint/types/build/drift, audyty zależności
i35 kontroli PowerShell PASS. Dwa znane dependency deprecation warnings oraz
rekomendacja pip-audit dot. hashy pozostają jawne; zdalnego CI nie uruchamiano.

Finalny niezależny review GREEN,201 testów ponownie PASS/6.94s. Testy łączą
symulowane raw HTTP z rzeczywistą kryptografią RSA; nie dowodzą TLS/DNS/socket
timeouts ani Keycloak loginu. [Pełny raport i ograniczenia](sp-01-b2a3-evidence.md).
Scoped staged check13 lokalnych sekretów PASS, nie pełny skan historii.
Root `.env`, legacy/trwałe zasoby, firma i remote bez zmian; brak push/PR.
Trwały API nadal na starszym obrazie fundamentu, bez deploy nowego komponentu.

Przerwę w realizacji spowodował limit usługi agentów; automatyczne heartbeat
w tym okresie nie oznaczają dodatkowo wykonanej pracy. Wznowiono istniejący WIP,
nie przepisywano ukończonych B1/B2a1/B2a2. Nie jest to blokada decyzją firmy.

### Następny krok — B2a4, bez powtarzania B2a3

1. Spec i review code exchange/revocation przed kodem. Użyć B2a3 metadata/cache
   oraz B2a2 TokenVerifier zamiast duplikowania podpisów. Token response bounded,
   token_type Bearer, oba podpisy/nonce/at_hash i zgodny issuer/sub; brak POST retry.
2. Bezpieczne DTO i profil logowania PRZED przekazywaniem credentials: HTTPX INFO
   loguje URL/reason, httpcore DEBUG może logować headers/exception. Obecne moduły
   nie dodają logów, ale to nie jest dowód pełnej ochrony logowania.
3. Zdefiniować orchestration i wspólny deadline z1s rezerwą cleanup. B2a1
   consume_flow commit PRZED siecią, brak DB locks podczas HTTP, sesja dopiero
   po pełnej walidacji, refresh szyfrowany dla best-effort revoke, bez auto refresh.
   B2b HTTP/cookie/CSRF/projekty oraz bootstrap/E2E wymagają osobnego kontraktu.
4. B2-AC01/02/03/04 nadal częściowe; B2-AC05/06/07, real Keycloak/UI/raw API,
   DR/restore, rate limits, retencja, metryki, NFR, pełne skany/SBOM i UX/a11y
   nie są zaliczone. SP-01 In progress; SPEC-0001/0002/0017 nie Verified.
   Nie rozpoczynać SP-02, nie ogłaszać enterprise ani pełnego loginu.
5. Kolejny lokalny przyrost nie wymaga decyzji użytkownika. Kontynuacja pozostaje
   aktywna; nie wstrzymywać automatyzacji z powodu samego podziału prac na przyrosty.

## 2026-09-19 — B2a4a: kodowanie i parsowanie komunikatów OAuth

Commit **`0e8de81`**: czysty encoder form/client_secret_basic oraz parser
bounded niezaufanych tokenów i odpowiedzi revocation. Stałe cele/callback,
canonical PKCE, ścisłe typy/limity, brak parameter injection i pól w repr.
Bez I/O, DB, tras, konfiguracji, nowych zależności ani deploy. To komponent
do wymiany kodu, nie wykonana wymiana, zweryfikowana tożsamość lub login.

Spec Accepted (delegated) po review PRZED implementacją, wszystkie trzy pliki
testów zaczęły RED. Agenci: rozłączne parser/testy oraz niezależne attack vectors;
root: encoder/integracja. Końcowy contract_review GREEN, niezależnie314 PASS.
Pełna bramka root `./scripts/check-platform-foundation.ps1 -IncludePostgres`:
**1400 backend +53 PostgreSQL +50 frontend PASS**, exit0. Nowych314 testów.
PG run `6c68a08b3558470b87e65362828fe98e`:53 PASS89.78s, regresja B1/B2a1,
nie integracja OAuth z DB. Ruff/format57, mypy30, kontrakty/JCS/API drift,
FE lint/types/build, audyty zależności i35 kontroli PowerShell PASS.
Dwa znane deprecation warnings i rekomendacja pip-audit dotycząca hashy jawne.
[Dowody, źródła i granice](sp-01-b2a4a-evidence.md).

Własny kontener/sieć usunięte po guardach, syntetyczny tmpfs odrzucony;
brak zasobów b1-integration po runie. Scoped staged check13 sekretów PASS,
nie pełny skan historii. Root `.env`, legacy/trwałe zasoby, istniejący stack,
firma/remote nienaruszone, brak push/PR. API nie zostało wdrożone na nowo.

### Następny krok — B2a4b, bez powtarzania komunikatów A4a

1. ADR + spec i niezależny review przed kodem bounded POST oraz polityki
   logowania przy starcie procesu. Bez automatycznych retry, proxy env,
   redirects/cookies, provider exception chains i sekretów w logach. Transport
   sam egzekwuje fixed URL nawet dla ręcznie skonstruowanego OAuthRequest.
2. Wstępny review zaleca jawne wyłączenie emitujących loggerów HTTPX/HTTPCore
   przy starcie i fail-closed guard przed credentials I/O. Koszt całego procesu
   wymaga ADR. Źródłowe nazwy i upgrade guard opisane w raporcie A4a.
   Nie zmieniono jeszcze logging; Uvicorn/gateway/APM osobno przed B2b.
3. Przed real Code+PKCE/replay testami ustalić politykę logów testowego IdP:
   Keycloak26.7.4 PkceUtils DEBUG ujawnia verifier, OAuth2CodeParser WARN przy
   replay składniki zużytego kodu. Nie dumpować raw logów jako artefaktów testu.
4. Osobna spec orchestration: consume_flow commit PRZED HTTP, deadline z rezerwą
   cleanup, B2a2 podpisy/nonce/at_hash/sub przed sesją, szyfrowany refresh,
   best-effort revoke bez auto-refresh. HTTP/cookie/CSRF/projekty, izolowany
   bootstrap i prawdziwe Keycloak/UI/raw API E2E pozostają B2b.
5. SP-01 In progress; SPEC-0001/0002/0017 nie Verified. Całe B2-AC01/02/03/04
   nadal częściowe, B2-AC05/06/07, DR/NFR/retencja/limiter/metryki, pełne skany/
   SBOM i UX/a11y pozostają otwarte. Nie rozpoczynać SP-02 ani ogłaszać enterprise.
   Bez nowej wymaganej decyzji użytkownika, automatyzacja kontynuacji aktywna.
