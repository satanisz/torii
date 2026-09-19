# SPEC-0018 — dowody lokalnego demonstratora

2026-09-19; baseline `7b65bd8`. SDD: SPEC/ADR Accepted (delegated) po
niezależnym contract_review przed kodem. Cel zmieniony przez użytkownika:
testowalny koncept, nie zakończenie enterprise sprintów.
Kod, specyfikacja, ADR i testy: lokalny commit `e44d6d5`.

## Wykonane kontrole

- Test-first: nowe API i frontend zaczęły RED z brakującymi modułami.
  Silnik danych/worker również miał osobny RED przed implementacją.
- Root `uv run --project apps/demo --frozen pytest -q apps/demo/tests`:
  **54 PASS /14.45s**. API10, data/worker37, lifecycle7. Real sklearn i lokalny
  MLflow/subprocess w testach; timeout/busy testy kontrolowane mockiem, nie
  dowód odmierzania rzeczywistych120s. Reprodukcja Ridge identyczne metryki.
- Demo Ruff/check/format: **PASS**,10 plików. Nowy izolowany uv.lock66packages;
  pip-audit2.10.1 **no known vulnerabilities**, rekomendacja pełnych hashy jawna.
- Frontend **68 PASS** (18 demo +50 istniejących), lint/typecheck/build,
  enterprise API type drift i npm audit **PASS /0 vulnerabilities**.
- Regresja backendu enterprise **1400 PASS,53 integration deselected /9.22s**.
  Nie zmieniono tego backendu, migracji ani deploy/platform; PostgreSQL tej
  zmiany nie uruchamiano. Ostatnie dowody53 PG pozostają przy B2a4a.
- Dwa istniejące deprecation warnings Starlette/httpx i AnyIO pozostały jawne.
  To nie pełny security scan ani kwalifikacja enterprise, brak zdalnego CI.
- Niezależny contract_review: source backend/worker/React GREEN,
  osobno54 backend i68 frontend PASS, lint/types PASS. Nie audyt człowieka.

## Rzeczywisty odbiór UI i HTTP

`scripts/demo.ps1` uruchomił serwer na **127.0.0.1:18440**, bez Dockera/root.env.
W przeglądarce Codex, bez mocka sieci, wykonano:

1. Nowy projekt „Torii — prezentacja”. Dane syntetyczne160 wierszy.
2. Zapis osobnej transformacji drop_missing i jej wykonanie:155 wierszy,
   odrębny dataset, źródło160 zachowane. Wybrana konkretna wersja wyniku.
3. Zapis Ridge i trening z GUI, automatyczny polling do succeeded, analiza,
   współczynniki,20 predykcji, prawdziwy ID MLflow.
4. Zapis baseline średniej i drugi trening na tej samej wersji danych;
   tabela rzeczywiście porównuje wyniki, kliknięcie wybiera odpowiednią analizę.

| Model | MAE | RMSE | R² | Train/test |
|---|---:|---:|---:|---|
| Ridge alpha1 | 0.6498 | 0.7963 | 0.9986 | 116/39 |
| Średnia train | 17.5200 | 21.7702 | -0.0718 | 116/39 |

To dane syntetyczne o zadanej zależności liniowej, nie ocena jakości biznesowej.
Torii runs `c11d5916-38fd-4f42-a444-e49942613861`,
`4f3c06ba-c53d-4e67-ac92-78a8b5053ce4`; MLflow runs
`4d4951ad790543b499f569ea37249c78`, `3a1efa91aa5c48e6b437d9963d3f0d56`.
Wszystkie w nowym ignorowanym apps/demo/.local/data, bez istniejącego MLflow.

Real HTTP pobranie result.json potwierdziło ID i podział116/39. Eksport
7obiektów/2runów nie zawiera payload/preview/predictions/importance. Test API
potwierdza pobieranie własnego joblib i odmowę job.json. Import CSV/wersjonowanie
zweryfikowano w realnych handlerach TestClient i komponentach; browser walkthrough
użył wbudowanych danych, nie ręcznego chooser plikuCSV.

Dwa cykle Stop/Start sprawdziły własność procesu i zachowanie projektu,
wersji oraz obu zakończonych wyników; po odświeżeniu przeglądarki były widoczne.
Domyślny viewport obejrzano na screenshot, również wąski390x844; przy wąskim
widoku document.scrollWidth=clientWidth375, brak overflow całej strony.
Temporary viewport reset. Nie jest to pełny audyt WCAG ani test urządzeń.

## Wykryte i poprawione podczas odbioru

- Raw nagłówek HTTP obs-text powodował UTF-8 decode failure; latin-1 i test
  rawASGI RED→GREEN. TestClient normalizował nagłówek, więc sam nie wystarczył.
- result={} przed sukcesem groził błędem UI; kontrakt null dla pending/failed,
  obie strony i testy spójne. Żadnych fikcyjnych wyników.
- Stan składany z kilku odczytów mógł pokazać succeeded bez wcześniejszej analizy.
  Jeden proces/RLock spina snapshot, nie blokuje treningu. Deterministyczny
  test realnego lockattempt; kontrolne pominięcie lock tylko w osobnym procesie
  daje oczekiwany FAIL, zwykły kod GREEN.
- Powolny poprzedni odczyt UI mógł nadpisać nowszy sukces; test RED→GREEN,
  monotoniczny numer odczytu ignoruje stare odpowiedzi.
- Windows venv python.exe jest redirectorem; pierwsza próba kontrolna ujawniła
  różnicę PID launchera i socket owner. Start zapisuje zweryfikowany listener
  child tego launchera. Stop sprawdza executable/module/data-dir/creationticks.
  PowerShell7 ConvertFrom-Json parsuje daty automatycznie; porównujemy ticks,
  nie datę przekonwertowaną do lokalnego stringa. Ponowny cykl start/stop PASS.
- Końcowy review wykrył zależność zapisu PID listenera od sukcesu /state.
  D07 rozszerzone przed poprawką: recorder działa przed HTTP i na timeout,
  dzięki czemu awaria readiness nie zostawia jedynie PID redirectora.
  Brak funkcji potwierdzony RED; kolejny rzeczywisty Stop/Start PASS.
  `scripts/test-demo-launcher.ps1`: 4 PASS (brak listenera, własne dziecko,
  obcy listener, bezpośredni PID). Kontrolowane stuby OS, bez realnych zapisów;
  nie jest to rzeczywiste wymuszenie awarii HTTP. Final review launchera GREEN.
  Staged diff-check i porównanie z 13 lokalnymi sekretami PASS, bez ujawnienia
  wartości. To kontrola zakresu commita, nie skan całej historii Git.

## Jawne ograniczenia i odbiór

D01–D07 zweryfikowane w podanym lokalnym zakresie i ścieżkach; nie oznacza
pełnego pokrycia wszystkich kombinacji przeglądarek/danych/awarii.
Bez SSO/multiuser/SQL/Parquet/Jupyter/arbitraryPython/production/fullXAI.
SQLite/localworker nie są zastępstwem enterprise infrastructure. ImportCSV
UI max5MiB uwzględnia narzutbase64 pod backendowym8MiB. Do danych niesensytywnych.
Przejściowy błąd pollingu może pozostawić baner do ręcznego „Odśwież”.
Gdy start przekroczy readiness timeout, zachowuje rekord własnego procesu;
operator ma instrukcję Stop, dane nie są kasowane.

Root.env, legacy/trwałe wolumeny, istniejące usługi, firma i remote bez zmian.
Wyłącznie lokalne commity; brak push/PR. Pozostawiono działający serwer demo
i syntetyczny projekt z wynikami do testów użytkownika. Instrukcja:
[apps/demo/README](../../apps/demo/README.md). Następny krok: feedback użytkownika,
nie automatyczne wracanie do wcześniejszego enterprise OIDC.
Automatyzacja `torii-realizacja-sprint-w` wstrzymana (PAUSED, potwierdzone narzędziem)
po wykonaniu uzgodnionego lokalnego zakresu, aby zachować stabilną wersję do testów.
