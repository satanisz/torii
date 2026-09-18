# Architektura docelowa — propozycja

Status: Draft. To projekt granic, nie dokumentacja wdrożonego backendu.
Architekturę istniejących obrazów opisuje [starszy dokument](../architecture.md).

## Podejście

Pozostajemy w repozytorium Torii. Proponujemy **modularny monolit sterowania**
z osobno uruchamianym frontendem i izolowanymi workerami. Moduły domenowe mają
kontrakty i właścicieli; nie wymagają osobnych mikroserwisów ani repozytoriów.
Wydzielenie usługi wymaga udokumentowanej potrzeby skali, izolacji lub organizacji.

Płaszczyzna sterowania odpowiada za użytkowników, definicje, wersje, uprawnienia,
plan wykonania i wydania. Płaszczyzna wykonawcza uruchamia kod użytkownika na
przyznanych zasobach. API nigdy nie importuje modelu ani transformacji użytkownika
w swoim procesie, także przy podglądzie metadanych lub walidacji.

## Komponenty i właściciele danych

| Komponent | Odpowiedzialność | Proponowana implementacja |
|---|---|---|
| Web | Katalog, Flow, eksperymenty, wyniki, Git i wydania | React/TypeScript; React Flow jako kandydat edytora grafu |
| API i domena | Walidacja, ACL, transakcje, wersje, polityki i publikacja | Python/FastAPI; jawne moduły domenowe |
| Baza platformy | Tożsamości lokalne, grants, wersje, wykonania, approvals, outbox | PostgreSQL, osobna baza/rola od MLflow |
| Uwierzytelnianie | Zewnętrzna tożsamość, sesje i konta usługowe | OIDC, lokalny testowy IdP; firmowy dostawca później |
| Artifact store | Snapshoty, pakiety modeli, raporty i paczki źródeł | Interfejs S3; MinIO do dev, firmowy magazyn po weryfikacji |
| Execution adapter | Dispatch, próby, heartbeat, cancel, reconcile | Decyzja po próbie Dagster kontra prosty runner zadaniowy |
| Worker | Izolowane wykonanie konkretnego planu | Kontener per zadanie; Docker dev, docelowy scheduler firmy |
| MLflow adapter | Tracking, metryki i kompatybilne modele | Obecny MLflow za kontrolowaną granicą dostępu |
| Catalog adapter | Projekcja katalogu i lineage | DataHub opcjonalny; nie wymagany dla transakcji Torii |
| Git adapter/SDK/CLI | Working copies, walidacja manifestów, lokalny run i synchronizacja | Zwykłe repozytoria, paczka Python, wspólne kontrakty |

MLflow jest autorytatywny dla swoich metryk/parametrów i identyfikatorów runów;
Torii dla planu wykonania, powiązań i decyzji o wydaniu. Mapowanie ma unikatowe
klucze i retry bez duplikacji. Zakończenie obliczeń i zakończenie publikacji
metryk/katalogu są osobnymi stanami. Wydanie nie przechodzi bramki jakości
przed uzgodnionym, kompletnym zestawem dowodów.

DataHub jest projekcją obiektów Torii i może dodawać katalog zewnętrzny.
Własność pól ustalamy jawnie: Torii nie nadpisuje automatycznie klasyfikacji
zarządzanej przez firmowy katalog. Awaria DataHub nie blokuje utrwalenia Runu;
outbox, retry i reconciliation uzupełniają projekcję po odzyskaniu usługi.
Jeśli projekcja jest nieaktualna, UI pokazuje ten stan.

## Granice bezpieczeństwa

Przeglądarka/SDK trafiają do uwierzytelnionego API. API ustala aktora i projekt
na podstawie tożsamości oraz grantów, nie ufa samemu `project_id` w payloadzie.
Wywołanie wykonawcze otrzymuje zatwierdzony plan z przypiętymi wersjami.
Worker dostaje krótkotrwałe uprawnienia do konkretnych wejść/wyjść, bez
poświadczeń administratora magazynu i bez dostępu do bazy sterowania.

Workspace/Jupyter to również środowisko wykonywania kodu: osobne per użytkownik,
z limitami, kontrolą sieci i audytem. Nie jest zaufaną częścią API. Sam kontener
nie wystarcza jako granica dla wrogiego kodu; docelowe profile izolacji muszą
przejść threat modeling i testy na wybranej infrastrukturze.

Bezpośredni dostęp do MLflow, DataHub, S3 i ich artefaktów nie może omijać ACL
Torii. Potrzebny jest sprawdzony adapter/proxy albo równoważna polityka usług.
W szczególności token wspólnego MLflow lub adres artefaktu nie daje prawa do
wszystkich projektów. Zgodność MLflow SDK i autoryzacji jest decyzją blokującą S4.
Nie zakładamy, że samo ukrycie portów rozwiązuje autoryzację per obiekt.

## Semantyka wykonania i awarii

- Run oddzielony od prób. Planowane stany: queued, starting, running,
  cancel_requested, succeeded, failed, cancelled. Stany terminalne nie są
  cofane; ponowienie tworzy nową próbę według polityki.
- Dispatch i zdarzenia traktujemy jako co najmniej jednokrotne. Idempotency key,
  lease z fencing token i unikatowe klucze publikacji chronią przed podwójnym
  opublikowaniem wyniku przez starego workera.
- Brak heartbeat uruchamia reconcile z backendem, nie automatyczne uznanie,
  że obliczenia bezpiecznie zakończono albo można je bez skutków ponowić.
- Zapis do systemu zewnętrznego wymaga kontraktu idempotencji/kompensacji;
  pierwszy zakres transformacji publikuje do zarządzanego magazynu. Odczyt SQL
  jest read-only. „Exactly once” nie jest domyślną obietnicą.
- Outbox w transakcji bazy eliminuje zgubienie intencji publikacji. Operacje
  w magazynie, Git i MLflow mają własne potwierdzenia i proces naprawy.
- Logi i cache są objęte prawami projektu. Cache uwzględnia komplet wejść,
  runtime i parametry; cache hit nie omija bieżącej autoryzacji.

Dokładne przejścia stanów, okna retry i zasady cancel zostaną kontraktami
SPEC-S2, nie szczegółami dopowiedzianymi przez implementującego workera.

## Jeden interfejs — zadania użytkownika

| Ekran | Co można zrobić | Stały kontekst |
|---|---|---|
| Projekty/katalog | Znaleźć udostępnione zasoby, właściciela i stan | Organizacja, projekt, role |
| Obiekt | Odczytać definicję, wersje, jakość, schema, preview, dostęp i użycia | Trwałe ID i wybrana wersja |
| Flow | Połączyć porty, wybrać wersje/parametry, zwalidować i uruchomić | Gałąź/draft, środowisko, status walidacji |
| Run | Śledzić kroki, próby, logi, wejścia/wyjścia; retry/cancel/replay | Run ID, manifest i uprawniony aktor |
| Eksperymenty/modele | Porównać wyniki na wspólnym protokole, obejrzeć pakiet modelu | Wersje danych/modelu i protokół |
| Analizy | Obejrzeć EDA/XAI/raport, przejść do jego wejść | Metoda, wersje, ostrzeżenia i dostęp |
| Zmiany/Git | Obejrzeć diff, walidację, konflikt, commit/push | Working copy użytkownika i gałąź |
| Wydania | Przejrzeć pakiet i dowody, zatwierdzić, wdrożyć, cofnąć | Digest, autor/recenzent/operator, środowisko |
| Administracja/audyt | Członkostwo, połączenia, polityki, zdarzenia | Zakres administracyjny bez domyślnego prawa do danych |

Każdy ekran projektujemy także dla braku danych, braku dostępu, ładowania,
częściowej awarii i konfliktu. Widok tabelaryczny/listowy i klawiatura muszą
umożliwiać pracę bez przeciągania węzłów. Ostrzeżenie PROD wymaga również
sprawdzenia serwerowego, nie tylko koloru przycisku.

Jupyter jest pierwszą integracją edytorską, nie projektem własnego IDE.
Zaawansowany interfejs MLflow/DataHub może być linkiem diagnostycznym z SSO,
lecz codzienna ścieżka pracy musi działać w Torii bez przełączania aplikacji.

## Planowane rozmieszczenie kodu

Nazwy poniżej są propozycją, nie istniejącymi katalogami:

- `apps/api/`, `apps/web/`: procesy API i interfejs;
- `packages/domain/`, `packages/sdk/`, `packages/contracts/`: domena i kontrakty;
- `adapters/`: storage, Git, MLflow, katalog, konektory i wykonanie;
- `deploy/`: konfiguracje dev/test i docelowego wdrożenia;
- `specs/`, `adr/`, `tests/`: specyfikacje, decyzje i dowody w repozytorium;
- obecne `scaffold/`, `docker/`, `mlflow/`: zachowane do osobnej migracji.

Nie przenosimy teraz istniejących plików. Projekty analityczne generowane dla
użytkowników mają własne `src/`, `notebooks/`, `tests/`, deklaracje katalogu,
Flow i lock. API platformy nie importuje ich pakietów.

## Uzasadnienie inspiracji

Rozdzielenie projektowania i uruchamiania wydanego Flow jest inspiracją z
[Dataiku deployments](https://doc.dataiku.com/dss/latest/deployment/index.html).
Do próby orkiestratora kwalifikujemy Dagster ze względu na model
[assets](https://docs.dagster.io/guides/build/assets), nie uznajemy go z góry za
właściciela całej domeny Torii. Adapter zgodnych modeli wykorzystuje możliwości
[MLflow PythonModel](https://mlflow.org/docs/latest/ml/model/python_model/).
Wymienione produkty nie stanowią dowodu spełnienia wymagań bezpieczeństwa Torii.
