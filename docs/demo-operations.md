# Torii demo — obsługa i diagnostyka

Ta instrukcja dotyczy wyłącznie lokalnego demonstratora `apps/demo`, nie starej
instalacji Docker ani enterprise API. Korzystaj z danych syntetycznych lub
niepoufnych. Brak kont i SSO oznacza, że każdy lokalny operator mający dostęp
do aplikacji może odczytywać wszystkie projekty. Nie udostępniaj portu w sieci.

[Szybki start i scenariusz](../apps/demo/README.md) ·
[Architektura](demo-architecture.md) ·
[Prezentacja](presentation/torii.html) · [Główne README](../README.md)

## 1. Wymagania i pierwszy start

Polecenia poniżej wykonuj w PowerShell z katalogu repozytorium, domyślnie
`C:\Users\stani\Projects\frame-ml\torii`.

- `uv` musi być dostępne w `PATH`; projekt wymaga Pythona `>=3.12,<3.13`.
  `uv sync --frozen` tworzy odizolowane `apps/demo/.venv` zgodnie z lockfile.
- Frontend wymaga Node.js `>=24.15.0 <25` oraz npm `>=11 <12`.
- Pierwsze pobranie Pythona/paczek może wymagać Internetu; sam scenariusz
  danych syntetycznych i lokalny tracking nie potrzebują chmury.
- Port TCP 18440 musi być wolny. Docker Desktop nie jest potrzebny.

Sprawdzenie narzędzi nie zmienia danych:

```powershell
uv --version
node --version
npm --version
```

Uruchomienie:

```powershell
.\scripts\demo.ps1 -Action Start
```

Otwórz [http://127.0.0.1:18440](http://127.0.0.1:18440). Launcher synchronizuje
Python, instaluje frontend, jeśli nie ma `node_modules`, buduje `dist` i startuje
własny proces w tle. Nie uruchamia Compose ani nie odczytuje root `.env`.

Jeżeli polityka PowerShell blokuje lokalne skrypty, sprawdź przyczynę zgodnie
z zasadami swojej stacji. Nie zmieniaj globalnie polityk bezpieczeństwa
ani firmowych ustawień, aby ominąć blokadę.

## 2. Status, zatrzymanie i restart po poprawce

```powershell
.\scripts\demo.ps1 -Action Status
```

Status sprawdza odpowiedź `/demo-api/state` z trybem `local-demo`. To test
dostępności API, nie dowód sprawności treningu, trackingu czy pełnego UI.

Przed zatrzymaniem poczekaj, aż nie będzie przebiegów `queued`/`running`:

```powershell
.\scripts\demo.ps1 -Action Stop
```

Launcher weryfikuje zapisany PID, ścieżkę programu, linię polecenia i czas
utworzenia procesu; odmawia zabicia procesu o niezgodnej tożsamości. Gdy API
zgłasza aktywny trening, odmawia zatrzymania. Nie usuwa danych.

Nie ma hot reload. Sam `Start` przy odpowiadającym demo **nie** wczytuje zmian
kodu, nie synchronizuje zależności i nie przebudowuje frontendu. Po poprawce:

1. Zakończ aktywne eksperymenty i użyj `Stop`.
2. Jeśli zmienił się `apps/web/package-lock.json`, odśwież frontendowe
   zależności poleceniem poniżej. Launcher nie wykonuje `npm ci`, gdy
   `node_modules` już istnieje.
3. Uruchom `Start`, poczekaj na gotowość i odśwież stronę.
4. Sprawdź projekty i wykonaj mały eksperyment na danych syntetycznych.

```powershell
npm --prefix apps/web ci --ignore-scripts
.\scripts\demo.ps1 -Action Start
```

Po nieoczekiwanym przerwaniu procesu startup oznacza osierocone przebiegi jako
`failed`. Nie wznawia automatycznie treningu. Jeśli API przestało odpowiadać,
sam komunikat „not responding” nie dowodzi, że proces roboczy już nie działa;
przed kopią danych lub naprawą należy to osobno ustalić.

## 3. Diagnostyka bez ujawniania danych

| Objaw | Bezpieczny następny krok |
|---|---|
| Port 18440 jest zajęty | Sprawdź właściciela portu; jeśli to demo, użyj jego `Status`/`Stop`. Nie zatrzymuj obcej usługi. |
| Start nie zgłosił gotowości | Sprawdź lokalnie `.local/stderr.log`. Przed kolejnym startem ustal status własnego procesu; nie kasuj danych ani `process.json` w ciemno. |
| UI jest stare lub brak `demo.html` | Po zakończeniu treningu `Stop` → `Start`, aby wykonać build i restart; odśwież stronę. |
| Import CSV nie działa | UTF-8 (BOM dopuszczalny), przecinek, plik do 5 MiB w GUI, do 5000 wierszy i 50 kolumn, unikalne nagłówki. Nie `.xlsx`, Parquet ani CSV rozdzielany średnikiem. |
| API zwraca 413 | Body przekroczyło 8 MiB; base64 powiększa plik. Zmniejsz wejście, nie zwiększaj limitu na potrzeby pojedynczego testu. |
| API zwraca 409 przy treningu | Jeden eksperyment już trwa. Poczekaj; demo nie jest kolejką wielu zleceń. |
| Run ma `failed` | Sprawdź minimum 20 wierszy, liczbowe cechy, cel bez braków, cechy różne od celu, czas 120 s i zapis do lokalnego magazynu. |
| Brak pobrania artefaktu | Artefakty dostępne są wyłącznie dla `succeeded` i nazw `model.joblib`, `result.json`, `environment.json`. |
| Zapis w przeglądarce przekroczył czas | Najpierw odśwież stan. Odpowiedź mogła zaginąć po zapisie; ponowienie może utworzyć kolejny obiekt. |
| Stop odmawia z powodu ownership | Nie obchodź kontroli ani nie zabijaj PID „na próbę”. Wyjaśnij rozbieżność rekordu i procesu. |

Lokalne sprawdzenia tylko do odczytu:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 18440 -ErrorAction SilentlyContinue
Get-Content -LiteralPath .\apps\demo\.local\stderr.log -Tail 40
```

Log traktuj jako materiał lokalny: przed udostępnieniem przejrzyj i usuń
identyfikujące ścieżki lub dane. Nie załączaj `.env`, `job.json`, baz SQLite,
plików modeli, pełnych eksportów ani zrzutów payloadów do publicznego zgłoszenia.
Przydatne zgłoszenie zawiera wersję/commit, etap, status HTTP/run, wersje narzędzi
oraz minimalny przykład syntetyczny. API nie publikuje raw traceback procesu
roboczego; jego stdout/stderr są celowo odrzucane przez launcher treningu.

## 4. Co przechowujemy lokalnie

Domyślny układ utworzony przez `scripts/demo.ps1`:

```text
apps/demo/.local/
├── process.json                 zapis tożsamości procesu launchera
├── stdout.log, stderr.log        lokalne logi serwera
└── data/
    ├── torii-demo-v1             znacznik katalogu należącego do demo
    ├── torii.sqlite              projekty, obiekty, wersje, snapshoty, runy
    ├── mlflow.sqlite             eksperymenty, parametry, metryki MLflow
    └── runs/
        ├── <torii-run-id>/       job.json, model, wynik, środowisko, staging
        └── mlflow-artifacts/     kopie artefaktów zarządzane przez MLflow
```

`job.json` zawiera snapshot danych do treningu. Backup tego katalogu jest
kopią danych, nawet jeśli manifest projektu pomija payloady. `.gitignore`
zapobiega zwykłemu dodaniu runtime do Git, ale nie jest szyfrowaniem ani ACL.

## 5. Ręczna kopia bezpieczeństwa — tylko po zatrzymaniu

To ostrożna instrukcja wykonania kopii lokalnego demo, **nie zweryfikowana
procedura odtworzenia ani kwalifikacja DR**. Nie wykonuj kopii otwartych baz
metodą zwykłego kopiowania plików podczas treningu lub pracy serwera.

1. Poczekaj na zakończenie wszystkich przebiegów. Zatrzymaj własne demo
   przez `Stop`; upewnij się, że zakończył się również jego worker. Jeśli proces
   jest osierocony lub API nie odpowiada, najpierw wyjaśnij jego stan.
2. Zanotuj bieżący commit, bezwzględną ścieżkę katalogu danych oraz wersje
   narzędzi. Zachowaj zgodny kod, `uv.lock` i `package-lock.json`.
3. Ręcznie skopiuj **całe** `apps/demo/.local/data`, razem ze znacznikiem,
   obiema bazami, całym `runs/` i ewentualnymi plikami pomocniczymi SQLite.
   Wybierz nowy, jednoznacznie nazwany katalog poza repozytorium; nie
   nadpisuj wcześniejszej kopii. Nie wystarcza sam `torii.sqlite` ani manifest.
4. Porównaj kompletność drzewa, rozmiary i — jeśli to możliwe — sumy plików
   źródłowych oraz kopii. Zapisz datę i wynik kontroli; chroń kopię jak dane.
5. Nie kopiuj `process.json` z powrotem jako rekordu aktywnego procesu.
   Nowy start powinien utworzyć własny aktualny rekord. `.venv` i `node_modules`
   odtwarza się z lockfile, nie są zamiennikiem kopii danych.

MLflow zapisuje **bezwzględne URI artefaktów**. Proste przeniesienie kopii
do innej ścieżki, konta Windows lub komputera może zerwać odwołania;
worker sprawdza zgodność lokalizacji eksperymentu. Najprostszy zakładany
wariant przywrócenia to ta sama bezwzględna ścieżka i zgodny kod/środowisko,
ale również ten wariant wymaga oddzielnej próby odtworzenia. Nie został tutaj
zwalidowany. Nie edytuj ścieżek w bazie ani nie nadpisuj bieżących danych
bez osobnego planu i zachowania ich kopii.

Eksport JSON projektu oraz pobrany CSV/model są użytecznymi artefaktami,
lecz nie zastępują pełnego backupu i nie tworzą automatycznie replay bundle.

## 6. Kontrole developerskie

Backend demo — nowe katalogi tymczasowe, bez używania danych aktywnej aplikacji:

```powershell
uv run --project apps/demo --frozen pytest -q apps/demo/tests
uv run --project apps/demo --frozen ruff check apps/demo/src apps/demo/tests
uv run --project apps/demo --frozen ruff format --check apps/demo/src apps/demo/tests
```

Frontend — wspólne zależności/build dla demo i osobnego UI enterprise:

```powershell
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web test
npm --prefix apps/web run build
```

`build` obejmuje także kontrolę wygenerowanych typów enterprise API; błąd tego
kroku nie oznacza, że demo zaczęło wymagać działającego Keycloak/PostgreSQL.
Testy mockowanych awarii nie zastępują rzeczywistego przebiegu worker/MLflow.
Po zmianie zachowania wykonaj też
[scenariusz manualny](../apps/demo/README.md#pierwszy-eksperyment-510-minut).
Aktualne wykonane kontrole: [SPEC-0018 — evidence](../specs/0018-concept-demo/evidence.md).

Źródła tej instrukcji: [launcher](../scripts/demo.ps1),
[entrypoint](../apps/demo/src/torii_demo/__main__.py),
[API](../apps/demo/src/torii_demo/app.py),
[worker](../apps/demo/src/torii_demo/worker.py),
[manifest Python](../apps/demo/pyproject.toml),
[manifest frontend](../apps/web/package.json).
