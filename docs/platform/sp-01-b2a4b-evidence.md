# SP-01 B2a4b — transport OAuth i polityka logowania

2026-10-10. Baseline funkcji `92692e6`, maintenance PyJWT `45f9eef`;
zakres: [SPEC B2a4b](../../specs/0001-project-object-version/increment-b2a4b.md)
rewizja 0.1 oraz [ADR-0008](../../adr/0008-credential-transport-logging.md).
Przyjęte niezależnie przez `regulated_examples` przed implementacją.
Kod i ten raport należą do tego samego przyrostu Git; nie jest to odbiór całego SP-01.

## Implementacja i AC

| AC | Dostarczone zachowanie i dowód |
|---|---|
| A4b-01 | Dedykowany POST składa istniejący encoder/parser, sprawdza exact DTO, stały endpoint, Basic i bounded ASCII body. Forged URL/operation/body odmawiają przed transportem. |
| A4b-02 | Raw stream bez dekompresji, limit 65536 bajtów, status/MIME/encoding/Content-Length. Tylko własny parser invalid_grant daje 401; błędy providera, także DomainError401, dają bezpieczne503. Revocation200 dopuszcza empty/nonJSON. |
| A4b-03 | Jeden POST, bez retry, redirect, proxy env lub zapisu cookies. Równoległe operacje nie przekazują Set-Cookie. Brak caller hooks/trace. |
| A4b-04 | Wspólny cutoff <=5s, kontrola przed send i po parserze, dodatkowy cooperative cleanup <=1s. Testy timeout, hanging close, cancellation i repeated cancel; closed client nie otwiera się ponownie. |
| A4b-05 | Jawny startup wyłącza dokładnie sześć emiterów przypiętych HTTPX/HTTPCore. Pin, AST manifest, idempotencja, brak init i ponowne włączenie emitera mają testy. Import nie zmienia logging. |
| A4b-06 | Syntetyczne markery w nagłówkach, treści, tokenach, reason phrase i wyjątkach nie trafiają do logów, repr lub formatted traceback. Torii emituje tylko event/operation/outcome/duration. |
| A4b-07 | Konstrukcja verified TLS, trust_env=False, brak cookies/redirects/ambient auth. Testy konfiguracji i socket guard; nie jest to prawdziwy TLS handshake lub login. |
| A4b-08 | Polityka działa przed zależnościami lifespan. Fabryka nie uruchamia jej przy imporcie. Nadal tylko dwie trasy health, bez Settings/env/migracji i zmian GET. Regresje i review opisane poniżej. |

Podział: `platform_runtime` — transport/testy; `platform_state` — polityka i
manifest/testy; root — startup/integracja; `regulated_examples` — niezależny
review i regresja wykrytego błędu. To przegląd techniczny agentów, nie audyt człowieka.

## Review i walidacja

Review wykrył P2: synchroniczne przygotowanie requestu mogło zużyć deadline,
a `asyncio.timeout_at` nie przerywa kodu bez await. Test reviewera najpierw
RED: przygotowanie150ms przy budżecie100ms nadal wywoływało transport raz.
Poprawka sprawdza cutoff po ostatnim guardzie bezpośrednio przed send.
Reviewer potwierdził zamknięcie w źródle; nie rozszerzano zakresu do nowego API.

Pierwszy przebieg root: **1527 PASS** poza katalogiem integration oraz osobno
**30 PASS** guardów harnessu, bez dostępu do DB/IdP. Dodana regresja P2 i
aktualizacja zależności wymagają końcowego przebiegu zapisanego niżej.
Ruff check/format62 pliki, strict mypy32 moduły oraz walidator OpenAPI/JCS PASS.
Walidator:21 operacji,5 valid/13 invalid fixtures,2 wektory JCS,8 request cases.

Testy asyncio na Windows uruchamiano poza sandboxem, który blokował tworzenie
wewnętrznego socketpair pętli przed wykonaniem testowanego kodu. To ograniczenie
środowiska testu; nie dodano obejścia do produktu. Nieukończonych przebiegów
nie zaliczono jako PASS. Dwa dotychczasowe ostrzeżenia deprecacyjne Starlette
(HTTPX TestClient i AnyIO BlockingPortal alias) pozostają jawne.

Kontrola zależności wykryła PyJWT2.14.0 z PYSEC-2026-4141 oraz PYSEC-2026-4183.
Wyodrębniono [SPEC-0002 M-01](../../specs/0002-engineering-baseline/maintenance-pyjwt-2.15.1.md),
przejrzaną przed aktualizacją pinu. Błędu skanu nie ukryto przez ignore.
Raport maintenance rozróżnia regresję upstream i profil RS256 Torii.

Końcowy przebieg root po poprawce i maintenance (Python3.12.12, Windows):

```powershell
# Z apps/api, po uv sync --frozen
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration' --cov
.\.venv\Scripts\python.exe -m ruff check src tests migrations
.\.venv\Scripts\python.exe -m ruff format --check src tests migrations
.\.venv\Scripts\python.exe -m mypy
```

**1565 PASS,53 deselected /20.90s**, w tym158 nowych testów B2a4b
(124 POST,31 logging,3 startup) oraz7 maintenance. Ruff/format63 pliki i
strict mypy32 moduły PASS. Transport ma93% coverage, polityka100%; całość83%
w tym przebiegu bez PostgreSQL, więc nie porównujemy jej z historycznym
łącznym coverage unit+PG. Test deadline P2 jest GREEN. Końcowy review źródła
`regulated_examples` nie pozostawił blokerów dla zakresu komponentu.
Po frozen aktualizacji PyJWT2.15.1 `pip-audit2.10.1` nie zgłasza znanych
podatności w sprawdzonych zależnościach runtime. To wynik z dnia kontroli,
nie gwarancja braku przyszłych zgłoszeń. Nie powtarzano niezmienionych testów UI.

## Granice dowodu i dalsza integracja

Nie wykonano nowego testu PostgreSQL/frontendu: ten przyrost nie zmienia ich
kodu, schematów ani kontraktów. Historyczne wyniki B1/B2a1 nie są nowym odbiorem
callback z DB. Nie wdrożono nowego obrazu API i nie wykonano zdalnego CI.
Nie było real Code+PKCE, TLS handshake, UI, IdP replay ani E2E. Niskopoziomowa
polityka logów nie kwalifikuje IdP, gateway, Uvicorn lub dowolnego APM.

`TokenReply` pozostaje niezaufany. Kolejny SP01-04b musi składać consume-flow
commit przed siecią, klucze z cache, oba podpisy/nonce/at_hash/sub i dopiero
potem sesję. Logout najpierw usuwa sesję lokalną, potem best-effort revoke.
Synchronizowanie DB, deadline i cancellation wymagają osobnego kontraktu.

SP-01 nadal In progress. B2b HTTP/cookie/CSRF/Bearer/projekty, bootstrap,
realny IdP/UI/raw API, restore, limiter/metryki/retencja, pełne skany/SBOM,
NFR i UX/a11y pozostają otwarte. Nie zaliczono SP-02, katalogu lub grafu.
Legacy, root `.env`, trwałe wolumeny i inne aplikacje bez zmian. Brak push/PR.
