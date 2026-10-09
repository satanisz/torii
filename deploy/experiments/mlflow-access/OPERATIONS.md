# Warsztat modeli — lokalna próba MLflow

[SPEC-0020](../../../specs/0020-model-workbench-trial/README.md), EXP-03a.
Syntetyczne dane; ten katalog nie zastępuje enterprise API ani UI Torii.

## Uruchomienie

Z katalogu repozytorium `torii`, PowerShell 7 z dostępem do Docker Desktop:

```powershell
./deploy/experiments/mlflow-access/trial.ps1 -Action provision
# Zapisz wypisany RunId, używaj go w kolejnych poleceniach.
$trialId = 'TU_RUN_ID'
./deploy/experiments/mlflow-access/trial.ps1 -Action check -RunId $trialId
./deploy/experiments/mlflow-access/trial.ps1 -Action build -RunId $trialId
./deploy/experiments/mlflow-access/trial.ps1 -Action up -RunId $trialId
./deploy/experiments/mlflow-access/trial.ps1 -Action test -RunId $trialId
./deploy/experiments/mlflow-access/trial.ps1 -Action status -RunId $trialId
```

Port domyślny: `http://127.0.0.1:18500`; inny wybiera się tylko przy provision
parametrem `-Port`. Login użytkownika treningowego: `analyst_a`; hasło znajduje
się lokalnie w `deploy/experiments/mlflow-access/.local/<RunId>/secrets/user_a`.
Nie kopiuj sekretu do repo, czatu
lub artefaktów. `analyst_b` używa `user_b`, admin `admin_password` tylko do testów.
Brak automatycznej rotacji i domyślnych haseł. Up ponownie weryfikuje tożsamości.

`test` uruchamia kolejno dwa identyczne treningi i jeden na zmienionych danych,
restartuje wyłącznie trzy usługi danych/MLflow tej próby, pobiera stare artefakty i wykonuje
macierz ACL. `train` wykonuje dodatkowy zwykły trening. `inspect` sprawdza
konfigurację/runtime i zapisuje raport limitów, obrazów i montowań bez sekretów.
JSON raportów jest w `deploy/experiments/mlflow-access/.local/<RunId>/results/`.
Macierz może dać NO-GO dla
integracji enterprise mimo poprawnego treningu. Nie ukrywamy FAIL/NOT TESTED.

```powershell
./deploy/experiments/mlflow-access/trial.ps1 -Action train -RunId $trialId
./deploy/experiments/mlflow-access/trial.ps1 -Action inspect -RunId $trialId
./deploy/experiments/mlflow-access/trial.ps1 -Action stop -RunId $trialId
```

Stop zachowuje wolumeny i sekrety. Wróć przez up z tym samym RunId. Nie uruchamiaj
gołego `docker compose up` z repo: root `.env` wskazuje osobny legacy stos.
Harness nie oferuje kasowania danych i nie zatrzymuje innych instalacji.
Blokada operacji i kontrola aktywnych instancji pozwalają uruchomić jeden warsztat
oraz jeden job naraz. Ręczne komendy omijające harness nie są objęte tą blokadą.

## Zależności i granice

Bazy i storage mają własne nowe wolumeny. Sieci workera/MLflow/DB/S3 są internal;
tylko Caddy publikuje loopback ze stałym upstream MLflow. Gateway ma osobną sieć
ingress, bez sekretów i bez otwartego proxy. Maksimum dla czterech usług i jednego
joba: 4 CPU / 3712 MiB.
Kod w obrazie, biblioteki w `requirements.lock` z hashami. Obrazy bazowe mają
digesty w Dockerfile/Compose. Raport `isolation.json` zapisuje rzeczywiste image ID.

Powtórne rozwiązanie zależności jest świadomą zmianą do review:

```powershell
uv pip compile --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --generate-hashes --output-file requirements.lock requirements.in
```

Polecenie powyżej uruchamia się w tym katalogu; zwykły build używa gotowego locka.
Przykład treningu jest w `train.py`. Wersjonowane pliki i manifesty są artefaktami
MLflow; joblib ładuje wyłącznie własny model po sprawdzeniu jego digestu w workerze.

## Odbiór przez autora modelu

W MLflow otwórz eksperyment `finance-forecast`, porównaj runy `dummy` i `ridge`,
sprawdź parametry oraz metryki, a następnie artefakty `manifest.json`,
`predictions.csv`, `model.joblib` i `code/train.py`. Każdy trening zapisuje cztery
runy: generację danych, transformację/split oraz dwa modele. Relacje między nimi
są w manifestach. Trzy treningi testowe dają 12 ukończonych runów.

Akcja `train` uruchamia ten konkretny worker. Zmiana implementacji modelu wymaga
edycji `train.py` i ponownego build/up — uniwersalny dispatcher definicji Torii
będzie osobnym przyrostem. Lokalne image ID nie zastępuje archiwum obrazów OCI.

Natywne konta basic-auth, lokalny HTTP, pojedynczy węzeł S3, brak zatwierdzeń
i audytu Torii ograniczają ten profil do syntetycznej próby. Eksperymenty A/B
nie są jeszcze projektami Torii. Registry/alias nie są release ani immutable snapshot.
Trwałość po restarcie nie jest dowodem backup/restore ani odporności na awarie hosta.

Wyniki: [evidence SPEC-0020](../../../specs/0020-model-workbench-trial/evidence.md).
