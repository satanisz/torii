# SP-01 B2a3 — pobieranie metadanych i cache kluczy OIDC

2026-09-19. Baseline `a2c319b`; kod/spec/testy: **`21bc4f0`**. Zakres:
[SPEC B2a3](../../specs/0001-project-object-version/increment-b2a3.md),
Accepted (delegated) po niezależnym review przed kodem. To komponent do przyszłego
logowania, nie nowe endpointy API ani pełny odbiór SP-01.

## Dostarczony zakres

- `security/oidc_transport.py`: ścisłe, niemutowalne public/backchannel realm
  endpoints; discovery nie wybiera celu sieciowego. Dedykowany HTTPX AsyncClient:
  TLS verification, brak redirectów, env proxy/CA oraz przechowywania cookies.
  GET status200, strict bounded JSON/JWKS, identity encoding bez decompression,
  stream64KiB i wspólny workdeadline z limitem5s na operację.
- `security/oidc_cache.py`: jeden issuer/proces/loop, monotoniczne TTL300s,
  pojedyncze odświeżenie i cooldown30s wszystkich prób (również cold/failure/cancel).
  O(1) snapshotów, bez słownika negatywnych kid. Atomowa pełna wymiana kluczy;
  awaria nie przedłuża TTL i nie dopuszcza stale keys. Ważny znany klucz może
  działać podczas outage, natomiast nieznany nie otrzymuje losowego fallback.
- Cache zwraca tylko SigningKeys; autoryzacja nadal wymaga B2a2 podpisu/claims
  i B2a1/B1 uprawnień. Żadnych nowych grants, DB writes, tras, migracji, zmian
  dependencies/env ani deploymentu. Code exchange/revocation wydzielono do B2a4.

## Spec-first i niezależna kontrola

Przed kodem contract_review zaakceptował zakres po uściśleniu polityki cookies,
aktywnego timeout lock waitera i Content-Type/charset. Infra sprawdził źródła
zainstalowanego HTTPX0.28.1/h11: eager mock response nie testuje raw stream,
timeout HTTPX nie jest deadline całego body, a h11 może normalizować identyczne
Content-Length przed adapterem. Te granice zapisano w spec przed implementacją.

Trzy pliki testów rozpoczęły od RED collection brakujących modułów. Root wykonał
cache, frontend transport, infra niezależne testy fake HTTP -> cache -> real RSA.
Wczesny review cache GREEN, późniejsze dodatkowe testy obejmują dwa różne kid,
cross-loop odmowę, jawny waiter.cancel oraz świeże klucze przy wygasłym discovery.

Review ujawnił konkretne usterki przed odbiorem:

1. `httpx.InvalidURL` nie dziedziczy po HTTPError/ValueError. Rzeczywisty parser
   HTTPX dla błędnego numerycznego hosta omijał bezpieczne503. Dodano mapowanie
   i regresje actual parser/injected marker, bez wykonywania sieci.
2. Timeout body nie ograniczał późniejszego `aclose`. HTTPX zamyka także wewnątrz
   `aiter_raw` oraz przy złym Location jeszcze przed zwrotem odpowiedzi. Po
   osobnym review i aktualizacji spec PRZED poprawką przyjęto pojedynczy
   cooperative cleanup do1s, bez detached tasks/retry. Response hook ogranicza
   close strumienia także w wewnętrznych ścieżkach HTTPX; lifecycle ma ten sam
   limit. Pierwotne zewnętrzne cancellation ma pierwszeństwo nad close fault.
3. Pierwsza poprawka rozpoznawała cancellation przez `sys.exception()` i mogła
   pomylić obsłużony wyjątek callera z anulowaniem nowej operacji, tłumiąc błąd
   close jako sukces. Dwie regresje miały RED (brak oczekiwanego503). Usunięto
   heurystykę; cancellation rozpoznaje wyłącznie lokalny handler rzeczywiście
   anulowanego odczytu. Dodano cztery testy cache w handlerach callera i mały
   `oidc_errors.py`: własny nowy błąd, `raise from None`, defensywne usunięcie
   kontekstu. Nie zmienia to ogólnego DomainError ani istniejących B2a1/B2a2.

Odczytowa reprodukcja integratora i reviewera potwierdziła granicę CPython3.12:
po timeout runtime może dołączyć na nowo ten sam obsłużony wcześniej wyjątek
callera, nawet po clear i ponownym catch na public boundary. Nie jest to kontekst
providera. Przed finalnym testem doprecyzowano spec: w tym scenariuszu dozwolone
wyłącznie None albo dokładnie ten sam istniejący obiekt callera, przy
`__suppress_context__=True`, cause=None i braku markera w formatted traceback.
Zwykłe testy błędów zależności nadal wymagają context=None; nie dopuszczono
arbitrary chain i nie obniżono wymagania503 dla nieudanego close.

Dziewięć regresji przed poprawką: **7 FAIL, 2 PASS /8.87s**. Po poprawce trzy
nowe zestawy: **195 PASS /5.92s**, a po dodatkowym review i regresjach ambient
handlera: **201 PASS /6.78s**. Realclock hanging close testy mają watchdog,
sprawdzają brak fałszywego sukcesu i zadań pozostawionych w tle. Nie twierdzą,
że uszkodzony/zawieszony provider faktycznie zamknął zasób. Cleanup może dodać
do1s do workdeadline; przyszły callback musi zarezerwować tę sekundę w całym
budżecie15s. Transport tłumiący cancellation nie ma gwarancji hard realtime.

Prace zostały przerwane limitem usługi agentów i wznowione z zachowanego drzewa;
kolejne powiadomienia heartbeat nie są dowodem wykonania dodatkowych sprintów.

## Wykonane testy i granice dowodów

| Zestaw | Zakres |
|---|---|
| `test_oidc_transport.py` (150) | URL/config, exact endpoints, status/headers/limits, timeout/close, env/TLS ustawienia, cookies, safe faults i regresje cleanup/InvalidURL/ambient cancellation |
| `test_oidc_cache.py` (36) | Cold/single-flight/cooldown, TTL dokładne granice, replacement/removal, outage, dwa kid, cancel leader/waiter, cross-loop, błędne budżety i bezpieczne wyjątki |
| `test_oidc_metadata_attacks.py` (15) | Fake raw HTTP -> klucze -> realny podpis, podmiana RSA, rotacja same-kid, hostile discovery, 304/503, storm, cancellation i deadline |

RSA/token fixtures wyłącznie syntetyczne i w RAM. MockTransport nie dowodzi
rzeczywistych DNS/TLS/puli/socket timeout lub konfiguracji Keycloak. Wstrzyknięty
PoolTimeout dowodzi mapowania błędu, nie działania puli. Konfigurację verify=True,
trust_env=False i limity sprawdzono osobno; nie podłączano się do IdP.

Torii nie dodaje logów zawierających sekrety. Nie uznajemy tego za pełną
kwalifikację logowania: HTTPX INFO zawiera URL/reason, httpcore DEBUG może zawierać
headers/exception. B2a4/B2b muszą rozstrzygnąć bezpieczny profil logowania przed
przekazywaniem credentials. Nie zmieniono globalnych loggerów ani CA stacji.

## Końcowa walidacja i zasoby

Root po zamrożeniu kodu: `./scripts/check-platform-foundation.ps1 -IncludePostgres`
**PASS, exit0**. **1086 backend bez DB + 53 real PostgreSQL + 50 frontend PASS**.
Nowe201 testów, wcześniejsze885 stanowią regresję. Testy PostgreSQL nadal
23 B1 +30 B2a1, nie są dowodem integracji OIDC z bazą. Finalny run
`594c5b19a12743cf999f1e241d85382e`:53 PASS,88.35s, bez skipów. Wcześniejszy run
`92157d2c71644f22bbfe3c584202e87a`:53 PASS,91.97s, przed ostatnimi regresjami.

Ruff/format52 plików, strict mypy28 source files, OpenAPI21 operations/JCS/
fixtures, frontend lint/types/API drift/build, pip-audit i npm audit oraz
35 kontroli PowerShell PASS. Coverage łącznie97%, transport96%, cache/helper100%
nie są dowodem braku luk. Dwa znane deprecation warnings (Starlette/httpx,
AnyIO alias) i rekomendacja pip-audit dotycząca pełnych hashy pozostają jawne.
Nie uruchamiano zdalnego CI, obrazowych skanów ani real Keycloak E2E.

Finalny contract_review **GREEN**, bez pozostałych findings; niezależny run
trzech zestawów: **201 PASS /6.94s**. To review agenta, nie ludzki audyt.
26 lokalnych odnośników w pięciu zmienionych dokumentach i staged diff check PASS.
Scoped kontrola13 znanych lokalnych sekretów w staged diff PASS; nie jest pełnym
skanem repozytorium/historii ani SBOM.

Oba własne efemeryczne kontenery/sieci usunięto po guardach, syntetyczne dane
tmpfs odrzucono. Końcowy odczyt etykiety b1-integration nie znalazł kontenerów
ani sieci. Nie zmieniono root `.env`, legacy lub trwałych wolumenów, istniejącego
stacku, remote ani zasobów firmy. Brak push/PR. API trwałej instancji nadal
jest wcześniejszym obrazem fundamentu; nie przedstawiamy health jako deploy.

## Dalszy krok i niezaliczone bramki

B2a4 wymaga własnej spec/review przed kodem: code exchange i best-effort revoke,
bounded odpowiedzi tokenów, brak POST retry, sekretne DTO/repr/logi, wspólny
budżet z rezerwą cleanup oraz orchestration z consume_flow commit PRZED siecią.
Nie dodawać bypass tokenów ani wydawania grantów na podstawie claims.

B2b nadal: HTTP/cookies/CSRF, fasada projektów, jawny izolowany bootstrap,
wieloużytkownikowy Keycloak + UI + surowy API E2E. Całe B2-AC01/02/03/04 nie są
zaliczone przez te testy komponentowe, a B2-AC05/06/07 pozostają do wykonania.
DR/restore, rate limits, retencja, metryki, NFR, pełne skany/SBOM i UX/a11y są
obowiązkowe. SP-01 In progress, SPEC-0001/0002/0017 nie Verified; bez SP-02.
Nie potrzeba obecnie nowej decyzji firmy do następnego lokalnego przyrostu.
