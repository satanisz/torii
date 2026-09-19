# SPEC-0002 — fundament infrastruktury i dostarczania

Rewizja 0.2, 2026-09-19. Status: **Accepted (delegated)**.
Podstawa: [mandat użytkownika](../../docs/platform/delivery-mandate.md).
Wymagania: NFR-01/04/05/06/07/08/09. Przyrosty: SP-01/02.

## Cel i granica

Powtarzalne środowisko API/UI/tożsamości/bazy, bez uzależniania rdzenia od
obrazu AutoML i bez naruszania działającej demonstracji. Nie obejmuje runnera
kodu użytkownika, MLflow proxy, pełnego deploymentu firmy ani konfiguracji
zdalnego GitHub bez osobnego zlecenia. Stan implementacji usług/workflow
i dowody są w [dzienniku realizacji](../../docs/platform/delivery-progress.md).

## Wybór bazowy do akceptacji

- Python 3.12 dla API i SDK kontraktowego, FastAPI/Pydantic, SQLAlchemy/Alembic;
  domena nie importuje FastAPI ani adapterów. Istniejące obrazy ML pozostają osobno.
- PostgreSQL 17: oddzielna baza platformy i baza IdP, osobne konta; instancja dev
  może być wspólna wyłącznie między nowymi usługami platformy. Nie baza MLflow.
- React + TypeScript strict, statyczny build SPA; Node 24 LTS jako linia narzędzi.
  Dokładne wersje pakietów oraz runtime patch ustalamy i zapisujemy w lockach
  przed pierwszym buildem. Zmiana major wymaga przeglądu kontraktów.
- Keycloak jako testowy OIDC, Caddy 2 jako lokalny TLS/reverse proxy.
  Wersje obrazów pinowane digestem; brak `latest`, brak kopiowania default credentials.
- `uv` + projektowy lock dla Python; npm + package-lock dla UI; instalacja frozen
  i `npm ci`. Nie budujemy produkcji z pakietów doinstalowanych ręcznie w Jupyter.

Node 24 jest linią LTS według [oficjalnej tabeli wydań](https://nodejs.org/en/about/previous-releases).
To wybór baseline, nie obietnica nieograniczonego wsparcia tej wersji.

## Topologia i konfiguracja

Proponowane pliki nowego stosu: `deploy/platform/compose.dev.yaml`,
`deploy/platform/compose.test.yaml` oraz lokalny ignorowany
`deploy/platform/.env`. Nie zmieniamy aktualnego `.env` w root ani jego mapowań.
Nowy projekt Compose `torii-platform-dev`; testy mają unikatowy identyfikator runu.
Implementacja tych plików jest przyrostem SP-01; samo ich istnienie nie zalicza AC.

| Usługa | Dostęp / dane | Ograniczenia |
|---|---|---|
| gateway | Tylko `127.0.0.1:9443` jako propozycja, preflight przed startem | TLS dev, UI/API same-origin, zaufanie tylko do własnych nagłówków proxy |
| web | Statyczne pliki builda | Brak sekretów/poświadczeń w bundle |
| api | Prywatna sieć aplikacyjna; role runtime bazy | Non-root, brak Docker socket/host mounts, brak importowania projektów użytkownika |
| identity | Prywatna sieć, publiczne ścieżki OIDC przez gateway | Oddzielne konto DB; admin UI nie jest częścią zwykłego UI Torii |
| database | Prywatna sieć, jawnie nowy wolumen | Runtime bez DDL; rola migracji oddzielna; health nie ujawnia danych |
| checks | Profil testowy, efemeryczne fixture | Może sprzątać wyłącznie własne zasoby oznaczone run ID |

Port 9443 nie jest teraz rezerwowany ani potwierdzony jako wolny. Preflight
odrzuca konflikt; nie zatrzymuje Airflow lub starego Torii, aby zwolnić port.
Przed pobraniem obrazów mierzymy budżet zasobów stacji; minimalny profil D1
projektujemy dla 4 CPU i 8 GiB dostępnych dla nowego stosu, bez obietnicy P1.

Propozycja URL publicznego: `https://localhost:9443`; issuer testowy
`https://localhost:9443/identity/realms/torii-dev`. Backend używa kontrolowanego
backchannel do identity w sieci kontenerów, ale nadal wymaga dokładnego publicznego
issuer w tokenie. Nie rozwiązujemy problemu localhost przez wyłączenie issuer/TLS
validation. Mapping endpointów token/JWKS jest konfiguracją operatora, nie
parametrem od klienta; test obejmuje discovery, login i fałszywe Host headers.
Możliwość rozdzielenia frontchannel/backchannel opisuje
[Keycloak hostname configuration](https://www.keycloak.org/server/hostname).

W dev dopuszczamy HTTP wyłącznie wewnątrz prywatnej sieci między gateway a
zaufanymi usługami; to jawny wyjątek lokalny. Profil prod musi mieć zaakceptowane
szyfrowanie sieciowe i granice zaufania. Testy przeglądarki ufają testowemu CA
w swoim profilu. Nie instalujemy CA systemowo na komputerze bez osobnej decyzji.

Nie ma domyślnego hasła. Sekrety generowane/provisionowane przed startem,
trzymane poza Git i osobno dla dev/test. Klucz szyfrowania sesji nie może być
w tym samym backupie w postaci jawnej co zaszyfrowane tokeny. Testy nigdy nie
korzystają z root keys MinIO demonstracji. Prosty secret provider dev jest
adapterem, nie obietnicą zastąpienia firmowego secret managera.

## CI i dowody

Kolejność: kontrakty/przykłady → lint/typy/unit → integration PostgreSQL/OIDC
→ build UI/API → E2E → skany/raporty. Kod UI może używać mocków podczas pracy,
ale bramka integracji wymaga prawdziwego API. Contract drift blokuje merge:
implementacja ma spełniać wersjonowane OpenAPI, nie nadpisywać go przy eksporcie.

Python: Ruff, statyczne typy, pytest. UI: TypeScript strict, lint, testy komponentów,
Playwright E2E. Testy granic modułów odrzucają importowanie adapterów przez domenę
i ML dependencies przez API. Wymagane testy ścieżek odmowy i awarii, nie wyłącznie
procent coverage. Nowa migracja musi przejść upgrade fixture poprzedniego sprintu.

Pipeline nie udostępnia sekretów niezaufanym PR/forkom. Workflow/pakiety/bazy
obrazów są przypięte, użycie runnera i uprawnień minimalne. SBOM i wyniki skanów
łączymy z commitem i digestem obrazu. Artefakty wydaniowe dostaną podpis/provenance
oraz weryfikację promocji w SPEC-0012; w SP-01 powstaje podstawa tego śladu.

Każdy raport zawiera commit, toolchain, topologię, polecenia, wynik i niespełnione
AC. Kontrole required checks/branch protection mają osobny udokumentowany stan;
sam zielony workflow nie dowodzi, że nie można go ominąć.

## Eksploatacja lokalna

Doprecyzowanie 0.2 przed kodem (przegląd bounded planu przez oddzielnego agenta):
`GET /health/live` zwraca 200 `{"status":"live"}` bez bazy;
`GET /health/ready` zwraca 200 `{"status":"ready"}` tylko przy bazie z dokładnie
wymaganą migracją, inaczej 503 Problem Details, Retry-After 3. Oba publiczne
wyłącznie przez jawnie skonfigurowany origin; bez echo DSN lub numeru schematu.
Nie przyjmują body. Wszystkie odpowiedzi, także błędy, mają no-store i nowe UUID
request ID. Obcy Host daje 400; nagłówki proxy klienta nie zmieniają origin.
Timeout 15 s obejmuje odczyt body oraz dispatch, 503 `request_timeout`.
Limit bajtów egzekwujemy przed parsowaniem; walidację treści wykonujemy dopiero
po autoryzacji właściwego zasobu. Log dostępu zawiera metodę/status/czas/request ID,
bez surowej ścieżki, query string, nagłówków, body i wyjątków zawierających wejścia.

Sekrety przez `TORII_*_FILE`; bezpośrednie `TORII_*` dozwolone wyłącznie przy
jawnym `TORII_PROFILE=test`. Dwie obecne formy (również jedna pusta) są błędem.
Brak automatycznego czytania root `.env`. Profile w tym przyroście: dev/test;
`prod` odrzucany do kwalifikacji infrastruktury. Dokładny kontrakt konfiguracji
i mapowanie AC: [plan API](../../apps/api/IMPLEMENTATION.md).

- Health liveness nie pyta bazy; readiness sprawdza bazę i zgodność schema,
  bez fałszywego green przy brakującej migracji. Endpointy nie ujawniają DSN.
- Log JSON: request ID, action, czas, status, bez tokenów, body i SQL. Błędy
  klienta mają stabilne code; stack trace tylko w chronionym logu operatora.
- Pomiar: latency/error API, pool DB, błędy logowania i audytu; bez labels
  per object/request ID, które powodują nieograniczoną kardynalność metryk.
- Timeout API 15 s, body 256 KiB, limity konfiguracji muszą być testowane.
  Proponowany rate limit dev: 120 żądań/min/principal, burst 30; login 10/min/IP.
  Limiter nie ufa dowolnemu X-Forwarded-For i nie jest jedyną ochroną DoS.
- Retencja syntetycznego dev: logi techniczne 7 dni, audyt 90 dni, receipts 24 h,
  sesje według SPEC-0001. Wersji obiektów nie sprzątamy automatycznie w S1.
  Retencja firmowa wymaga osobnej akceptacji i nie dziedziczy tych wartości.
- Backup bazy + wersja aplikacji + schema + konfiguracja bez sekretów; restore
  do nowej bazy i porównanie ID/grants/digestów/audytu. Sesje po restore
  unieważniamy, wymuszając ponowne logowanie. Stara instalacja nie jest ruszana.

## Kryteria odbioru — planowane, niewykonane

| AC | Given / When / Then | Wymagania |
|---|---|---|
| AC-01 | Świeży checkout i zadeklarowany toolchain; build z locków daje działający testowy stos bez ręcznej edycji bazy | NFR-06/07 |
| AC-02 | Działa legacy/Airflow; preflight nowego stosu nie nadpisuje env/portów/wolumenów; konflikt daje błąd bez zatrzymania obcej usługi | NFR-04/09 |
| AC-03 | Brak sekretu lub niepoprawny issuer/schema; start/readiness odrzuca konfigurację zamiast użyć hasła domyślnego | NFR-01/09 |
| AC-04 | PR zawiera błąd kontraktu, import ML do API lub test odmowy nie przechodzi; wymagany job jest czerwony i raportuje przyczynę | NFR-01/06/07 |
| AC-05 | Test podaje sekret i złośliwy nagłówek; log/bundle/raport nie ujawniają sekretu, nie przyjmują wstrzykniętego request ID | NFR-08/09 |
| AC-06 | Restart i restore nowej bazy; ID/grants/audyt zachowane, sesje wygaszone, baza demonstracji nienaruszona | NFR-04 |
| AC-07 | Zła audience/issuer, CSRF lub podmieniony proxy Host; login/API nie obniżają weryfikacji | NFR-01 |
| AC-08 | Start testu równolegle z dev i cleanup; usunięte są tylko jawnie należące do testu zasoby | NFR-04/09 |
| AC-09 | Baseline obciążenia na opisanym D1; raport latency/zasobów powstaje bez twierdzenia, że zalicza P1 | NFR-05/08 |

## Ready, implementacja i wycofanie

Do przyjęcia: powyższe rodziny technologii/topologia/limity i reviewer.
Dokładne locki/digesty są artefaktem pierwszego builda SP-01, obowiązkowe przed
jego odebraniem. Przegląd ich licencji/podatności nie może być pominięty.
Kolejność i zadania wskazuje [SP-01](../../docs/platform/sprints/01-foundation.md).
Rollback: zachowanie nowych wolumenów, wyłączenie tylko nowego stosu,
kompatybilny obraz lub restore; brak globalnego czyszczenia Docker.

Żadne AC runtime nie jest jeszcze PASS. Walidacja dokumentów nie potwierdza
działania CI, OIDC ani konfiguracji sieci. Akceptacja umożliwia implementację,
nie stanowi odbioru produktu.
