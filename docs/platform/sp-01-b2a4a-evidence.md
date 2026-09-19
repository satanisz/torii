# SP-01 B2a4a — czyste komunikaty OAuth

2026-09-19. Baseline `706654e`; kod/spec/testy **`0e8de81`**. Zakres:
[SPEC B2a4a](../../specs/0001-project-object-version/increment-b2a4a.md),
Accepted (delegated) po niezależnym review przed kodem. Jest to formatowanie
żądań i parsowanie niezaufanych odpowiedzi, nie wykonana wymiana kodu ani login.

## Dostarczony zakres i traceability

| AC | Implementacja i dowód |
|---|---|
| A4a-01 | OAuthRequests: RFC6749 form-encoding obu credentials przed Basic Base64; literalne wektory UTF-8, colon/plus/percent/spacje |
| A4a-02 | Stałe endpointy z RealmEndpoints, public origin callback, zamknięte listy pól form; injection nie zmienia parametrów; code401 przed canonical PKCE503; UTF-8 byte bounds secret |
| A4a-03 | TokenReply: strict bounded JSON B2a2, token_type Bearer, wymagane/optional pola, duplikaty i limity także w ignorowanych extensions; unsigned token pozostaje niezaufanym stringiem, nie Identity/grant |
| A4a-04 | Revocation exact int200 i bounded bytes, także empty/nonJSON; ignorowana treść nie dowodzi cofnięcia access JWT ani SSO logout |
| A4a-05 | Frozen/slotted repr bez pól, safe errors bez markerów/provider chain, niezależny guard socket/HTTP client/DB/logger; review GREEN i regresje |

OAuthRequest jest zwykłym sekretnośnym DTO, nie capability potwierdzającą URL.
Przyszły adapter musi sam sprawdzać swój skonfigurowany cel; jawny odczyt pól,
asdict lub debugger może ujawnić sekrety. TokenReply nie sprawdza podpisów.
Nie dodano I/O, DB writes, tras, ustawień, zależności, migracji ani deploy.

## SDD i kontrola

Przed kodem review doprecyzował exact int status, pierwszeństwo code401 przed
verifier503 oraz rozdzielenie walidacji pól200 od klasyfikacji error400.
Wszystkie trzy zestawy zaczęły od RED collection brakujących modułów.
Root: encoder i60 testów; frontend: parser i215 testów; infra:39 niezależnych
testów ataków. Agenci mieli rozłączne pliki; nie commitowali.
Root uruchomił razem **314 PASS /0.27s**. Końcowy contract_review przeczytał
oba moduły i wszystkie testy, powtórzył **314 PASS /0.27s**, wynik **GREEN**,
bez pozostałych findings. To przegląd agenta, nie audyt człowieka.

Baseline przed zmianą: **1086 PASS,53 deselected /8.47s**. Root uruchomił
`./scripts/check-platform-foundation.ps1 -IncludePostgres`: **PASS, exit0**.
**1400 backend +53 real PostgreSQL +50 frontend PASS**. Backend10.93s;
PG run `6c68a08b3558470b87e65362828fe98e`:53 PASS89.78s, FE50 PASS7.80s.
PG to regresja B1/B2a1 (23+30), nie integracja OAuth z bazą.
Ruff/format57 plików, strict mypy30 source files, OpenAPI21 operations,
fixtures/JCS/API drift, frontend lint/types/build, pip-audit/npm audit oraz
35 kontroli PowerShell PASS. Coverage łącznie97%, parser100%, encoder96%;
niepokryty guard nadmiarowego body jest obroną na przyszłą zmianę pól,
publiczne wejścia w przyjętych limitach nie mogą go osiągnąć.
Dwa znane warnings Starlette/httpx i AnyIO alias oraz rekomendacja pip-audit
dotycząca hashy pozostają jawne. Nie uruchamiano zdalnego CI ani skanów obrazów.

Własny efemeryczny kontener i sieć usunięte po guardach ID/etykiet; syntetyczne
dane tmpfs odrzucone. Końcowy odczyt Docker nie znalazł zasobów b1-integration.
Root `.env`, legacy/trwałe wolumeny, istniejący stack, firma i remote bez zmian.
Brak push/PR, wdrożenia i zmian globalnego CA. Scoped staged check13 znanych
lokalnych sekretów PASS, nie pełny skan repozytorium/historii. Trwała instancja
API nadal używa wcześniejszego obrazu fundamentu, nie nowego modułu.

## Źródła i konieczne granice kolejnego etapu

Integrator sprawdził pierwotne [RFC6749](https://www.rfc-editor.org/rfc/rfc6749.html)
i [RFC7009](https://www.rfc-editor.org/rfc/rfc7009.html). Rozmiary komunikatów
są polityką Torii, nie uniwersalną gwarancją kompatybilności IdP.
Research przypiętych źródeł przez infra:

- [Keycloak BasicAuthHelper26.7.4](https://github.com/keycloak/keycloak/blob/26.7.4/core/src/main/java/org/keycloak/util/BasicAuthHelper.java#L66)
  dekoduje form obie strony; zwykły [HTTPX BasicAuth0.28.1](https://github.com/encode/httpx/blob/0.28.1/httpx/_auth.py#L139)
  nie wykonuje potrzebnego wstępnego form-encoding.
- [OAuth2CodeParser](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/utils/OAuth2CodeParser.java#L97)
  konsumuje kod; nie wolno automatycznie ponawiać POST przy nieznanym wyniku.
- [TokenRevocationEndpoint](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/endpoints/TokenRevocationEndpoint.java#L141)
  może zwrócić200 z treścią dotyczącą invalid token; nie wymagamy JSON sukcesu.
- [PkceUtils DEBUG](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/utils/PkceUtils.java#L112)
  zawiera verifier; [OAuth2CodeParser replay WARN](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/utils/OAuth2CodeParser.java#L98)
  zawiera składniki pozwalające odtworzyć zużyty kod. Przed real E2E potrzebna
  jawna polityka IdP; nie kopiować surowych logów Keycloak do artefaktów replay.

Źródła nie zastępują real Code+PKCE E2E. Nie wywoływano IdP, nie mintowano
tokenów instancji ani nie czytano jej logów. Wszystkie komunikaty syntetyczne.

Następny B2a4b wymaga krótkiego ADR i Accepted spec przed kodem: jawna polityka
logowania przy starcie procesu, bounded POST bez retry, lifecycle z B2a3,
stateless cookies, guard URL/headers/body i wspólny deadline. Wstępny review
zaleca wyłączyć emitujące loggery przypiętych bibliotek, nie globalne logging.disable
ani per-request przełączanie poziomów. Inspekcja źródeł HTTPX/HTTPCore wskazała
`httpx`, `httpcore.connection`, `httpcore.http11`, `httpcore.http2`,
`httpcore.proxy`, `httpcore.socks`; manifest wymaga upgrade guard. Koszt dotyczy
całego procesu API, nie tylko OIDC, i musi być jawny w ADR. Nie zmieniono jeszcze
żadnej polityki logging. Uvicorn/gateway/APM/IdP to osobne powierzchnie.

Orchestration później: B2a1 consume_flow commit PRZED siecią, oba podpisy/
nonce/at_hash/sub z B2a2, zapis sesji dopiero po walidacji, szyfrowany refresh
i best-effort revoke, bez auto-refresh. Nie duplikować ukończonych komponentów.
B2b nadal wymaga HTTP/cookies/CSRF/projektów, izolowanego bootstrap i realnych
Keycloak/UI/raw API E2E. SP-01 In progress; SPEC-0001/0002/0017 nie Verified.
DR/restore, NFR, metryki/limiter/retencja, pełne skany/SBOM oraz UX/a11y otwarte.
Brak nowej wymaganej decyzji firmy; kontynuacja pozostaje aktywna.
