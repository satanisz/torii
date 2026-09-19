# Torii — demonstrator konceptu

Lokalna aplikacja pokazująca rzeczywisty proces:
CSV → wersja danych → transformacja → model → eksperyment MLflow → analiza.
**Bez kont i SSO. Używaj danych syntetycznych lub innych niepoufnych danych;
nie wystawiaj serwera przez LAN, proxy ani Internet.** Lokalny operator ma
dostęp do wszystkich projektów. To osobny profil, nie tryb omijania zabezpieczeń
enterprise API ani potwierdzenie gotowości produkcyjnej.

[Repozytorium Torii](../../README.md) ·
[Prezentacja konceptu](../../docs/presentation/torii.html) ·
[Obsługa i diagnostyka](../../docs/demo-operations.md) ·
[Architektura i zależności](../../docs/demo-architecture.md)

## Uruchomienie na Windows

Potrzebne są PowerShell, `uv` dostępne w `PATH`, Python 3.12 oraz Node.js
`>=24.15.0 <25` i npm `>=11 <12`. `uv` zarządza osobnym środowiskiem demo;
przy braku Pythona lub paczek może potrzebować dostępu do sieci. Pierwsza
instalacja zależności frontendowych również wymaga dostępu do rejestru paczek.
Docker Desktop nie jest wymagany.

Z katalogu `C:\Users\stani\Projects\frame-ml\torii`:

```powershell
.\scripts\demo.ps1 -Action Start
```

Otwórz [http://127.0.0.1:18440](http://127.0.0.1:18440).
Skrypt przygotowuje `apps/demo/.venv` z zamrożonego `uv.lock`, buduje React
i uruchamia proces w tle. Jeśli demo już odpowiada, `Start` kończy się bez
przebudowy lub restartu. Po poprawce kodu użyj kolejno `Stop` i `Start`.

```powershell
.\scripts\demo.ps1 -Action Status
.\scripts\demo.ps1 -Action Stop
.\scripts\demo.ps1 -Action Start
```

`Stop` sprawdza tożsamość zapisanego procesu. Odmawia, gdy API zgłasza
aktywne wykonanie; poczekaj na wynik. Nie usuwa danych. Nie zatrzymuj innych
usług zajmujących port 18440 i nie kasuj katalogów w celu naprawienia startu.
Szczegółowe procedury: [instrukcja operacyjna](../../docs/demo-operations.md).

## Pierwszy eksperyment: 5–10 minut

1. Utwórz projekt, np. „Pierwszy eksperyment”, i dodaj dane przykładowe.
   Otrzymasz 160 syntetycznych wierszy: `x1`, `x2`, `x3`, `target`, z kilkoma
   brakami w `x2`. Alternatywnie zaimportuj niepoufny CSV.
2. Obejrzyj podgląd 20 wierszy, profile kolumn, hash i numer wersji.
   Dane są osobnym obiektem, a ponowny import do tego obiektu tworzy nową wersję.
3. Zapisz i wykonaj transformację „Usuń braki”. Powstanie nowy dataset
   ze wskazaniem wersji źródłowej i transformacji; oryginał pozostaje bez zmian.
4. Dla wynikowego datasetu zapisz model Ridge: cel `target`, cechy `x1`, `x2`,
   `x3`, `alpha = 1`. Uruchom eksperyment i poczekaj na zakończenie.
5. Obejrzyj MAE, RMSE, R², liczebności train/test, ID przebiegu MLflow,
   predykcje oraz współczynniki. Pobierz własny model lub raport JSON.
6. Zapisz drugi model — baseline średniej — i uruchom go na **tej samej wersji
   danych**, z tym samym celem. Porównaj metryki. Dla przykładu syntetycznego
   Ridge powinien uzyskać lepszy wynik niż stała średnia.
7. Obejrzyj przepływ powiązań i obiekt analizy utworzony po sukcesie.
   Wyeksportuj manifest projektu: zawiera definicje, hashe i metryki, ale
   nie wiersze danych, predykcje ani współczynniki/model.
8. Po zakończeniu wszystkich eksperymentów odśwież stronę i wykonaj
   `Stop` → `Start`. Sprawdź zachowanie projektów, wersji i wyników.

## Dane i ograniczenia

| Obszar | Obecny zakres |
|---|---|
| Import w GUI | Niepusty plik CSV do **5 MiB**, UTF-8, opcjonalny BOM, separator przecinek; nie Parquet ani Excel |
| Żądanie API | Maks. **8 MiB całego body**, w tym base64 i JSON; nie oznacza pliku CSV o rozmiarze 8 MiB |
| Tabela | Maks. 5000 wierszy, 50 kolumn i 250 000 komórek |
| Kolumny i komórki | Unikalne, niepuste nazwy do 100 znaków; tekst komórki do 2000 znaków; brak NaN/Inf |
| Braki | Puste pole CSV oznacza brak; tekst jest zachowany, wartości liczbowe zamieniane na skończone liczby |
| Transformacje | Usunięcie wierszy z brakami, usunięcie duplikatów, wybór kolumn, filtr liczbowy `>=` / `<=` |
| Trening | Regresja, co najmniej 20 wierszy; liczbowe cechy i cel, bez braków w celu; cel nie może być cechą |
| Wykonania | Jeden trening naraz, limit 120 s; brak kolejki wielu równoległych zleceń |

Podział jest deterministyczny: `seed = 42`, 25% danych testowych. Najpierw
następuje podział; dopiero później mediana do uzupełniania braków i
standaryzacja są dopasowywane **wyłącznie na train**. Cecha całkowicie pusta
w train powoduje odmowę treningu. Ridge ma `alpha` od 0 do 100; baseline
przewiduje średnią celu z train.

Współczynniki Ridge dotyczą standaryzowanych cech. Nie są dowodem
przyczynowości, pełnym XAI ani uniwersalnym rankingiem ważności. Porównuj
przebiegi na zgodnych wersjach danych, celu i podziale.

## Zapis, pobieranie i granice demo

Metadane i snapshoty znajdują się w `apps/demo/.local/data/torii.sqlite`,
tracking w `mlflow.sqlite`, a joby i artefakty w `runs/`. Cały katalog `.local`
jest ignorowany przez Git. Demo nie czyta root `.env` i nie korzysta ze starych
usług PostgreSQL, MinIO ani MLflow.

Dla zakończonego sukcesem przebiegu dostępne są `model.joblib`, `result.json`
i `environment.json`. Model zawiera także preprocessing; ładuj wyłącznie
własny zaufany plik w zgodnym środowisku. Nie importuj obcych plików
joblib/pickle. Eksport CSV neutralizuje teksty wyglądające jak formuły arkusza,
więc nie należy traktować go jako bezstratnego pakietu odtworzenia.

Nieprawidłowe dane, timeout lub awaria trackingu kończą wykonanie jako `failed`,
bez udawanego sukcesu MLflow. Po restarcie osierocone `queued`/`running`
otrzymują status `failed`; nową próbę uruchamia operator.

Odłożone są konta/ACL, konektory SQL, Parquet, Jupyter, własny kod Python,
AutoML/tuning, klasyfikacja, rozbudowane modele regułowe, pełne XAI,
harmonogramy i wdrożenia produkcyjne. Etykieta „kandydat” jest oznaczeniem UI,
nie zatwierdzeniem do produkcji. Manifest nie jest pełnym replay bundle.

## Testy i dokumenty

Z katalogu repozytorium:

```powershell
uv run --project apps/demo --frozen pytest -q apps/demo/tests
uv run --project apps/demo --frozen ruff check apps/demo/src apps/demo/tests
```

Testy demo korzystają z osobnych katalogów tymczasowych. Instrukcje testowania
frontendu oraz kopii lokalnych danych są w
[instrukcji operacyjnej](../../docs/demo-operations.md).

Zakres: [SPEC-0018](../../specs/0018-concept-demo/README.md).
Decyzja o osobnym profilu: [ADR-0004](../../adr/0004-local-concept-demo.md).
Wykonane kontrole i ograniczenia: [dowody](../../specs/0018-concept-demo/evidence.md).
