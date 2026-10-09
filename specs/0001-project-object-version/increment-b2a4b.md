# SPEC-0001 B2a4b — transport komunikatów OAuth i ochrona logów

Rewizja 0.1, 2026-10-10. Status: **Accepted (delegated)**. Właściciel: integrator Torii.
Niezależny review przed kodem: `regulated_examples`, 2026-10-10, bez blokerów.
Zakres akceptacji: lokalny SP01-04a; bez orkiestracji, rzeczywistego loginu lub
odbioru enterprise. Autor specyfikacji nie zatwierdzał własnej pracy.
Przyrost SP01-04a, podzbiór B2-D06/B2-AC02 oraz SPEC-0001 AC-10/14.
Decyzja procesu logowania: [ADR-0008 Accepted](../../adr/0008-credential-transport-logging.md).

## Problem i zakres

[B2a4a](increment-b2a4a.md) potrafi kodować żądania i parsować niezaufane
odpowiedzi. Brakuje ograniczonego transportu POST i jawnej ochrony przed
zapisem credentials przez biblioteki HTTP. Istniejący B2a3 obsługuje wyłącznie
metadata GET/cache; nie przenosimy do niego wymiany kodu ani nie przepisujemy go.

Przyrost dodaje klienta token/revocation, politykę logowania przy starcie API
i testy komponentów. Nie dodaje orkiestracji flow/sesji, weryfikacji JWT,
grantów, DB, migracji, nowych tras, cookies przeglądarki, UI ani deploy.
Wynik `TokenReply` pozostaje niezaufany; sukces POST nie jest loginem.
Orkiestracja, B2b i realny Code+PKCE E2E mają osobne bramki.

## Publiczny kontrakt komponentów

Nowy moduł `security/credential_logging.py`:

- `configure_credential_logging() -> None`: jawna, idempotentna inicjalizacja
  polityki procesu; bez I/O sieciowego i bez efektu przy samym imporcie.
- `assert_credential_logging() -> None`: sprawdzenie, że polityka została
  zainicjalizowana i pozostaje aktywna. Odmowa: bezpieczne
  `503 identity_unavailable`, bez danych z wyjątków bibliotek.

Nowy moduł `security/oidc_exchange.py`:

```python
OidcCredentialTransport(
    endpoints: RealmEndpoints,
    client_id: str,
    client_secret: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
)
async exchange(code: str, verifier: str, *, deadline: float) -> TokenReply
async revoke(refresh_token: str, *, deadline: float) -> None
async aclose() -> None
```

Klient składa istniejące `OAuthRequests`, `TokenReply.from_response` oraz
`validate_revocation_response`; nie implementuje ponownie Basic/form ani JWT.
`transport` jest zaufanym punktem wstrzykiwania transportu testowego, nie
parametrem żądania użytkownika. Nie przyjmujemy gotowego klienta HTTPX,
zewnętrznych hooks, `httpx.Request`, dowolnych nagłówków lub callbacków trace.
`repr/str` klienta nie ujawnia endpointów, credentials lub komunikatów.

Prywatny transport POST nadal przyjmuje i sprawdza własny `OAuthRequest`.
Nie polega wyłącznie na użyciu enkodera: testy wstrzykują również ręcznie
skonstruowane DTO z obcym URL, nagłówkiem lub body. Konstruktor nie otwiera
połączenia. Właściciel klienta jawnie kończy jego async lifecycle.

## Polityka logowania procesu

Przypięty profil: **HTTPX 0.28.1, HTTPCore 1.0.9** z obecnego `apps/api/uv.lock`.
Manifest emitujących loggerów, sprawdzony w źródłach obu pakietów:

| Pakiet | Dokładne nazwy |
|---|---|
| HTTPX | `httpx` |
| HTTPCore | `httpcore.connection`, `httpcore.http11`, `httpcore.http2`, `httpcore.proxy`, `httpcore.socks` |

1. `configure_credential_logging` sprawdza wersje obu zainstalowanych pakietów
   i ustawia `disabled=True` na każdym loggerze manifestu. Nie wystarcza zmiana
   poziomu loggera rodzica, bo loggery potomne mają własną emisję. Nie używamy
   globalnego `logging.disable`, filtracji sekretów regexem ani przełączania
   poziomów per request. Inne loggery Torii pozostają aktywne.
2. Funkcja jest wywołana w `app.py` na początku lifespan, przed inicjalizacją
   zależności mogących wykonywać credentials I/O. Sam import lub `create_app`
   nie zmienia globalnej polityki. Testy samodzielnego klienta wywołują ją jawnie.
3. Guard odmawia, gdy inicjalizacji nie było lub dowolny logger manifestu
   został ponownie włączony. Brak/zmiana wersji pakietu zamyka inicjalizację.
   Żaden publiczny POST nie naprawia po cichu uszkodzonej konfiguracji logów.
4. Guard jest sprawdzany przed budową komunikatu i ponownie bezpośrednio przed
   `send`, bez `await` pomiędzy drugim sprawdzeniem a rozpoczęciem wysłania.
   Ochrona obowiązuje przy każdym kolejnym żądaniu, również po poprzednim błędzie.
   `aclose` pozostaje dostępne do zwolnienia zasobów także po odmowie guarda.
5. Test upgrade analizuje źródła zainstalowanych przypiętych pakietów:
   literalne nazwy `logging.getLogger` w HTTPX/HTTPCore odpowiadają manifestowi.
   Nowa nazwa albo konstrukcja, której test nie potrafi rozpoznać, wymaga review;
   nie jest automatycznie akceptowana. Pin i test nie kwalifikują innych wersji.
6. Dedykowany klient nie dodaje extension `trace`. HTTPCore może przekazywać
   dane do tego callbacku niezależnie od loggerów, dlatego samo wyłączenie
   `logging` nie uprawnia do dopuszczenia dowolnej instrumentacji/APM.

Skutkiem jest brak niskopoziomowych logów HTTPX/HTTPCore w całym procesie API,
również dla GET metadata. Polityka trwa do końca procesu; shutdown klienta
nie włącza loggerów z powrotem. Fixture testów odtwarza wyłącznie własne zmiany.
Po przyjęciu ADR późniejsza konfiguracja logging musi respektować tę politykę.
Guard wykrywa zmianę przed operacją; nie stanowi izolacji od kodu, który
celowo modyfikuje loggery lub instrumentację podczas trwającego requestu.

Transport zastępuje raw diagnostics zdarzeniem INFO loggera `torii.identity`:
stałe `event=oidc_transport`, `operation=exchange|revoke`,
`outcome=success|unauthorized|unavailable|cancelled` i skończone `duration_ms`.
Nie emituje code, verifier, Basic, tokenów, URL/query, reason phrase, body,
exception ani `exc_info`. Nie przejmuje polityki audytu tożsamości z B2b.

## Żądanie i granica zaufania

- `RealmEndpoints` pozostaje źródłem zaufanych URL. `exchange` dopuszcza
  dokładnie `backchannel + /protocol/openid-connect/token`, `revoke` dokładnie
  `backchannel + /protocol/openid-connect/revoke`. Porównanie exact string,
  bez normalizacji lub pobierania URL z discovery/DTO odpowiedzi.
- Prywatny POST odrzuca przed I/O DTO o złym typie albo URL, także query,
  fragment, inną ścieżkę/host/port, userinfo i zamianę token/revoke. `url` jest
  dokładnym `str`, DTO dokładnym `OAuthRequest`; nazwa operacji z allowlisty.
- `authorization`: exact str, prefiks `Basic `, całość <=65536 ASCII bytes,
  canonical Base64 bez whitespace/control; zdekodowane ASCII zawiera dokładnie
  jeden separator `:`. Transport nie ocenia poprawności samych credentials.
- `body`: exact bytes, 1..65536, wyłącznie drukowalne ASCII bez spacji/control.
  To granica transportowa, nie ponowny parser semantyki pól OAuth. Enkoder B2a4a
  pozostaje właścicielem nazw pól, escaping, PKCE i stałego redirect URI.
- Wysyłamy `content=request.body`, dokładny Authorization z enkodera,
  `Content-Type: application/x-www-form-urlencoded`, `Accept: application/json`
  oraz `Accept-Encoding: identity`. HTTPX może dodać Host/Content-Length;
  nie dodajemy Cookie, dodatkowego BasicAuth ani credentials w URL/argv.
- Dedykowany `AsyncClient`: `auth=None`, `trust_env=False`, `verify=True`,
  `follow_redirects=False`, cookie jar odrzucający wszystkie domeny. Bez retry
  POST, netrc, proxy środowiska, caller trace/hooks i domyślnych cookies.
  Provider Set-Cookie nie jest przechowywane ani wysyłane w kolejnej operacji.
- Dozwolony HTTP do hosta `identity` pozostaje wyłącznie istniejącym wyjątkiem
  dev B2a3; dla HTTPS certyfikat zawsze jest weryfikowany. Nie dodajemy
  `verify=False`, zmiany trust store lub dowolnego plaintext hosta.

## Odpowiedzi i błędy

Najpierw status i nagłówki, następnie bounded surowy stream, na końcu parser.
Limit wynosi 65536 faktycznie odczytanych bajtów; nie ufamy samemu nagłówkowi.
Nie używamy automatycznej dekompresji, `.text`, `.json` ani `raise_for_status`
jako granicy błędu, która mogłaby zachować URL/body.

| Operacja / status | Dopuszczalne dane i wynik |
|---|---|
| exchange 200/400 | Dokładnie jeden Content-Type `application/json`, opcjonalnie charset UTF-8, bez innych parametrów. Bounded body trafia do parsera B2a4a. |
| exchange 200 poprawny | `TokenReply`, nadal niezaufany. Żadna sesja lub tożsamość nie powstaje. |
| exchange 400 `invalid_grant` | Wyłącznie wynik naszego strict parsera daje `401 unauthorized`; error text nie jest zwracany. |
| exchange pozostałe statusy | `503 identity_unavailable`, bez odczytu body; response nadal zamykane. |
| revoke 200 | Puste lub nie-JSON body jest dozwolone; Content-Type nie jest wymagany. Jeśli obecny, pojedynczy i do 256 ASCII znaków bez control. Po limitach wywołanie walidatora B2a4a. |
| revoke inny status | `503 identity_unavailable`; bez retry i bez obietnicy globalnego logout. |

W obu ścieżkach Content-Encoding: brak albo pojedyncze dokładne `identity`
(case-insensitive). Content-Length: opcjonalny pojedynczy ciąg cyfr ASCII,
wartość <=65536; po odczycie podana długość musi odpowiadać faktycznym bajtom.
Duplikaty, nieprawidłowy typ/encoding/framing lub przekroczony limit dają503.
Oceniana jest reprezentacja nagłówków HTTPX; jak w A3, h11 może scalić identyczne
Content-Length przed tą granicą. Test adaptera nie jest parserem surowego HTTP.
Dla niedopuszczalnego statusu nie trzeba parsować treści ani typu odpowiedzi.

Zwykłe wyjątki providera transportu/HTTPX/cleanup, w tym wstrzyknięty
`DomainError(401, ...)`, są mapowane na bezpieczne503, bez cause/context lub
markerów w formatted traceback. Nie przepuszczamy wyjątku providera jako
decyzji o tożsamości. Zachowujemy401 wyłącznie z własnego enkodera przy złym
code lub z własnego parsera `invalid_grant`. Nie używamy wprost A3 `_load`,
które mapuje wszystkie DomainError na503. Funkcja `raise_identity_error`
zachowuje istniejącą granicę CPython dla ambient caller exception z B2a3/A4a.

## Deadline, cancellation i cleanup

- `deadline` to absolutny monotoniczny deadline pracy: dokładny int/float,
  bez bool, skończony, 0..2^53-1 i późniejszy niż bieżący czas pętli.
  Brak/zły/wyczerpany deadline, closed client i niespełniony guard odmawiają
  przed I/O. Maksymalny work cutoff to `min(deadline, now + 5s)`.
- Cała praca POST (pool/connect/write/status/body/parser) używa wspólnego
  cutoff, bez nowego budżetu na każdym etapie. Pula max4 connections/max2
  keepalive; connect/pool <=2s, read/write <=5s, dodatkowo wspólny cutoff.
- Sprawdzenie czasu także po parserze; przekroczenie nie daje spóźnionego
  sukcesu. Po pracy dozwolone najwyżej dodatkowe1s na cleanup. Przyszła
  orkiestracja rezerwuje tę sekundę przed swoim zewnętrznym deadline.
- Odpowiedź jest zamykana na sukcesie, błędzie nagłówków/parsera, timeout
  i anulowaniu. Ochrona `aclose` obejmuje także automatyczne ścieżki błędu
  HTTPX, np. parsowanie niepoprawnego Location mimo wyłączonych redirectów.
  Można reuse ograniczony hook/stream B2a3; nie zmieniamy kontraktu jego GET.
- Zewnętrzne `asyncio.CancelledError` propaguje po ograniczonym cleanup,
  nie zmienia się w401/503. Błąd zamykania nie zastępuje cancellation.
  Kolejne anulowanie może skrócić cleanup; nie tworzymy nieśledzonych tasks
  ani shield dla całego requestu. Anulowanie/timeout nie uruchamia retry.
- `aclose()` klienta jest idempotentne, oznacza klient zamkniętym przed próbą
  cleanup i ma łączny limit1s. Żaden kolejny request nie otwiera go ponownie.
  Przy zwykłym błędzie cleanup nie zwracamy pozornego sukcesu operacji.

Limit cleanup jest kooperatywny, jak w A3. Nie gwarantuje twardego czasu
zakończenia arbitralnego transportu tłumiącego cancellation; zaufany wstrzyknięty
transport jest częścią granicy testowej, nie nieufnym pluginem użytkownika.

## AC i dowody przed odbiorem

| AC | Testowalny warunek |
|---|---|
| A4b-01 | Publiczna kompozycja używa istniejącego encoder/parser. Raw request ma fixed URL, dokładne form/basic bytes i dozwolone nagłówki. Forged DTO/operation/headers/body odrzucone przed wywołaniem transportu. |
| A4b-02 | Token200/400 MIME/framing/encoding i realny limit streamu; `invalid_grant`401, pozostałe503. Revocation200 działa z empty/nonJSON; inne statusy/oversize odrzucone. Wynik nie tworzy Identity. |
| A4b-03 | Jedno wywołanie POST przy timeout/read/protocol/provider failure, redirect i5xx; żadnego retry. Set-Cookie nie powraca na wire, także w równoległych operacjach. Brak trace extension i caller hooks. |
| A4b-04 | Deadline typy/zakres/przeszłość, pool/connect/write/read/body, kontrola po parserze, hanging close i explicit close. Test realclock z ograniczoną tolerancją pętli potwierdza work cutoff+1s; cancellation pozostaje CancelledError nawet z błędem cleanup. |
| A4b-05 | Import nie zmienia logging. Startup idempotentnie wyłącza dokładnie manifest; root/Torii logger działa nadal. Brak init lub ponownie włączony emitter blokuje następny POST przed I/O. Zła wersja pakietu blokuje startup. Test źródeł zgadza się z manifestem. |
| A4b-06 | Syntetyczne markery w Authorization/body/tokenach, reason phrase, headers i wyjątkach nie trafiają do loggerów (także handlers na emiterach), repr/str lub traceback. Torii emituje wyłącznie skończony schemat operacja/outcome/duration, bez exception repr. |
| A4b-07 | Default client ma verified TLS, trust_env=False i brak proxy/cookies/redirectów/retry; środowiskowe proxy/netrc/CA nie zmieniają konfiguracji. Mock/socket guard zapobiega realnym połączeniom w tych testach; nie jest to dowód handshake TLS lub loginu z IdP. |
| A4b-08 | Lifecycle app uruchamia politykę przed zależnościami; brak nowych tras/Settings/env/migracji i zmian w B1/B2a1/2/3/4a. Lint/types, kontrakty, regresje backendu i niezależny review z raportem niespełnionych bramek SP-01. |

Testy używają syntetycznych credentials i kontrolowanego streamu/transportu.
Nie czytają sekretów instancji, nie uruchamiają rzeczywistego loginu ani nie
eksportują HAR/raw trace. Dotychczasowy scope testów PostgreSQL/frontendu
pozostaje opisany w bramce integratora; brak zmian ich kodu nie oznacza nowego
odbioru DB/UI. Wyniki wykonanych AC komponentu, review i niespełnione bramki:
[raport B2a4b](../../docs/platform/sp-01-b2a4b-evidence.md). Pełne B2/SP-01
pozostają otwarte; raport nie kwalifikuje rzeczywistego loginu.

## Podział pracy i wycofanie

- Właściciel transportu: `security/oidc_exchange.py` i testy transportu.
- Właściciel logging: `security/credential_logging.py`, testy polityki i manifestu.
- Integrator: jedyny właściciel `app.py`, ewentualnego wydzielenia wspólnych
  helperów A3, testu startup i raportu dowodów. Publiczne interfejsy zgodne
  z tą rewizją; bez równoległej edycji istniejącego GET przez obie osoby.
- Reviewer: niezależne wektory negatywne oraz review przed i po kodzie.

Brak zmiany trwałego stanu. Wycofanie nowego klienta i wywołania startup wymaga
restartu procesu; nie włączamy loggerów w trakcie życia innej instancji API.
Nie podłączamy credentials I/O po usunięciu guarda. Bez zmian starych usług,
wolumenów i root `.env`; samo przyjęcie spec nie jest deploy ani ukończeniem
SP-01. Polityka IdP/Uvicorn/gateway/APM zostaje osobną bramką przed B2b.

Źródła profilu: lokalne źródła z `apps/api/.venv` i lock odczytane2026-10-10;
[HTTPX0.28.1 client](https://github.com/encode/httpx/blob/0.28.1/httpx/_client.py),
[HTTPCore1.0.9 trace](https://github.com/encode/httpcore/blob/1.0.9/httpcore/_trace.py),
[HTTPX environment](https://www.python-httpx.org/environment_variables/).
Normatywne encoding/revocation oraz źródła Keycloak pozostają w B2a4a;
źródła nie zastępują testów rzeczywistego dostawcy w B2b.
