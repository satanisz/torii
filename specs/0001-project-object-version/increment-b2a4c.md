# SPEC-0001 B2a4c — wewnętrzna orkiestracja logowania i wylogowania

Rewizja 0.1, 2026-10-10. Status: **Accepted (delegated)**.
Niezależny review przed kodem: `regulated_examples`, bez blokerów; autor
`platform_state`. Zależne B2a4b odebrane lokalnie w commicie `d63bee6`.
Właściciel: integrator Torii. Przyrost **SP01-04b**, część B2-D06,
B2-AC01–04 oraz SPEC-0001 AC-09/10/12/14. Wymagany niezależny review przed kodem.
Decyzja synchronizacji DB: [ADR-0009 Proposed](../../adr/0009-oidc-db-cancellation.md).

## Problem i zakres

[B2a1](increment-b2a1.md) przechowuje flow i sesje,
[B2a2](increment-b2a2.md) weryfikuje JWT,
[B2a3](increment-b2a3.md) dostarcza klucze,
[B2a4a](increment-b2a4a.md) definiuje komunikaty, a
[B2a4b](increment-b2a4b.md) wykonuje ograniczone POST i chroni logi.
Brakuje jednej kolejności, która zużyje flow przed siecią, zweryfikuje oba
tokeny i dopiero wtedy zapisze sesję. Ten przyrost dostarcza tę kompozycję
oraz lokalne wylogowanie z ograniczoną próbą revocation.

Implementacja może rozpocząć się dopiero po akceptacji tej rewizji i odbiorze
zależnego B2a4b. Jego status Accepted sam nie zastępuje końcowego review kodu.
Nie powstają nowe HTTP routes, cookies, middleware, Settings/env, migracje,
granty, bootstrap, deploy ani integracja UI. Serwis nie zostaje jeszcze
podłączony do publicznego requestu. Nie dodajemy logowania SDK/Bearer,
odświeżania tokenów ani okresowego cleanup. Istniejący IdentityStore i profile
JWT/sieci pozostają źródłami reguł; nie tworzymy drugiego magazynu ani parsera.

Wartość przyrostu: następna fasada HTTP może użyć przetestowanego przebiegu,
zamiast samodzielnie składać transakcje, tokeny i obsługę anulowania.
To nadal wewnętrzny adapter, nie działający login przeglądarki ani odbiór B2b.

## Minimalne API i własność zasobów

Nowy `application/oidc_login.py`, bez frameworkowego request/response:

```python
OidcLoginService(
    engine: Engine,
    settings: Settings,
    *,
    metadata_transport: httpx.AsyncBaseTransport | None = None,
    credential_transport: httpx.AsyncBaseTransport | None = None,
)
async start(*, deadline: float) -> LoginStart
async callback(
    state: str,
    browser: str,
    *,
    code: str | None = None,
    error: str | None = None,
    previous_session: str | None = None,
    deadline: float,
) -> NewSession
async logout(session_id: str, *, deadline: float) -> None
async aclose() -> None
```

`LoginStart` jest frozen/slotted z `authorization_url: str` i `browser: str`,
oba `repr=False`. `NewSession` jest istniejącym wynikiem IdentityStore;
nie kopiujemy go do kolejnego typu. Nie zwracamy Flow, verifier, raw JWT,
refresh, raw claims ani wyniku niezakończonej transakcji. Repr/str serwisu
i nowych wartości nie ujawnia konfiguracji, URL lub credential.

Serwis składa konkretne istniejące klasy: RealmEndpoints, SecretCodec,
IdentityStore, TokenVerifier, OidcMetadataTransport, OidcKeyCache i
OidcCredentialTransport. Wszystkie otrzymują spójne wartości z tego samego
Settings. Nie przyjmujemy niezależnych issuer/client z requestu ani dowolnego
gotowego HTTPX client. Dwa opcjonalne transporty to zaufane seams testowe
B2a3/B2a4b; nie konfiguracja produktu. Nie wprowadzamy hierarchii repozytoriów,
pluginów ani dodatkowych Protocol tylko na potrzeby mocków.

Konstruktor nie wykonuje DB/network I/O ani konfiguracji loggerów. Engine
pozostaje własnością callera; serwis go nie usuwa ani nie wywołuje dispose.
Najpierw waliduje czyste ustawienia/komponenty, potem tworzy klientów. Jeśli
drugi konstruktor odmawia, częściowy serwis nie zostaje opublikowany. Domyślne
klienty nie wykonały wówczas żadnego requestu ani nie otworzyły połączenia;
nie tworzymy detached task tylko po to, aby wywołać async close z konstruktora.
Testy wstrzykują dwa niezależne, nieuruchomione transporty i sprzątają je same
przy nieudanej konstrukcji; nie przekazują współdzielonej działającej puli.
Serwis jest jedną instancją per issuer/proces/event loop, współdzieli cache
i klientów. Użycie w innym loopie lub po rozpoczęciu close daje safe503.
Jawny `configure_credential_logging()` należy do istniejącego startup B2a4b;
testy serwisu wywołują go oraz odtwarzają własny stan loggerów.

`logout` jest metodą wewnętrzną po autoryzacji przyszłej fasady, a nie dowodem
CSRF/Origin. Nie przyjmuje `authorized=True` ani arbitralnego actor. Bezpieczne
przyłączenie jej do requestu wymaga B2b. Authenticate-session, Bearer auth,
uprawnienia projektu i HTTP logout policy B2-D05 pozostają poza tym zakresem.

## Start logowania

1. Sprawdź lifecycle, deadline i guard logging przed jakimkolwiek zapisem.
2. Wykonaj `IdentityStore.create_flow()` w synchronizowanym workerze DB.
   Wynik jest dostępny dopiero po commit; brak IdP I/O na tej ścieżce.
3. Zbuduj publiczny URL dokładnie `issuer + /protocol/openid-connect/auth`.
   Parametry występują raz, jako kontrolowana lista form/urlencode:
   `client_id`, `redirect_uri`, `response_type=code`, `scope=openid profile`,
   `state`, `nonce`, `code_challenge`, `code_challenge_method=S256`.
   Redirect to public origin skonfigurowanego issuer + `/auth/callback`,
   zgodny z B2a4a. Challenge to base64url bez padding SHA256 ASCII verifier.
   Bez secret, verifier, browser, `offline_access`, return_to albo input URL.
4. Po ostatniej kontroli czasu zwróć LoginStart. Future HTTP zdecyduje o 303
   i cookie; ten serwis ich nie tworzy. Start nie odwołuje istniejącej sesji.

Gdy commit flow zakończy się po anulowaniu lub deadline, nie wydajemy URL ani
browser credential. Niewykorzystany flow wygasa według istniejącego TTL5min;
nie dodajemy nowej metody DELETE ani background job tylko dla tej sytuacji.

## Callback — jedna próba i jedna sesja

1. Sprawdź lifecycle/deadline/logging. Wymagane jest dokładnie jedno z code/error.
   Code ma profil B2a4a: exact str1..4096 ASCII0x21..7e; error to exact
   str1..256 ASCII0x21..7e. Niepoprawny kształt daje401 przed consume/I/O.
   State/browser sprawdza canonical token_hash B2a1. Query duplicates, iss,
   session_state i dekodowanie HTTP są odpowiedzialnością B2b; tu są już
   pojedyncze wartości. Żadnego error_description, URL lub tekstu providera
   w rezultacie/błędzie/logu.
2. W workerze wywołaj `consume_flow(state, browser)` i poczekaj na jego commit.
   Dopiero pomyślny zwrot ConsumedFlow dopuszcza HTTP. Wrong browser nie zużywa
   rekordu; expired/missing/used pozostaje401. Równoległe callbacki nie mają
   dwóch exchange. Nie ma otwartej transakcji ani connection podczas HTTP.
3. Dla provider error po poprawnym consume zwróć401; bez exchange/cache/sesji.
   Powrót do logowania wymaga nowego flow. Nie różnicujemy wartości error.
4. Dla code wywołaj raz `credentials.exchange(code, consumed.verifier,
   deadline=work_deadline)`. Nie odtwarzaj flow ani nie powtarzaj POST po
   invalid_grant, timeout, cancel, parse failure albo awarii zapisu.
5. Pobierz dwa niezaufane hints przez `token_key_id(id_token)` i
   `token_key_id(access_token)`, następnie jeden snapshot przez
   `cache.keys_for((id_kid, access_kid), deadline=work_deadline)`.
   Dopuszczalne są dwa różne kid; nie wybieramy kluczy z JWT ani nie robimy
   oddzielnego refresh na każdy token. Hint nigdy nie staje się tożsamością.
6. Wywołaj dokładnie istniejące `TokenVerifier.verify_login(id_token,
   access_token, consumed.nonce_hash, keys)`. Oba podpisy, issuer, rodzaj,
   audience/azp, daty, zgodność subject i nonce są obowiązkowe. Obecne at_hash
   musi pasować do otrzymanego access token; jego brak nadal jest dozwolony
   przez przyjęty B2a2. Nie zaostrzamy tego profilu przy okazji kompozycji.
7. Dopiero po walidacji i kontroli czasu uruchom w workerze
   `create_session(identity, previous_session, refresh_token)`.
   Nie wywołuj wcześniej provision_identity. Principal/upsert, lokalna sesja
   i rotacja wskazanej starej sesji pozostają jedną transakcją B2a1. Nie ma
   grantów z claims, reaktywacji principal ani kasowania innych urządzeń.
8. Zwróć NewSession dopiero po potwierdzonym commit i końcowej kontroli czasu.
   Żadna ścieżka odmowy nie wydaje cookie/session credential lub raw tokenów.

Refresh z poprawnie sparsowanego TokenReply jest nadal opaque i niezaufany.
Jeśli callback po otrzymaniu tego wyniku nie zakończy się wydaniem NewSession,
wolno raz próbować revoke tego refresh do stałego endpointu, wyłącznie w
pozostałym work budget i po zakończeniu DB. Brak refresh, wyczerpany budżet
lub cancellation oznacza pominięcie HTTP. Błąd revocation nie przesłania
pierwotnej odmowy. Nie wydobywamy refresh z malformed/odrzuconego response.

## Logout i lokalny skutek

1. Sprawdź lifecycle/deadline, następnie uruchom `revoke_session(session_id)`
   w workerze. Ta metoda zakłada uprzednią autoryzację HTTP; sama nie wykonuje
   authenticate_session/touch ani kontroli Origin/CSRF. Nie obiecuje aktywności
   sesji, której nie sprawdziła; B2b ma własny kontrakt wygasłej sesji.
2. DELETE i commit muszą poprzedzać jakikolwiek remote revoke. Missing/invalid
   credential daje401. Błąd DB daje503, nie pozorny sukces i nie próbę remote
   revoke na podstawie niezakończonej transakcji.
3. Przy `RevokedSession(refresh_token=None, secret_error=True)` lokalny logout
   nadal jest skuteczny. Operational decrypt failure pozostaje błędem B2a1,
   nie jest utożsamiany z uszkodzonym ciphertext.
4. Jeśli refresh istnieje i pozostał work budget, spróbuj raz remote revoke.
   Jego zwykła awaria, zły response, niespełniony logging guard lub timeout
   nie cofa lokalnego DELETE i nie zmienia poprawnego lokalnego wyniku na503.
   Guard nie może zablokować lokalnego revoke tylko dlatego, że IdP I/O jest
   obecnie niedozwolone. Brak background retry i gwarancji globalnego SSO logout.
5. Zewnętrzne CancelledError pozostaje cancellation również po udanym DELETE;
   lokalny skutek jest wtedy zachowany, lecz caller nie otrzymuje sukcesu.
   Jeśli limit czasu minie przed potwierdzeniem lokalnego DELETE, zwracamy503
   po join i opisujemy rzeczywisty możliwy skutek niżej. Gdy lokalny DELETE
   potwierdzono w work budget, niepowodzenie późniejszej best-effort sieci
   nie unieważnia tego sukcesu, również gdy wykorzysta całą rezerwę cleanup.

## Jeden deadline i synchroniczna baza poza event loopem

Każda metoda start/callback/logout otrzymuje jeden serwerowy absolutny
monotoniczny deadline: exact int/float, bez bool, finite, zakres0..2^53−1.
Na wejściu `final_deadline = min(deadline, loop.time() + 15.0)`;
`work_deadline = final_deadline - 1.0`. Brak dodatniego work budget odmawia
przed skutkiem. Caller nie przekazuje deadline z niezaufanego requestu.

Ten sam work_deadline obowiązuje dla queue/DB, exchange, cache/GET, weryfikacji
i zapisu. Nie przyznajemy kolejnych15s każdej zależności. A3/A4b zachowują
dodatkowe max5s pracy pojedynczego I/O oraz najwyżej1s cooperative cleanup;
ostatnia sekunda została zarezerwowana właśnie dla tego cleanup. Nie zaczynamy
kolejnego etapu, gdy work_deadline już minął, także po synchronicznym parserze
lub podpisie. Nie shield całego callback. CPU weryfikatora jest bounded przez
już przyjęte rozmiary/JWK; sprawdzenie czasu po nim nie jest preemptive timeout.

**Wrapper async nie jest anulowaniem transakcji PostgreSQL.** Obecny store
i granica transaction mają sync pool/connect/lock/statement timeout, bez
zewnętrznego deadline transakcji. Nie zmieniamy ich API ani wartości w tym
przyroście. Pojedynczy SQL timeout nie jest łącznym limitem całej transakcji;
join może przekroczyć15s. Nie deklarujemy twardego czasu odpowiedzi DB.

To **jawna bramka blokująca podłączenie B2b**. Obecny EnvelopeMiddleware
otacza request przez `asyncio.timeout(15)`, bez przekazania absolutnego deadline
do aplikacji; sam timeout nie zatrzyma sync workera. B2b musi uzgodnić deadline
całego requestu, zachowanie odpowiedzi po cancellation i drain przed podłączeniem
serwisu. Nie wolno prezentować obecnego middleware jako twardej gwarancji15s
ani zaczynać nowego15s budżetu po parsowaniu HTTP. A4c nie zmienia middleware.

Kontrakt prywatnego helpera DB w tym samym module:

- Wyłącznie całe wywołanie istniejącej metody store działa w workerze; engine
  jest współdzielony, Connection/transakcja nigdy nie przechodzi między wątkami.
  Nie blokujemy event loop wywołaniem store ani synchronicznym future.result().
- Jedna instancja dopuszcza najwyżej4 uruchomione/zgłoszone wywołania DB.
  Oczekiwanie na permit ma aktywny timeout do work_deadline. Nie tworzymy
  nieograniczonej kolejki executor futures ani nowego executora per request.
- Worker ma śledzony task/future i sygnał cancellation; przed rozpoczęciem
  samej metody store sprawdza ten sygnał i pozostały budżet. Odmowa przed
  startem nie otwiera transakcji. Użyty zegar jest serwerowy i odpowiada
  monotonicznemu budżetowi; nie używa czasu JWT/DB do deadline asyncio.
- Po timeout/cancel już uruchomionego store zapisujemy odmowę i **czekamy na
  zakończenie workera** bez blokowania loopa. Krótko chroniony jest join,
  nie logowanie/sieć; kolejne cancellation nie porzuca workera ani permit.
  Oryginalny CancelledError ma pierwszeństwo przed błędem workera/cleanup.
  Timeout pozostaje safe503. Nie uruchamiamy następnego zwykłego etapu.
- Metoda nie wraca ani nie wypuszcza permit przed join. Nie zakładamy rollback
  z faktu anulowania coroutine. Wątek może zakończyć commit po utracie odpowiedzi.
  Nie ma detached tasks, background revoke ani automatycznego retry DB.

### Późny commit i kompensacja

- Po późnym consume materiał jest odrzucony; flow pozostaje zużyty, zero
  exchange. Po późnym start niewydany flow wygasa naturalnie.
- Jeśli create_session zwróci **znany** NewSession po timeout/cancel,
  wykonujemy najwyżej jedną synchronizowaną lokalną próbę
  `revoke_session(new_session.session_id)` przed zakończeniem metody.
  To jawny wyjątek pozwalający na kompensacyjne DB po work_deadline; nie ma
  nowego budżetu sieci. Join kompensacji ma tę samą uczciwą granicę sync DB.
  Missing session w kompensacji oznacza już osiągnięty lokalny skutek.
- Kompensacja dotyczy wyłącznie znanej nowej sesji. Nie odtwarza starej sesji
  usuniętej atomowo przy rotacji, nie usuwa principal/grantów i nie szuka po sub.
  Jej awaria nie wydaje credential ani nie zmienia cancellation w sukces.
- Jeśli po awarii COMMIT wynik jest nieznany i NewSession nie zostało zwrócone,
  nie znamy nowego credential i nie zgadujemy rekordu do usunięcia. Możliwy
  pozostaje niewydany rekord sesji oraz dokonana rotacja; obowiązują istniejące
  idle30min/absolute8h. Nie nazywamy tego pewnym rollback ani pełną kompensacją.
  Retry tego callback nie odtworzy flow ani nie wykona drugiego exchange.

## Lifecycle i bezpieczna granica błędów

`aclose()` najpierw trwale blokuje nowe publiczne operacje, następnie czeka
na już przyjęte operacje i wszystkie ich workery/kompensacje, a potem zamyka
obu klientów. Nie zamyka HTTP client pod trwającym requestem ani engine pod
wątkiem DB. Close jest idempotentne; równoległe close czekają na ten sam
proces zamykania. Każdy istniejący client ma swój cooperative limit1s
(sekwencyjnie do2s po drain); drain DB nie ma deklaracji hard timeout.
Błąd jednego close nie pomija drugiego; zewnętrzne cancellation propaguje
po synchronizacji możliwego cleanup. Nie włączamy loggerów przy shutdown.
Przyszły lifespan B2b odpowiada za wywołanie close przed engine.dispose.

Zaufane metody B2a1/2/3/4a/4b zachowują własną klasyfikację401/503;
orkiestracja emituje świeże `DomainError(401, "unauthorized")` albo
`DomainError(503, "identity_unavailable")`, bez pointers, treści wyjątku,
provider cause/context. DB `dependency_unavailable` jest na tej granicy503.
Nieznane wyjątki zwykłe są503, BaseException nie udaje zwykłej odmowy.
Obowiązuje istniejąca granica ambient caller exception CPython opisana w A3.

Nie logujemy state/browser/code/verifier/nonce/session/CSRF/refresh/JWT,
URL/query, display_name/sub, ciphertext lub wyjątków. Dopuszczalne nowe
zdarzenie `torii.identity` ma wyłącznie stałe `event=oidc_login`,
`operation=start|callback|logout|close`,
`outcome=success|unauthorized|unavailable|cancelled`,
`cleanup=none|remote_failed|local_failed|secret_corrupt|commit_unknown`
i skończone nieujemne `duration_ms`. Przypadki jednoczesne wybierają
`commit_unknown > local_failed > secret_corrupt > remote_failed > none`.
Bez exc_info i identyfikatorów z requestu. To diagnostyka komponentu,
nie trwały security audit ani metryki/limiter B2b.

## AC i plan testów

Poniższe AC stanowią kontrakt odbioru. Wykonane wyniki i granice opisuje
[raport A4c](../../docs/platform/sp-01-b2a4c-evidence.md).
Mock store nie zalicza kolejności commit, locków, rotacji ani skutku w DB.

| ID | Warunek i wymagany dowód |
|---|---|
| A4c-01 | Start tworzy flow raz, commit przed wynikiem, poprawny S256 i dokładny public auth URL/query. Brak verifier/browser/secret w URL; brak sieci i zmian istniejącej sesji. Bezpieczny repr wyników. |
| A4c-02 | Real PG + kontrolowany POST: exchange widzi już brak flow przez niezależne połączenie; równoległe callbacki dają jeden exchange. Wrong browser, expired, used oraz błąd commit consume nie wykonują POST. Błąd sieci nie przywraca flow. |
| A4c-03 | Syntetyczne rzeczywiście podpisane JWT przez prawdziwy cache/verifier: oba kid, issuer/audience/typ/nonce/sub oraz obecne at_hash. Uszkodzony dowolny podpis/claim nie tworzy principal ani sesji; brak at_hash zachowuje profil A2. Claims grants ignorowane. |
| A4c-04 | Real PG: NewSession dopiero po commit, brak organizacji/inactive odmawia; atomowa rotacja tylko wskazanej sesji i brak grantów. Injected session-commit failure nie daje wyniku i próbuje co najwyżej jednego refresh revoke w pozostałym budżecie. |
| A4c-05 | Provider error zużywa poprawny flow bez exchange; malformed code/error odmowa przed consume. Malformed TokenReply nie dostarcza tokena do kompensacji. Błąd verify/cache po otrzymaniu refresh może próbować tylko fixed-endpoint revoke. |
| A4c-06 | Real PG: lokalny logout commit poprzedza HTTP i blokuje dalsze auth; awaria/timeout/guard remote oraz corrupt refresh nie cofają DELETE. Błąd local DB nie daje sukcesu ani remote revoke; zachowana klasyfikacja operational decrypt failure. |
| A4c-07 | Jeden work_deadline w zapisanych wywołaniach wszystkich zależności, kolejka/lock cache ograniczone tym samym terminem, czas kontrolowany po verifier/store. Realclock test cooperative HTTP mieści się w final_deadline z tolerancją pętli; osobno pokazany możliwy dłuższy DB join. |
| A4c-08 | Event loop pozostaje responsywny podczas kontrolowanego sync store; max4 futures. Cancel przed startem nie zaczyna DB; cancel/timeout/repeated cancel podczas DB czeka na join, nie wydaje credential i nie pozostawia taska/permit. Brak sieci podczas transakcji. |
| A4c-09 | Real PG + bariery: późny consume daje zero exchange; znany późny session commit uruchamia lokalną kompensację bez cofnięcia rotacji. Błąd kompensacji i commit-unknown są raportowane bez sukcesu/credential; flow replay nie powtarza exchange. Stan DB sprawdzony po join. |
| A4c-10 | Close blokuje nową pracę, drenuje trwającą DB/kompensację przed client close, zamyka obu klientów także po błędzie jednego. Idempotencja, równoległy close, cancellation i odmowa cross-loop. Engine pozostaje własnością callera. |
| A4c-11 | Markery we wszystkich sekretach, raw wyjątkach i nazwach nie trafiają do repr/str/formatted traceback/log handlers. Telemetria wyłącznie zgodna ze schematem; lokalny logout działa przy uszkodzonym logging guard. |
| A4c-12 | Ruff/strict mypy/kontrakty i regresje B1/A1–A4b, niezależny review. Żadnych nowych tras/config/migracji/deploy; raport podaje real PG PASS/SKIP osobno od unit i zachowuje otwarte bramki B2b/SP-01. |

Pure/async testy korzystają z kontrolowanych transportów i barier/events,
nie z przypadkowych sleep jako jedynego dowodu kolejności. Zegar JWT jest
serwerowym seam; deadline używa zegara monotonicznego. Klucze i podpisane
tokeny są syntetyczne, ephemeral, bez utrwalania private PEM/sekretów.

Testy sklejenia z DB używają istniejącego
`deploy/platform/test-projects.ps1` i `tests/integration/conftest.py`:
nowa baza na test, zweryfikowany lokalny Docker/context/container run ID,
osobne role migrator/runtime, żadnych ambient DSN lub działającego stosu.
Testowy transport może odczytać stan przez inne połączenie i zwolnić bariery;
nie utrzymuje transakcji callback. Commit-unknown wymaga jawnej fault injection
po rzeczywistym zatwierdzeniu, a nie nazwania zwykłego rollback tym scenariuszem.
Ten dokument nie uruchamia harnessu ani nie modyfikuje jego konfiguracji.

## Decyzje przekazane do niezależnego review

1. Kompozycja engine + jeden Settings i dwa istniejące seams HTTP zamiast
   zestawu wymienialnych repozytoriów. Nowy kod nie zmienia API IdentityStore.
2. Start bez discovery; fixed public auth endpoint z RealmEndpoints, sieć
   metadata dopiero przy callback. Brak nowej reguły required at_hash.
3. Uczciwa granica czasu: wspólny15s budżet z1s cleanup sieci, synchronizowany
   sync DB bez obietnicy preemption. Opisane commit-unknown, znana kompensacja
   i nieodwracalność już dokonanej rotacji. Integrator wskazał tę minimalną
   kompozycję jako preferowaną2026-10-10; nie jest to niezależna akceptacja.
4. Callback error zużywa flow; malformed shape nie zużywa. Refresh revoke
   po nieudanym callback tylko z poprawnego TokenReply i w pozostałym budżecie.
5. Local logout przed guardem sieci; brak remote revoke nie cofa skutku.
   Autoryzacja/CSRF/Origin/expired-cookie policy nadal obowiązkowe przed B2b.

Uwagi odbioru spec: istniejący `transaction()` nie rozróżnia awarii SQL od
COMMIT. Nieznany wynik zapisu klasyfikujemy konserwatywnie; nie deklarujemy
rozpoznania fazy błędu. Test utraty potwierdzenia po rzeczywistym COMMIT jest
wymagany niezależnie od testu zwykłego rollback.

Jeśli dalszy review wykaże, że bezpieczeństwo wymaga zmiany transakcji store lub
modelu, aktualizujemy tę specyfikację przed kodem. Nie maskujemy tej zmiany
prywatnym hookiem SQL ani deklaracją, że asyncio timeout przerwał COMMIT.

## Wycofanie i otwarte bramki

Wycofanie niepodłączonego serwisu nie zmienia schematu, danych projektów,
uprawnień, kluczy ani uruchomionych usług. Nie usuwa istniejących sesji masowo.
Testy sprzątają wyłącznie własne zasoby zgodnie z guardami harnessu.

Nadal niewykonane: publiczne cookie/CSRF/Origin, parsowanie callback HTTP,
Bearer/session auth i protected routes, bootstrap grantów, real Code+PKCE
Keycloak i przeglądarka, logowanie IdP/gateway/APM, limiter, UI, restart/restore,
pełna obserwowalność i odbiór SP-01. Poprawny JWT z testowego RSA + real PG
nie dowodzi zgodności rzeczywistego dostawcy ani gotowości produkcyjnej.
