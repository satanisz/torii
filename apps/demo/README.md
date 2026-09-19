# Torii — demonstrator konceptu

Osobna lokalna aplikacja do ręcznego testowania. **Bez SSO i współdzielenia;
nie używaj danych firmy i nie wystawiaj serwera w sieci.** Istniejąca instalacja
AutoML i enterprise API nie są modyfikowane. Kontrakt: [SPEC-0018](../../specs/0018-concept-demo/README.md).

## Start na Windows

Z katalogu repozytorium `C:\Users\stani\Projects\frame-ml\torii`:

```powershell
.\scripts\demo.ps1
```

Skrypt instaluje zamrożone zależności we własnym `apps/demo/.venv`, buduje
istniejący frontend i uruchamia oddzielny proces w tle. Wejdź na
**http://127.0.0.1:18440**. Docker nie jest wymagany dla tego demonstratora.
Wymagane: lokalne uv oraz Node/npm zgodne z `apps/web/package.json`.

```powershell
.\scripts\demo.ps1 -Action Status
.\scripts\demo.ps1 -Action Stop
```

Stop sprawdza zapisany PID, ścieżkę i czas utworzenia własnego procesu.
Odmówi podczas aktywnego treningu; zaczekaj na wynik. Nie usuwa żadnych danych.
Jeżeli start nie zgłosi gotowości, sprawdź `apps/demo/.local/stderr.log` i użyj
Stop przed ponownym Start. Nie zatrzymuj innych usług zajmujących port18440.
Po zmianie kodu zrób Stop/Start — działający proces nie ma hot reload.

## Ręczny scenariusz 5–10 minut

1. Utwórz projekt, np. „Mój pierwszy eksperyment”. Dodaj dane przykładowe.
   To160 syntetycznych wierszy, cechy x1/x2/x3 i target, z kilkoma brakami x2.
   Alternatywnie zaimportuj własny niesensytywny CSV UTF-8 rozdzielany przecinkiem.
2. Obejrzyj podgląd, profile kolumn, hash i wersję. Dane są osobnym obiektem.
3. Zapisz transformację „Usuń braki”, następnie ją wykonaj. Powstanie osobny
   wynikowy dataset ze wskazaniem źródła i wersji transformacji. Oryginał zostaje.
4. Wybierz wynikowy dataset. Zapisz model „Ridge”, cel target, cechy x1/x2/x3,
   alpha1. Uruchom eksperyment. Poczekaj na zakończenie.
5. Obejrzyj MAE, RMSE, R², podział train/test, ID prawdziwego runu MLflow,
   przewidywania i współczynniki. Pobierz model lub raport JSON.
6. Zapisz drugi model „Średnia” z algorytmem baseline. Uruchom na tej samej
   wersji danych. Porównaj metryki; Ridge powinien dobrze uchwycić syntetyczną
   zależność liniową. Współczynniki nie dowodzą przyczynowości.
7. Obejrzyj przepływ/lineage i eksport manifestu. Eksport zawiera definicje,
   hashe i metryki — bez wierszy danych, przewidywań i wag modelu.
8. Odśwież stronę, następnie Stop/Start. Projekt, wersje i zakończone wyniki
   powinny pozostać. Nowy import do wybranego obiektu tworzy nową wersję.

## Co działa, a co jest odłożone

Rzeczywiste: CSV/synthetic, trwałe projekty i wersje, cztery deklaratywne
transformacje, trening Ridge i baseline średniej, oddzielny proces wykonania,
lokalny MLflow, metryki, raport, własny plik modelu, porównania i lineage.
Wyniki nie są mockami. Trening: seed42, test25%, preprocessing wyłącznie train.
Baseline nie jest rozbudowanym mechanizmem modeli regułowych.

Odłożone: konta/ACL, SQL/konektory, Parquet, Jupyter, dowolny kod Python,
AutoML tuning, klasyfikacja, pełne XAI, harmonogramy i produkcyjne wdrożenia.
Manifest nie jest kompletnym replaybundle; zapisany joblib odtwarzaj wyłącznie
we własnym zaufanym środowisku. Nigdy nie ładuj joblib/pickle z nieznanego źródła.
UI „kandydat” nie oznacza zatwierdzenia do produkcji. Enterprise sprinty są otwarte.

Limity: żądanie8MiB (base64 ma narzut), CSV5000wierszy/50kolumn,
tekstkomórki2000znaków, trening minimum20wierszy, jeden run naraz, timeout120s.
Nieprawidłowy cel/cechy lub awaria trackingu daje failed, nie fikcyjny sukces.
Po awarii procesu osierocone runy mają failed; uruchom je ponownie.

## Dane lokalne i testy

`apps/demo/.local/data/torii.sqlite` — metadane i snapshoty, `mlflow.sqlite` —
rzeczywisty tracking, `runs/` — własne joby i artefakty. Wszystko ignorowane
przez Git. Nie korzystamy z `.env`, legacy PostgreSQL, MinIO czy MLflow.
Lokalny operator ma dostęp do wszystkich projektów tego demo.

```powershell
uv run --project apps/demo --frozen pytest -q apps/demo/tests
uv run --project apps/demo --frozen ruff check apps/demo/src apps/demo/tests
```

Testy używają osobnych katalogów tymczasowych. Podział na osobny entrypoint
jest opisany w [ADR-0004](../../adr/0004-local-concept-demo.md).
