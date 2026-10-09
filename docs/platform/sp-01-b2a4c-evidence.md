# SP-01 B2a4c — kompozycja OIDC i trwałych sesji

2026-10-10. Baseline `d63bee6`; [SPEC A4c](../../specs/0001-project-object-version/increment-b2a4c.md)
rewizja0.1 i [ADR-0009](../../adr/0009-oidc-db-cancellation.md).
Spec/ADR przyjęto w granicach mandatu po niezależnym review `regulated_examples`
przed kodem. Autor spec i implementacji: `platform_state`; niezależne testy
unit/async: `platform_runtime`; testy real PostgreSQL i integracja: root.

## Co zostało połączone

`application/oidc_login.py` składa istniejące IdentityStore, cache/JWKS,
TokenVerifier oraz transport OAuth. Udostępnia wewnętrzne start, callback,
logout i close. Nie został podłączony do tras API ani interfejsu.

Start zapisuje browser-bound flow i zwraca fixed authorization URL z S256.
Callback zużywa flow i potwierdza commit przed pierwszym POST. Dopiero po
sprawdzeniu obu podpisów, issuer/audience/typów, nonce/sub i obecnego at_hash
może utworzyć lokalną sesję. Nie przyznaje grantów na podstawie claims.
Logout potwierdza lokalny DELETE przed ewentualnym remote revoke.

Sync DB działa poza event loop, z najwyżej4 zgłoszonymi workerami per serwis.
Anulowanie nie porzuca workera i nie udaje rollback; join poprzedza powrót
metody i zamknięcie klientów. Znana późna sesja ma jedną lokalną próbę usunięcia.
Nieznany wynik COMMIT jest jawnie raportowany, bez zwrócenia credential.
Wspólny work budget zachowuje1s rezerwy sieci; sync DB join może trwać dłużej
niż15s. To nadal bramka integracji middleware w B2b, nie obietnica hard timeout.

## Macierz dowodów

| AC | Dowód |
|---|---|
| A4c-01 | Start/S256/query bez verifier i secret; rzeczywisty flow w PostgreSQL przed wynikiem; brak sieci na start. |
| A4c-02 | Handler kontrolowanego IdP odczytuje już zużyty flow przez niezależne połączenie. Dwa callbacki dają jeden exchange. Wrong browser/expired/missing i deferred commit fault odmawiają przed HTTP. |
| A4c-03 | Dwa rzeczywiste klucze RSA, podpisy obu tokenów, jeden snapshot. PG odmawia provisioning po błędnych podpisach, nonce, sub lub at_hash; brak grantów z roles. |
| A4c-04 | Sesja po commit; atomowa rotacja zachowuje inne urządzenie. Deferred trigger blokujący commit przywraca poprzednią sesję. Inactive i brak organizacji odmawiają. |
| A4c-05 | Provider error zużywa flow bez sieci; awaria exchange nie przywraca flow ani nie ponawia POST. Z dostępnego poprawnego TokenReply po odmowie najwyżej jedna próba revoke. |
| A4c-06 | Real PG logout commit widoczny przed revoke; remote error, uszkodzony guard i corrupt refresh nie cofają lokalnego DELETE. Local commit fault zachowuje sesję i nie wykonuje HTTP. |
| A4c-07 | Testy wspólnego cutoff i kontroli czasu po zależnościach; osobno granica dłuższego sync DB join. |
| A4c-08 | Bariery real PG po commit consume/session i repeated cancellation: coroutine czeka na worker, nie wydaje credential. Testy unit sprawdzają loop, limit4 i kolejkę. |
| A4c-09 | Real PG: późna znana sesja usuwana, stara rotacja nie jest cofana. Błąd kompensacji zachowuje cancellation. Fault po rzeczywistym commit pozostawia niewydany rekord i diagnostykę commit_unknown, nie fikcyjny rollback. |
| A4c-10 | Testy close/drain, dwóch klientów, błędów/cancellation, idempotencji i odmowy cross-loop; engine jest własnością callera. |
| A4c-11 | Syntetyczne markery i schema telemetrii, bez raw tokens/wyjątków. 503 ze store jest konserwatywnie commit_unknown, również gdy fazy SQL/COMMIT nie da się rozpoznać. |
| A4c-12 | Wyniki końcowej regresji i review poniżej; nadal bez nowych tras/config/migracji/deploy. |

## Wykonane kontrole

Oba zestawy nowych testów zaczęły od RED collection brakującego modułu.
Pierwszy przebieg rzeczywistej bazy root:

```powershell
./deploy/platform/test-projects.ps1 -TestArgs @('tests/integration/test_oidc_login_integration.py', '-q')
```

**26 PASS /43.55s**, run `ef04dbd3e01e40b1bdb51a317b4d42ab`.
Harness: przypięty PostgreSQL17, nowa migrowana baza per test, oddzielne role
migrator/runtime, tmpfs, lokalny zweryfikowany Docker/context i losowy port
loopback. Kontener/sieć usunięte po sprawdzeniu własności, dane testów odrzucone.
Nie korzystano z działającej bazy platformy lub legacy. Syntetyczne klucze RSA
i tokeny pozostają w pamięci; brak danych banku i rzeczywistego IdP.

Regresja istniejących B1/B2a1, bez ponownego odtwarzania tych komponentów:

```powershell
./deploy/platform/test-projects.ps1 -TestArgs @('tests/integration/test_projects.py', 'tests/integration/test_identity_store.py', '-q')
```

**53 PASS /88.36s**, run `d78827c09666449aa0a3148fd22cda2c`.
Również osobna baza per test, runtime role i potwierdzony cleanup własnego
kontenera/sieci. Łącznie wykonano79 przypadków real PG w dwóch zakresach;
testy bez bazy nie są doliczane do tej liczby. Dwa znane ostrzeżenia zależności
Starlette (HTTPX TestClient/AnyIO BlockingPortal) pozostały jawne.

Review wykrył P2: uruchomienie pomocniczego revoke wewnątrz handlera surowego
wyjątku pozwalało cancellation odziedziczyć ten wyjątek w `__context__`.
Formatted traceback zawierał syntetyczny marker. Regresja najpierw była RED;
poprawka zachowuje tylko bezpieczny status i wychodzi z handlera przed kolejnym
await. Po zmianie test jest GREEN; cancellation nadal propaguje.
Po zmianie callback powtórzono26 nowych testów PG: **26 PASS /42.46s**, run
`1ae15b481d6a4a90b0c9633c3b2d1a34`, cleanup ponownie potwierdzony.

Końcowa bramka root z `apps/api` (Python3.12.12, Windows):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m 'not integration' --cov
.\.venv\Scripts\python.exe -m ruff check src tests migrations
.\.venv\Scripts\python.exe -m ruff format --check src tests migrations
.\.venv\Scripts\python.exe -m mypy
```

**1642 PASS,79 deselected /21.04s**, w tym77 nowych unit/async A4c.
Ruff/format66 plików, strict mypy33 moduły PASS. Moduł orkiestracji ma96%
coverage w przebiegu bez PG; całe85% nie jest porównywane z historycznym
łącznym coverage unit+PG. AC sprawdzano scenariuszami, nie samym procentem.
Autor testów niezależnie wykonał77 PASS /1.45s. Test cache-lock dopuszcza
co najwyżej jeden pomocniczy revoke wyłącznie przed pierwotnym work deadline;
uwzględnia rozdzielczość timerów Windows, bez zmiany budżetu produktu.

Walidator kontraktów:21 operacji OpenAPI,5 valid/13 invalid fixtures,
2 wektory JCS,8 request cases PASS.5 dokumentów/48 lokalnych linków oraz
diff whitespace PASS. Zależności nie zmieniły się od maintenance `45f9eef`;
jego audyt34 pakietów/0 zgłoszonych podatności pozostaje odrębnym dowodem,
nie nowym skanem dla tej samej zawartości locka. Nie zmieniano ani ponownie
nie testowano frontendów, obrazów lub zdalnego CI.

Końcowy niezależny review `regulated_examples`: **GREEN**, bez pozostałych
blokerów zakresu. Reviewer powtórzył wyłącznie konkretną regresję P2:
**1 PASS /0.15s**; nie przypisujemy mu pełnych przebiegów integratora.
Końcowy odczyt Docker nie znalazł pozostawionych kontenerów ani sieci
`io.torii.scope=b1-integration`. Nie używano globalnego cleanup.

## Granica ukończenia

To odbiór wewnętrznej kompozycji SP01-04b, nie login przeglądarki lub cały SP-01.
Rzeczywisty PostgreSQL i podpisane testowe tokeny nie dowodzą konfiguracji
Keycloak. B2b pozostają: trasy HTTP, parsing query/cookie/Origin/CSRF/Bearer,
tożsamość i autoryzacja requestu, chronione projekty, bootstrap, IdP/UI E2E,
polityka logów IdP/gateway i współpraca z timeout middleware.

Nie zmieniono IdentityStore, migracji, Settings, deploymentu lub frontendów.
Brak nowego rejestru operacji/kompensacji, federated logout lub auto-refresh.
Nieznany credential sesji przy commit-unknown nie jest zwracany; rekord podlega
dotychczasowym idle30min/absolute8h. Wydanie enterprise, restore, limiter,
metryki/retencja, skany/SBOM, NFR i UX pozostają osobnymi bramkami.
Review agenta nie zastępuje audytu człowieka. Bez push/PR i bez zmian legacy.
