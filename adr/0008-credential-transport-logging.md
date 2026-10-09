# ADR-0008 — logowanie przy transporcie credentials OAuth

2026-10-10. Status: **Accepted (delegated)** po niezależnym review
`regulated_examples` przed kodem. Bez audytu człowieka ani wydania enterprise.
Zakres: [SPEC-0001 B2a4b](../specs/0001-project-object-version/increment-b2a4b.md),
SP01-04a. Nie zmienia akceptacji pozostałych fragmentów B2 ani całego SP-01.

## Kontekst

Enkoder B2a4a tworzy secret-bearing DTO z bezpiecznym repr. Przekazanie DTO do
HTTPX nie zachowuje automatycznie tej granicy: HTTPX może emitować URL i reason
phrase, a HTTPCore trace może formatować nagłówki, dane odpowiedzi lub wyjątki.
HTTPX i HTTPCore używają loggerów procesu, nie prywatnego namespace klienta OIDC.
Logger rodzica i jego poziom nie wyłączają wszystkich emiterów potomnych.
Transport POST będzie wysyłał client secret, code/verifier i refresh token;
polityka logowania musi poprzedzać pierwszy taki request.

Odczyt lokalnych przypiętych źródeł oraz
[HTTPX0.28.1](https://github.com/encode/httpx/blob/0.28.1/httpx/_client.py) i
[HTTPCore1.0.9](https://github.com/encode/httpcore/blob/1.0.9/httpcore/_trace.py)
potwierdza manifest `httpx`, `httpcore.connection`, `httpcore.http11`,
`httpcore.http2`, `httpcore.proxy`, `httpcore.socks`. HTTPCore posiada także
niezależne extension `trace`; dopuszczenie własnego callbacku omijałoby ochronę
opartą wyłącznie na loggerach.

## Decyzja

Przy starcie procesu Torii API jawnie wyłączamy dokładnie emitujące loggery
przypiętych HTTPX0.28.1/HTTPCore1.0.9 przez `logger.disabled=True`.
Inicjalizacja odbywa się w lifespan, bez efektu przy imporcie i bez wyłączania
pozostałych logów aplikacji. Polityka dotyczy całego procesu i pozostaje do
jego zakończenia. Nie odtwarzamy starych ustawień na shutdown pojedynczego klienta.

Przed credentials I/O guard sprawdza inicjalizację i stan manifestu. Błąd
odmawia wykonania z bezpiecznym503, zamiast automatycznie przywracać loggerów
lub ignorować konfigurację. Startup odmawia dla innej/brakującej wersji pakietu;
test źródeł stanowi bramkę aktualizacji manifestu. Sama zgodność numeru wersji
nie zastępuje przypiętych artefaktów instalacji i kontroli zależności.

Dedykowany klient buduje własne żądania. Nie przyjmuje zewnętrznego HTTPX client,
hooks ani callbacków trace. Traci raw diagnostics bibliotek, ale emituje własne
zdarzenie `torii.identity` ze stałą operacją/outcome i czasem; bez credentials,
URL, body, wyjątków i pól dostarczonych przez IdP. Dokładne API i AC są w spec.

Guard sprawdza stan przed operacją. Nie obiecuje ochrony przed zaufanym kodem
procesu celowo zmieniającym logger/transport w trakcie requestu, profilerem,
debuggerem lub APM odczytującym pamięć. API nie wykonuje kodu użytkowników;
wprowadzenie nowej instrumentacji wymaga przeglądu tej granicy.

## Alternatywy

| Alternatywa | Powód odrzucenia w tym przyroście |
|---|---|
| Pozostawić domyślne INFO/WARNING | Konfiguracja operatora może włączyć emiter; nawet reason phrase i wyjątek mogą zawierać niezaufaną treść. |
| Filtr regex usuwający hasła/tokeny | Nie znamy wszystkich reprezentacji, pól i przyszłych formatterów; filtr nie stanowi kompletnej granicy. |
| Wyłączyć tylko logger `httpcore` lub podnieść jego poziom | Potomkowie emitują własne rekordy; trzeba objąć rzeczywiste emitery. |
| Globalne `logging.disable` | Usuwa również potrzebne logi domeny i operatora; zakres jest szerszy niż wymagany. |
| Przełączać logger na czas pojedynczego requestu | Globalny stan i współbieżność tworzą wyścigi; restore może włączyć logowanie dla innego requestu. |
| ContextVar i filtry per request | Wnosi dodatkowy kontrakt propagacji przez biblioteki/handlers/tasks; niepotrzebny przy obecnej jednej aplikacji i wydzielonych workerach. |
| Osobny proces proxy OAuth | Dodaje kolejną granicę IPC/deploy i przechowywanie secrets; nie jest konieczne dla obecnego modularnego API. |

## Konsekwencje i granice

- Metadata GET i każdy inny użytkownik HTTPX w tym procesie również tracą
  niskopoziomowe logi. To świadomy koszt; pozostałe logowanie Torii działa.
- Aktualizacja HTTPX/HTTPCore wymaga przeglądu wersji, źródeł emiterów, trace
  i testów markerów. Nie rozszerzamy manifestu automatycznie na nowe biblioteki.
- Testy idempotencji/startup/zmiany guarda muszą odtwarzać własne ustawienia
  loggerów, aby nie ukrywać wyników pozostałych testów procesu.
- Polityka nie chroni logów serwera IdP, reverse proxy, Uvicorn, operatora lub
  zewnętrznego APM. Ich przegląd pozostaje bramką przed pełnym logowaniem B2b;
  B2a4b nie uruchamia realnych code/replay testów Keycloak.
- Brak zmian modelu danych, env, migracji, dependency locka i publicznych tras.
  Wycofanie wymaga restartu oraz usunięcia/odłączenia zależnego credentials I/O,
  nie włączania emiterów w działającym procesie z aktywnymi operacjami.

Przyjęcie tej decyzji pozwoli implementować wyłącznie wskazany lokalny
komponent. Nie oznacza pełnego audytu bezpieczeństwa, loginu, enterprise release
ani przyjęcia przyszłej orkiestracji sesji.
