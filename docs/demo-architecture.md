# Torii demo — architektura i zależności

Opis dotyczy działającego profilu lokalnego z [SPEC-0018](../specs/0018-concept-demo/README.md).
Nie należy go utożsamiać z kompletną architekturą enterprise.
Rozdzielenie profili uzasadnia [ADR-0004](../adr/0004-local-concept-demo.md).

[Szybki start](../apps/demo/README.md) · [Obsługa](demo-operations.md) ·
[Prezentacja](presentation/torii.html) · [Główne README](../README.md)

## Co łączy interfejs

Jedno repozytorium zawiera moduły o różnych odpowiedzialnościach. Dane,
transformacje, modele i analizy mają własne obiekty oraz wersje; wykonanie
jest osobnym rekordem odnoszącym się do konkretnych wersji.

```text
Przeglądarka: React / TypeScript (demo.html)
                  │ ten sam origin, /demo-api
                  ▼
       Uvicorn + FastAPI, jeden proces, 127.0.0.1:18440
          │              │                    │
          ▼              ▼                    ▼
       data.py        store.py          osobny worker Python
   CSV / profile /    sqlite3          podział train/test → Pipeline
    transformacje        │                    │
                         ▼                    ├── własne pliki runu
                    torii.sqlite              └── MlflowClient
                                                   ├── mlflow.sqlite
                                                   └── lokalne artefakty
```

CSV jest przetwarzany w ograniczonej, deklaratywnej ścieżce API. Trening
działa w oddzielnym subprocessie z tego samego środowiska Python.
Nie jest to sandbox dla dowolnego kodu użytkownika: takiego kodu demo nie przyjmuje.
Nie ma tu klastra obliczeniowego, kolejki rozproszonej ani serwera MLflow UI.

## Mapa modułów — gdzie szukać zachowania

| Moduł | Odpowiedzialność i zależności |
|---|---|
| [scripts/demo.ps1](../scripts/demo.ps1) | Windows: przygotowanie `.venv`, build frontendu, start/status/stop własnego procesu; bez Compose i root `.env` |
| [__main__.py](../apps/demo/src/torii_demo/__main__.py) | Jawne `--local-demo`, zajęcie loopback przed otwarciem danych, Uvicorn z jednym procesem |
| [app.py](../apps/demo/src/torii_demo/app.py) | FastAPI/Pydantic, walidacja formularzy i origin/Host, katalog, wykonania transformacji, jeden aktywny subprocess, pobieranie artefaktów |
| [data.py](../apps/demo/src/torii_demo/data.py) | Standardowa biblioteka Pythona: CSV UTF-8, finite scalar snapshots, profile, dane syntetyczne, cztery transformacje bez `eval`/`exec` |
| [store.py](../apps/demo/src/torii_demo/store.py) | Standardowe `sqlite3`: projekty, obiekty, wersje, runy; transakcje, hash, spójny odczyt stanu, eksport i oznaczenie osieroconych wykonań |
| [worker.py](../apps/demo/src/torii_demo/worker.py) | NumPy/scikit-learn: trening i metryki; joblib: zapis Pipeline; MLflow: parametry, metryki i artefakty, zawsze jawnie lokalne |
| [src/demo](../apps/web/src/demo) | Ekrany React: katalog danych, transformacje, modele, eksperymenty, wyniki i powiązania; osobny adapter `/demo-api` |
| [api.ts](../apps/web/src/demo/api.ts) | Same-origin fetch, brak automatycznych powtórzeń zapisu, 15 s oczekiwania na HTTP, CSV do 5 MiB przed base64 |
| [vite.config.ts](../apps/web/vite.config.ts) | Jeden build tworzy oddzielne wejścia `index.html` i `demo.html`; gotowe pliki demo serwuje FastAPI |

Node/npm służą do budowania i testowania UI. Po buildzie aplikację obsługuje
serwer Python; launcher nie uruchamia dodatkowego serwera Node ani Vite dev.

## Model danych i przebieg eksperymentu

W `torii.sqlite` znajdują się:

- `projects` — lokalne projekty;
- `objects` — tożsamość i rodzaj: dataset, transformation, model, analysis;
- `versions` — kolejne definicje, payload/snapshot, numer i SHA-256;
- `runs` — stan wykonania i konkretne `model_version_id` / `dataset_version_id`.

Hash powstaje z deterministycznie serializowanego JSON definicji i payloadu.
Nie jest podpisem cyfrowym ani dowodem pochodzenia danych. Aplikacja dopisuje
wersje zamiast nadpisywać wcześniejsze; nie oznacza to odporności na ręczną
edycję pliku SQLite przez lokalnego właściciela.

Przebieg:

1. Import zapisuje snapshot danych i profil. Powtórny import do tego samego
   obiektu tworzy kolejną wersję.
2. Transformacja zapisuje deklarację i wersję źródła. Jej wykonanie tworzy
   nowy dataset z odniesieniem do obu wersji; nie modyfikuje źródła.
3. Model jest definicją wyboru algorytmu, celu, cech i parametrów — jeszcze
   nie wytrenowanym plikiem. Cel nie może być cechą.
4. Run utrwala odwołania do wersji modelu i danych. API zwraca 202;
   stan przechodzi `queued` → `running` → `succeeded` albo `failed`.
   Drugie aktywne zlecenie otrzymuje 409, nie czeka w trwałej kolejce.
5. Worker wykonuje podział z `seed = 42`, `test_size = 0.25`, a następnie
   dopasowuje na train median imputer, StandardScaler i Ridge lub DummyRegressor.
   Braki w celu oraz cecha całkowicie pusta w train powodują odmowę.
6. Parametry, rzeczywiste MAE/RMSE/R² i trzy artefakty trafiają do MLflow.
   Logowanie parametrów/metryk jest synchroniczne; failure nie jest sukcesem.
   Po zakończeniu tracking/artifact calls worker publikuje `result.json`.
7. API tworzy obiekt analizy powiązany z runem i wersjami, po czym zapisuje
   `succeeded`. Odczyt całego stanu jest chroniony blokadą jednego procesu,
   aby nie pokazać późniejszego sukcesu bez wcześniejszego obiektu analizy.

MLflow ma własny `mlflow_run_id`, odrębny od ID wykonania Torii. Wynik zawiera
oba powiązania poprzez rekord runu i jego payload. Oddzielne bazy nie tworzą
jednej rozproszonej transakcji: awaria między zapisami może wymagać ponownego
wykonania. Restart oznacza niedokończone runy jako `failed`, nie odtwarza ich
automatycznie. Nie jest to gwarancja wykonania dokładnie raz.

## Biblioteki: po co są w aplikacji

Kanoniczne deklaracje: [pyproject.toml](../apps/demo/pyproject.toml),
[uv.lock](../apps/demo/uv.lock), [package.json](../apps/web/package.json)
i [package-lock.json](../apps/web/package-lock.json).
Lockfile ustalają konkretne wersje, również tam, gdzie manifest Python dopuszcza
zakres. Korzystaj z `uv ... --frozen` i `npm ci`, nie z przypadkowego środowiska.

| Zależność | Rola w obecnym demo |
|---|---|
| Python 3.12 | Serwer, standardowy parser CSV, SQLite i proces roboczy |
| FastAPI + Pydantic + Uvicorn | Endpointy, walidacja żądań i lokalny serwer HTTP |
| NumPy + scikit-learn | Macierze liczbowe, stały train/test split, Pipeline, Ridge/Dummy i metryki |
| joblib | Zapis własnego wytrenowanego Pipeline wraz z preprocessingiem; brak importu obcych modeli |
| mlflow-skinny 3.14.0 | Klient rzeczywistego lokalnego trackingu; bez uruchamiania osobnej usługi MLflow |
| SQLAlchemy + Alembic | Obsługa SQL i schematu magazynu MLflow; nie ORM dla `store.py`, które używa `sqlite3` |
| pandas | Część zainstalowanego stosu ML/MLflow; aktualny importer CSV Torii nie używa pandas |
| React + ReactDOM + TypeScript | Komponenty i typy UI; wspólny projekt frontendowy z osobnym wejściem demo |
| Vite | Build statycznych zasobów, nie wymagana usługa produkcyjna demo |
| pytest / HTTPX / Ruff | Testy Pythona, klient testowy API, kontrola stylu i błędów kodu |
| Vitest / Testing Library / ESLint | Testy komponentów i jakość frontendu |

Wymagania frontendowego środowiska build: Node `>=24.15.0 <25`, npm `>=11 <12`.
Wspólny build sprawdza też wygenerowany kontrakt enterprise API, ale demo
korzysta z własnych endpointów i nie wymaga działającego enterprise backendu.

Worker otrzymuje ograniczone środowisko procesu, jawne lokalne URI SQLite
i katalog artefaktów. Nie korzysta z odziedziczonego `MLFLOW_TRACKING_URI`;
telemetria MLflow jest wyłączana przed jego importem w workerze.
To ograniczenie integracji demo, nie ogólny firewall ani audyt całego stosu.

## Pliki, Git i przenoszenie

W Git są kod modułów, deklaracje, specyfikacje i lockfile. W ignorowanym
`apps/demo/.local/data` są rzeczywiste snapshoty, joby, bazy i modele.
Nie dodawaj `.local`, CSV z danymi, sekretów ani artefaktów modeli przez `git add -f`.

Eksport projektu zawiera definicje, hashe, metryki, podstawowe dane środowiska
i identyfikatory. Pomija snapshoty, podglądy, predykcje, współczynniki i pliki
modeli. Nadaje się do przeglądu deklaracji, ale nie jest pełnym replay bundle:
nie ma automatycznego importu/odtworzenia takiego manifestu.

`environment.json` dokumentuje Python, system i wybrane wersje bibliotek;
nie jest kompletnym obrazem wykonawczym ani lockfile. Joblib wymaga zaufania
do pliku i zgodnego środowiska. Pełny katalog danych zawiera także bezwzględne
odwołania MLflow: zasady kopii i ograniczenia odtworzenia opisuje
[instrukcja operacyjna](demo-operations.md#5-ręczna-kopia-bezpieczeństwa--tylko-po-zatrzymaniu).

## Demo a planowana platforma

| Obecny profil demo | Osobna ścieżka platformy / zakres odłożony |
|---|---|
| SQLite + lokalne pliki | PostgreSQL i zewnętrzny magazyn obiektowy; legacy MinIO nie jest używany przez demo |
| Jeden lokalny operator, brak SSO | Integracja tożsamości, konta, ACL i współdzielenie; Keycloak jest częścią odrębnego stosu developerskiego |
| Bezpośredni HTTP na loopback | Osobny gateway Caddy/HTTPS i infrastruktura enterprise; nie są elementami startu demo |
| Jeden ograniczony subprocess | Kolejkowanie, izolowane executory, harmonogramy i kontrolowane środowiska |
| CSV, regresja, współczynniki | Parquet/SQL, Jupyter, inne klasy modeli, rozbudowane XAI i produkcyjny lifecycle |

Istniejące [apps/api](../apps/api/README.md) i
[deploy/platform](../deploy/platform/README.md) są inną ścieżką realizacji,
nie wymaganymi zależnościami lokalnego demo. Uruchomienie demo nie startuje
PostgreSQL, Keycloak, Caddy ani MinIO, nie zmienia ich danych i nie zalicza
niedokończonych sprintów enterprise.

Ochrony Host/origin/nagłówka i brak CORS ograniczają przypadkowe wywołania
z obcej strony, lecz nie uwierzytelniają lokalnych procesów ani operatorów.
Podział projektów sprawdza spójność referencji, nie ustanawia wieloużytkownikowego
ACL. Etykieta „kandydat” nie jest zatwierdzeniem ani deploymentem produkcyjnym.
