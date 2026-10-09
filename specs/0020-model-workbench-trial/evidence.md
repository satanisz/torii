# SPEC-0020 — dowody EXP-03a

2026-10-10 Europe/Warsaw (2026-10-09 UTC), lokalny Docker Desktop Linux amd64.
Baza Git przed implementacją: `a2b1cc2`; przyrost przygotowany oddzielnie od
wcześniejszego demo i planu. RunId `20261010ab01`, Compose project
`torii-exp03-20261010ab01`. Dane i konta wyłącznie syntetyczne.

## Wynik

Warsztat modeli działa. Trzy treningi zapisały 12 ukończonych runów: dane,
transformację/split i dwa modele. Dwie próby z seed 42 mają identyczne predykcje
i metryki oraz różne run ID; seed 43 zmienia digest danych. Po restarcie
MLflow/PostgreSQL/S3 pobrano i zweryfikowano 36 wcześniejszych artefaktów.

Macierz MLflow 3.14.0: **136 PASS, 0 FAIL, 1 NOT TESTED**. To wynik wyłącznie
przetestowanego podzbioru API. NOT TESTED dotyczy kwalifikowanego, niezależnego
audytu autoryzacji. Decyzja dla bezpośredniej integracji enterprise: **NO-GO**.
Brak audytu/SSO Torii i pełnego pokrycia API nie jest zastąpiony raportem klienta.

Gateway loopback: anonimowe API 401, konto A 200. Cztery usługi + jeden job:
4 CPU / 3712 MiB limitów. Worker ma wyłącznie sekret A i wewnętrzną sieć API.
DB/S3/MLflow nie publikują portów. Caddy nie ma sekretów ani trwałych danych.

## Polecenia i wyniki

Komendy wykonywano z repozytorium `torii`; `-RunId 20261010ab01` przy każdej
akcji harnessu poza testami Python. Dostęp do hostowego Dockera wymagał
zaakceptowanej eskalacji poza sandbox Windows.

| Sprawdzenie | Wynik |
|---|---|
| `trial.ps1 -Action provision/check/build/up` | PASS; własne zasoby, brak zmiany root `.env` i legacy |
| `trial.ps1 -Action test` | PASS: bootstrap, trzy treningi, replay, zmiana danych, restart, download i macierz ACL |
| `trial.ps1 -Action inspect` po dodaniu ingress rev0.2 | PASS: konfiguracja i runtime; anonimowe 401 / uwierzytelnione 200 przez host loopback |
| Pełne `stop` → `up` własnej instancji + ponowne verify | PASS: te same konta, ingress 401/200, 36 wcześniejszych artefaktów z poprawnymi digestami |
| `python -m pytest deploy/experiments/mlflow-access/test_train.py -q` w demo venv | 13 PASS: temporal split, brak przyszłych cech, scaler train-only, digest i powtarzalność |
| Ruff check + format | PASS dla 7 plików Python |
| mypy `--follow-imports=skip --ignore-missing-imports --check-untyped-defs` | PASS dla 5 plików wykonawczych; nie jest pełnym typowaniem bibliotek dostawcy |
| `docker exec ...-mlflow-1 uv pip check --system` | 97 pakietów kompatybilnych |
| Odmowa ponownego provision / nieprawidłowego RunId / równoległego train podczas test | PASS; żadna z prób nie rozpoczęła drugiego zadania |
| Kontrola eksportu raportów i `.gitignore` | 9 JSON bez wartości sekretów instancji; `.local` ignorowane |

Treningi i pełna macierz wykonane na rev0.1 kontraktu bazowego; po dodaniu
ingress rev0.2 osobno sprawdzono host API oraz izolację czterech usług. Warstwa
MLflow, skrypty treningowe i zależności pozostały te same. Obrazy OCI indeksu
mogą mieć różne ID po ponownym buildzie z nową atestacją, mimo tego samego
manifestu platformy. Nie utożsamiamy aktualnego tagu z dawnym wykonaniem:
każdy raport treningu zachowuje swój faktycznie użyty image ID.

## Trwałe raporty bez sekretów

- [Macierz API/SDK](evidence/access.json) — wszystkie nazwane przypadki,
  zasoby syntetyczne, dokładne statusy i ograniczenia modelu JSON bez fit.
- [Trening 1](evidence/train-1.json), [trening 2](evidence/train-2.json),
  [zmienione dane](evidence/train-changed.json) — runy, image ID, metryki, digesty.
- [Odtwarzalność](evidence/reproduction.json), [trwałość](evidence/persistence.json).
- [Trwałość po pełnym stop/up](evidence/persistence-after-stop.json).
- [Izolacja i obrazy](evidence/isolation.json), [ingress](evidence/ingress.json),
  [konta bootstrap](evidence/bootstrap.json).

Seed 42: baseline MAE 89,7743 i RMSE 98,4410; Ridge MAE 8,6576 i RMSE 10,5653.
To jednostki syntetycznego generatora, nie wynik walidacji modelu bankowego.
Artefakty wejść/modeli/kodu są w MLflow/S3, nie w Git. Raporty zawierają ich hash
i lokalizację we właściwym runie. Dostępność obrazu w przyszłości wymaga
archiwum OCI; samo image ID nie jest polityką retencji.

## Znalezione i naprawione problemy

- Domyślna allowlista MLflow nie obejmuje `mlflow:5000`; dodano wąską listę.
- Równoległe harnessy mogły przekroczyć budżet; wspólna blokada oraz kontrola
  obcych instancji i pozostałych jobów odmawiają dodatkowego wykonania.
- Początkowe cztery wolumeny SeaweedFS zostały zajęte przez kolekcję domyślną;
  zapis S3 zawiódł. Zwiększono lokalny limit do 16 × 100 MiB, bez resetu danych.
- Lista YAML tmpfs wymagała cytowania opcji z przecinkiem.
- Docker Desktop nie publikował portu internal-only MLflow; rev0.2 dodaje
  Caddy ingress zamiast udostępniać workerowi sieć zewnętrzną.
- Binarka Caddy miała file capability kolidującą z cap_drop ALL; usunięto ją
  podczas builda, zachowując nonroot, read-only i no-new-privileges.

Pierwszy nieudany run pozostaje jako failed; nie usuwano go, aby ukryć błąd.
Ostrzeżenie dostawcy Starlette WSGI deprecation pozostaje jawne. Zmiana tej
integracji wymaga osobnego sprawdzenia nowej wersji MLflow, nie losowego upgrade.

## Review i kwalifikacja

`regulated_examples` niezależnie przyjął spec 0.1 i ingress 0.2 przed kodem,
przejrzał infrastrukturę, worker, ACL harness i ingress; końcowo bez blokerów.
`platform_state` przejrzał instrukcje/architekturę; poprawiono zakres SP-02,
ścieżki i opis lokalnych obrazów. Jest to review agentów, nie audyt człowieka.

AC-01: isolation/ingress/guards. AC-02: train-1. AC-03: reproduction/persistence.
AC-04: 136 przypadków. AC-05: JSON bez fit i jawny NO-GO audytu.
AC-06: instrukcja, raporty, wersje i review. Odbiór dotyczy wykonania badania;
nie nadaje statusu Verified całemu EXP-03, SP-01 ani SP-10.

Nie wykonano kwalifikacji HA/DR/WORM, retencji, pentestu ani pełnego skanu CVE
obrazów. Hash locka i sprawdzenie zgodności pakietów nie dowodzą braku podatności.
Lokalny HTTP/basic-auth oraz brak audytu i integracji ACL Torii ograniczają użycie
do syntetycznego warsztatu. Następna decyzja SP-10A musi zaprojektować wspólną
granicę autoryzacji/audytu albo wydzielone instancje; brak zgody na shared admin token.
