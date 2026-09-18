# Torii — AutoML Workshop Stack — scenariusze warsztatowe

Ten materiał służy do praktycznego przejścia przez możliwości lokalnego stosu
AutoML: od danych źródłowych, przez walidację i transformacje, po AutoML,
rejestr modeli, predykcje oraz katalog i lineage. Ćwiczenia można wykonać jako
całość albo niezależne moduły.

Diagram komponentów, zależności oraz sekwencję kompletnej sesji treningowej
znajdziesz w sekcji **Architecture and persistence** dokumentu
[`automl-mvp.md`](automl-mvp.md#architecture-and-persistence).

## Plan warsztatów

| Moduł | Temat | Orientacyjny czas |
|---|---|---:|
| 0 | Uruchomienie i orientacja w architekturze | 20 min |
| 1 | Dane, wersjonowanie i MinIO | 35 min |
| 2 | Walidacja oraz transformacje | 45 min |
| 3 | AutoML i śledzenie eksperymentów | 60 min |
| 4 | Rejestr, promocja i rollback modelu | 40 min |
| 5 | Predykcja poza procesem treningowym | 30 min |
| 6 | DataHub: katalog, schematy i lineage | 45 min |
| 7 | Monitoring batchowy i symulacja driftu | 35 min |
| 8 | Odporność, restart i diagnostyka | 35 min |
| 9 | Scenariusz końcowy i pytania audytowe | 30 min |

Pełna wersja zajmuje około jednego dnia z przerwami. Dla krótkiego demo warto
wybrać moduły 0, 2, 3, 4 i 6.

## Stan początkowy

Polecenia administracyjne wykonuj w PowerShellu z katalogu `docker-images-ml`.
Kod Pythona można uruchamiać jako komórki w JupyterLab albo w terminalu
JupyterLab poleceniem `python`.

Uruchom stos:

```powershell
docker compose -f compose.demo.yaml up --build -d
docker compose -f compose.demo.yaml ps -a
```

Otwórz strony:

| System | Adres | Dane lokalne |
|---|---|---|
| JupyterLab | <http://localhost:8888> | token `torii-local-dev` |
| MLflow | <http://localhost:5000> | brak logowania |
| MinIO | <http://localhost:9001> | `minioadmin` / `minioadmin` |
| DataHub | <http://localhost:9002> | `datahub` / `datahub` |

Nie używaj polecenia `docker compose down -v` podczas warsztatów. Parametr `-v`
usuwa wolumeny wraz z eksperymentami, modelami, danymi i notebookami.

---

## Moduł 0 — orientacja w architekturze

### Cel

Zrozumieć, która usługa odpowiada za obliczenia, a która przechowuje stan.

### Scenariusz

1. W wyniku `docker compose ... ps -a` znajdź kontenery `workspace`, `mlflow`,
   `minio`, `postgres`, `datahub-gms`, `mysql`, `search`, `broker` i
   `schema-registry`.
2. Zwróć uwagę, że tylko JupyterLab, MLflow, MinIO i DataHub wystawiają porty na
   komputerze użytkownika.
3. Kontenery `create-bucket` i `datahub-system-update` powinny mieć status
   `Exited (0)`. Są to poprawnie zakończone zadania inicjalizacyjne, nie awarie.
4. Utwórz w JupyterLab plik `reports/workshop.txt`, a potem zrestartuj tylko
   workspace:

```powershell
docker compose -f compose.demo.yaml restart workspace
```

5. Po ponownym otwarciu JupyterLab sprawdź, czy plik nadal istnieje.

### Co należy zapamiętać

- JupyterLab jest interfejsem pracy, a nie magazynem metadanych ani serwerem
  produkcyjnej predykcji.
- PostgreSQL przechowuje metadane MLflow, MinIO przechowuje dane i artefakty.
- DataHub korzysta z MySQL, OpenSearch, Kafka i Schema Registry.
- Kod użytkownika przeżywa wymianę kontenera dzięki wolumenowi `/workspace`.

### Kryterium zaliczenia

Wszystkie usługi są dostępne, a plik użytkownika przetrwał restart workspace.

---

## Moduł 1 — dane i wersjonowanie w MinIO

### Cel

Zobaczyć, gdzie przechowywane są dane oraz w jaki sposób hash zawartości tworzy
niezmienny identyfikator wersji.

### Ćwiczenie

Uruchom w JupyterLab:

```python
from torii_project.automl.mvp import prepare_data

processed, manifest = prepare_data()
manifest
```

Sprawdź w zwróconym manifeście:

- `source` — logiczne pochodzenie danych;
- `raw_uri` oraz `processed_uri` — fizyczne lokalizacje;
- `raw_sha256` i `processed_sha256` — hashe zawartości;
- `rows`, `columns`, `null_cells` i `target_values`;
- listę `transformations`.

Wyświetl próbkę:

```python
processed.head()
```

Następnie otwórz MinIO i przejdź do bucketa `automl-data`. Powinny istnieć:

```text
raw/breast-cancer/sha256=.../data.csv
processed/breast-cancer/sha256=.../data.parquet
processed/breast-cancer/sha256=.../manifest.json
```

Uruchom `prepare_data()` ponownie. URI powinny pozostać takie same, ponieważ
identyczna zawartość daje ten sam hash i tę samą ścieżkę.

### Pytania kontrolne

1. Czy nazwa pliku `latest.csv` pozwoliłaby odtworzyć historyczny trening?
2. Co stanie się z hashem po zmianie jednej wartości?
3. Dlaczego metadane pliku są w manifeście, a sam plik w object storage?

### Kryterium zaliczenia

Uczestnik potrafi wskazać konkretny snapshot raw, snapshot processed oraz
manifest opisujący ich relację.

---

## Moduł 2 — walidacja i transformacje

### Cel

Pokazać, że trening nie powinien rozpocząć się na danych, które nie spełniają
kontraktu.

### Scenariusz poprawny

Pipeline sprawdza:

- typy kolumn;
- brak wartości `null`;
- unikalność `row_id`;
- wartości targetu ograniczone do `0` i `1`;
- kompletność oczekiwanych kolumn.

Po walidacji normalizuje nazwy kolumn do `snake_case`, usuwa duplikaty po
`row_id`, sortuje dane deterministycznie i zapisuje Parquet.

### Scenariusz błędnych danych

Wykonaj w nowej komórce:

```python
import pandera.pandas as pa
from pandera import Check

broken = processed.copy()
broken.loc[0, "is_benign"] = 7

target_contract = pa.DataFrameSchema(
    {
        "is_benign": pa.Column(
            int,
            Check.isin([0, 1]),
            nullable=False,
            coerce=True,
        )
    },
    strict=False,
)

try:
    target_contract.validate(broken, lazy=True)
except pa.errors.SchemaErrors as error:
    display(error.failure_cases)
```

Oczekiwany rezultat: walidacja pokazuje wartość `7` i wskazuje naruszoną regułę.
Napraw wartość i wykonaj walidację ponownie:

```python
broken.loc[0, "is_benign"] = 1
validated = target_contract.validate(broken, lazy=True)
print(f"validated rows: {len(validated)}")
```

### Eksperyment dodatkowy

Powtórz ćwiczenie dla:

- wartości `None` w kolumnie cechy;
- zduplikowanego `row_id`;
- brakującej kolumny;
- tekstu wpisanego do kolumny numerycznej.

### Dyskusja

Transformacja nie jest „zapisywana przez MLflow” jako wykonywalny kod. Kod
transformacji znajduje się w repozytorium, jej parametry i opis trafiają do
MLflow, wynik do MinIO, a relacja pomiędzy wejściem i wyjściem do DataHub. W
produkcyjnym rozwiązaniu należy dodatkowo zapisać commit Git i identyfikator
obrazu kontenera.

### Kryterium zaliczenia

Niepoprawny target zostaje zatrzymany przed treningiem, a uczestnik umie znaleźć
opis transformacji i wynikowy snapshot.

---

## Moduł 3 — AutoML i MLflow Tracking

### Cel

Uruchomić kompletny eksperyment i porównać kandydatów wygenerowanych przez
AutoGluon.

### Ćwiczenie podstawowe

W terminalu JupyterLab uruchom krótszy przebieg:

```bash
python -m torii_project.automl.mvp 60 --skip-catalog
```

AutoGluon trenuje między innymi LightGBM, Random Forest, Extra Trees, CatBoost i
sieć neuronową, a następnie może zbudować ważony ensemble. Po zakończeniu zapisz
z terminala:

- `run_id`;
- `registered_version`;
- `processed_uri`;
- `predictions_uri`.

W MLflow otwórz eksperyment `automl-end-to-end-mvp` i przebieg
`autogluon-candidate-training`. Znajdź:

- parametry `preset`, `time_limit_seconds`, `target` i `metric`;
- metryki rozpoczynające się od `test_`;
- metryki jakości danych;
- dataset wejściowy;
- `data/manifest.json`;
- `environment.json`;
- `reports/mvp_leaderboard.csv`;
- zapisany model.

### Porównanie eksperymentów

Uruchom drugi przebieg z innym budżetem, na przykład 30 sekund:

```bash
python -m torii_project.automl.mvp 30 --skip-catalog
```

Zaznacz oba przebiegi w MLflow i wybierz porównanie. Oceń:

1. Czy wybrany model lub ensemble się zmienił?
2. Czy zmieniły się metryki testowe?
3. Czy oba przebiegi wykorzystały ten sam hash danych?
4. Czy dodatkowy czas przyniósł mierzalną poprawę?

Te same dane można sprawdzić przez API:

```python
from mlflow import MlflowClient

client = MlflowClient()
experiment = client.get_experiment_by_name("automl-end-to-end-mvp")
runs = client.search_runs(
    [experiment.experiment_id],
    order_by=["attributes.start_time DESC"],
    max_results=10,
)

[
    {
        "run_id": run.info.run_id,
        "name": run.data.tags.get("mlflow.runName"),
        "roc_auc": run.data.metrics.get("test_roc_auc"),
        "snapshot": run.data.params.get("data_snapshot_sha256"),
    }
    for run in runs
]
```

### Kryterium zaliczenia

Uczestnik potrafi porównać dwa przebiegi oraz powiązać wynik z wersją danych,
parametrami i środowiskiem.

---

## Moduł 4 — Model Registry, promocja i rollback

### Cel

Oddzielić techniczną wersję modelu od stabilnej nazwy używanej przez odbiorców.

### Inspekcja rejestru

W MLflow przejdź do **Models** i otwórz
`automl-breast-cancer-classifier`. Pipeline po każdym treningu tworzy nową
wersję i przesuwa alias `candidate`.

Sprawdź to przez API:

```python
from mlflow import MlflowClient

MODEL_NAME = "automl-breast-cancer-classifier"
client = MlflowClient()

versions = client.search_model_versions(f"name='{MODEL_NAME}'")
[(version.version, version.run_id, version.status) for version in versions]
```

```python
candidate = client.get_model_version_by_alias(MODEL_NAME, "candidate")
print(candidate.version, candidate.run_id, candidate.status)
```

### Symulacja promocji

Po zaakceptowaniu metryk nadaj bieżącej wersji alias `champion`:

```python
client.set_registered_model_alias(
    MODEL_NAME,
    "champion",
    candidate.version,
)
```

W realnym systemie ten krok powinien być wykonywany przez kontrolowany proces
po przejściu testów jakości, bezpieczeństwa i zgodności, a nie dowolną komórkę
notebooka.

### Symulacja rollbacku

Wybierz wcześniejszą wersję z listy i przestaw tylko alias:

```python
previous_version = sorted(
    (int(version.version) for version in versions),
    reverse=True,
)[1]

client.set_registered_model_alias(
    MODEL_NAME,
    "champion",
    str(previous_version),
)
```

Artefakty nie są kopiowane ani trenowane ponownie. Odbiorca aliasu `champion`
zacznie pobierać wskazaną wcześniejszą wersję.

### Pytania kontrolne

1. Dlaczego aplikacja nie powinna ładować po prostu „najnowszej wersji”?
2. Kto powinien mieć prawo przesuwania `champion`?
3. Jakie testy powinny stanowić promotion gate?

### Kryterium zaliczenia

Uczestnik potrafi promować i cofnąć model bez ponownego treningu.

---

## Moduł 5 — niezależna predykcja

### Cel

Udowodnić, że model nie zależy od obiektu pozostawionego w pamięci notebooka.

Zrestartuj kernel JupyterLab, a następnie wykonaj:

```python
import mlflow.pyfunc

from torii_project.automl.mvp import prepare_data

MODEL_NAME = "automl-breast-cancer-classifier"
processed, manifest = prepare_data()
features = processed.drop(columns=["row_id", "is_benign"])

model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@candidate")
predictions = model.predict(features.head(10))
predictions
```

Sprawdź, czy wynik ma 10 wierszy i kolumnę `prediction`. Następnie odszukaj w
MinIO wynik wcześniejszego pełnego przebiegu:

```text
predictions/breast-cancer/run_id=.../predictions.parquet
```

### Dyskusja

To nadal batch inference, a nie produkcyjny endpoint. Produkcyjne serwowanie
wymagałoby osobnej usługi wdrożeniowej, skalowania, health-checków, limitów,
autoryzacji i obserwowalności.

### Kryterium zaliczenia

Model daje predykcje po restarcie kernela i jest ładowany wyłącznie przez alias
MLflow Registry.

---

## Moduł 6 — DataHub: katalog i lineage

### Cel

Odpowiedzieć na pytania: „jakie dane istnieją?”, „kto ich użył?” i „z czego
powstał wynik?”.

Jeżeli ostatni przebieg pomijał katalog, uruchom pełny scenariusz:

```bash
python -m torii_project.automl.mvp 60
```

W DataHub wyszukaj kolejno:

- `breast-cancer`;
- `automl-breast-cancer-classifier`;
- fragment hasha z `processed_uri`;
- `predictions.parquet`.

### Inspekcja danych

Otwórz dataset processed utworzony przez konektor S3. Sprawdź:

1. pełną ścieżkę w MinIO;
2. schemat i nazwy kolumn;
3. opis datasetu;
4. właściwość z identyfikatorem treningu MLflow;
5. zakładkę **Lineage** — raw powinien być upstreamem.

Następnie otwórz dataset predykcji. Jego upstreamem powinien być processed.

### Inspekcja modeli

Otwórz grupę modelu i wersje importowane z MLflow. Sprawdź relację między:

- eksperymentem;
- przebiegiem treningowym;
- wejściowym datasetem;
- zarejestrowaną wersją modelu.

### Ręczne ponowienie konektorów

W terminalu JupyterLab można ponowić ingestie bez treningu:

```bash
datahub ingest -c config/datahub/minio.yml
/opt/datahub-mlflow-venv/bin/datahub ingest -c config/datahub/mlflow.yml
```

Konektor MLflow ma osobne środowisko, ponieważ jego obsługiwana wersja klienta
MLflow jest starsza niż klient używany przez pipeline treningowy. Oba klienty
komunikują się z tym samym serwerem.

### Kryterium zaliczenia

Uczestnik potrafi przejść w katalogu od predykcji do przetworzonych i surowych
danych oraz odnaleźć model i przebieg treningowy.

---

## Moduł 7 — monitoring batchowy i symulowany drift

### Cel

Pokazać podstawowy kontrakt monitoringu przy braku etykiet rzeczywistych oraz
jasno oddzielić go od kompletnej platformy observability.

W JupyterLab wykonaj:

```python
import mlflow
import mlflow.pyfunc

from torii_project.automl.mvp import prepare_data

MODEL_NAME = "automl-breast-cancer-classifier"
processed, manifest = prepare_data()
features = processed.drop(columns=["row_id", "is_benign"])

model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@candidate")
baseline_predictions = model.predict(features)["prediction"]

shifted = features.copy()
shifted["mean_radius"] = shifted["mean_radius"] * 1.25
shifted_predictions = model.predict(shifted)["prediction"]

metrics = {
    "mean_radius_relative_shift": float(
        shifted["mean_radius"].mean() / features["mean_radius"].mean() - 1
    ),
    "baseline_positive_rate": float(baseline_predictions.mean()),
    "shifted_positive_rate": float(shifted_predictions.mean()),
    "prediction_rate_delta": float(
        shifted_predictions.mean() - baseline_predictions.mean()
    ),
}

mlflow.set_experiment("automl-end-to-end-mvp")
with mlflow.start_run(run_name="monitoring-simulated-drift"):
    mlflow.log_params(
        {
            "model_alias": "candidate",
            "source_snapshot": manifest["processed_uri"],
            "scenario": "mean_radius_x_1.25",
        }
    )
    mlflow.log_metrics(metrics)

metrics
```

W MLflow znajdź `monitoring-simulated-drift` i porównaj rozkład predykcji przed
i po zmianie cechy.

### Interpretacja

- Zmiana rozkładu cech oznacza data drift, ale nie dowodzi pogorszenia modelu.
- Bez nowych etykiet nie można policzyć rzeczywistego ROC AUC ani błędu modelu.
- W produkcji metryki powinny być liczone cyklicznie, mieć progi, alerty i
  przypisanego właściciela.
- To MVP przechowuje wyniki monitoringu w MLflow, ale nie ma jeszcze schedulera,
  alert managera ani dedykowanego silnika typu Evidently.

### Kryterium zaliczenia

W MLflow istnieje osobny przebieg monitoringowy z miarą przesunięcia cechy i
zmiany udziału pozytywnych predykcji.

---

## Moduł 8 — odporność i diagnostyka

### Cel

Przećwiczyć różnicę pomiędzy statusem kontenera, dostępnością API i poprawnością
całego przepływu.

### Scenariusz A — niedostępny MLflow

Zatrzymaj MLflow:

```powershell
docker compose -f compose.demo.yaml stop mlflow
```

Spróbuj w JupyterLab pobrać alias modelu. Oczekiwany jest błąd połączenia, a nie
ciche użycie lokalnej kopii. Przywróć usługę:

```powershell
docker compose -f compose.demo.yaml start mlflow
```

Sprawdź <http://localhost:5000/health>.

### Scenariusz B — niedostępne object storage

Zatrzymaj MinIO i wykonaj `prepare_data()`. Zapis snapshotu powinien zakończyć
się błędem, więc trening nie powinien ruszyć dalej.

```powershell
docker compose -f compose.demo.yaml stop minio
docker compose -f compose.demo.yaml start minio
```

Po starcie MinIO odczekaj kilka sekund i ponów operację.

### Scenariusz C — restart całego stosu bez utraty danych

```powershell
docker compose -f compose.demo.yaml down
docker compose -f compose.demo.yaml up -d
```

Po starcie potwierdź, że istnieją wcześniejsze:

- eksperymenty i wersje modeli w MLflow;
- obiekty w MinIO;
- notebooki w workspace;
- encje w DataHub.

### Diagnostyka baz

Liczba rekordów MLflow w PostgreSQL:

```powershell
docker compose -f compose.demo.yaml exec -T postgres `
  psql -U mlflow -d mlflow -Atc `
  "select 'runs='||count(*) from runs union all select 'model_versions='||count(*) from model_versions;"
```

Liczba encji DataHub w MySQL:

```powershell
docker compose -f compose.demo.yaml exec -T mysql `
  mysql -uroot -pdatahub datahub -N -e `
  "select count(distinct urn) from metadata_aspect_v2;"
```

Nie zmieniaj ręcznie danych w tych bazach. Polecenia służą wyłącznie do
diagnostyki; normalna komunikacja odbywa się przez API MLflow i DataHub.

### Kryterium zaliczenia

Uczestnik potrafi rozpoznać błąd zależności, przywrócić usługę i potwierdzić
trwałość stanu po pełnym restarcie.

---

## Moduł 9 — scenariusz końcowy

### Zadanie

Wyobraź sobie, że audytor pyta, skąd pochodzi predykcja dla konkretnego batcha.
Uruchom pełny pipeline i przygotuj odpowiedzi bez zaglądania do pamięci procesu
treningowego:

```bash
python -m torii_project.automl.mvp 60
```

### Lista dowodów

| Pytanie | Gdzie znaleźć odpowiedź |
|---|---|
| Z jakiego źródła pochodzą dane? | manifest oraz DataHub |
| Jaka dokładnie wersja danych była użyta? | URI i SHA-256 w MinIO/MLflow |
| Jakie reguły jakości przeszły dane? | `data/manifest.json` w przebiegu MLflow |
| Jakie transformacje wykonano? | manifest i kod `torii_project.automl.mvp` |
| Jakie algorytmy porównano? | leaderboard AutoGluon w MLflow |
| Jakie były parametry i wersje bibliotek? | params oraz `environment.json` |
| Który model został zaakceptowany? | wersja i alias w MLflow Registry |
| Czy model można pobrać w nowym procesie? | `models:/...@candidate` i moduł 5 |
| Gdzie zapisano predykcje? | `predictions_uri` oraz MinIO |
| Z czego powstały predykcje? | zakładka Lineage w DataHub |

### Kryterium zaliczenia

Każda odpowiedź wskazuje trwały artefakt lub metadane w systemie, a nie tylko
wydruk z notebooka.

---

## Co ten stos pokazuje, a czego jeszcze nie ma

### Pokazane w MVP

- niezmienne snapshoty danych i manifest transformacji;
- data quality gate;
- automatyczne porównanie modeli;
- śledzenie eksperymentów i środowiska;
- wersjonowanie, aliasowanie, promocja i rollback modelu;
- odtwarzalna predykcja batchowa;
- katalog danych, schematy, modele i lineage;
- podstawowe zapisywanie metryk monitoringowych;
- trwałość danych po wymianie kontenerów.

### Następny etap platformy

- orkiestracja i harmonogramy, np. Argo Workflows lub Kubeflow Pipelines;
- automatyczne promotion gates i CI/CD modeli;
- produkcyjny model serving;
- cykliczny monitoring jakości, driftu, opóźnień i kosztu wraz z alertami;
- feature store, jeżeli pojawi się potrzeba współdzielenia cech online/offline;
- RBAC, SSO, sekrety, polityki retencji, backup i disaster recovery;
- zarządzane odpowiedniki PostgreSQL, object storage, Kafka i OpenSearch w
  AWS/GCP;
- rejestrowanie commita Git, digestu obrazu i tożsamości wykonującego jako
  obowiązkowych elementów każdego produkcyjnego przebiegu.

## Skrócony scenariusz demonstracyjny — 20 minut

Jeżeli trzeba pokazać MVP interesariuszom:

1. Pokaż architekturę i działające kontenery.
2. Wprowadź błędny target i pokaż odrzucenie przez Pandera.
3. Uruchom pełny pipeline z budżetem 30–60 sekund.
4. W MLflow pokaż manifest, leaderboard, metryki i alias `candidate`.
5. W MinIO pokaż raw, processed, manifest i predictions.
6. W DataHub przejdź po lineage `raw -> processed -> predictions`.
7. Załaduj model po aliasie po restarcie kernela.
8. Zakończ listą funkcji, których świadomie nie obejmuje MVP.
