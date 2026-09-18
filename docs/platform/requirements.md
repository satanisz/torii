# Stan wyjściowy i wymagania

Status: Draft. Wymagania są propozycją operacjonalizacji ustaleń użytkownika.
Identyfikatory są trwałe; zmiana znaczenia wymaga historii i przeglądu wpływu.

## Odczyt istniejącego repozytorium

| Obszar | Dowód w kodzie | Wniosek dla planu |
|---|---|---|
| Workspace | `docker/Dockerfile`, `scaffold/` | Zachować jako środowisko i przykład projektu, nie doklejać tam backendu platformy |
| Dane | `prepare_data()` w `scaffold/src/torii_project/automl/mvp.py` | CSV, Parquet, hash i manifest istnieją, ale źródło jest zaszyte w kodzie |
| Trwałość wersji | `_upload_bytes()` w tym samym pliku | `put_object` zapisuje pod kluczem; hash w nazwie nie wymusza niezmienności ani retencji |
| Eksperymenty | `train_and_register()` | Jest MLflow i AutoGluon; nie ma ogólnego kontraktu modelu ani pełnego odcisku kodu/runtime |
| Predykcja | `run_batch_inference()` | Odczytuje zmienny alias `candidate`, mimo otrzymania konkretnej wersji treningu; równoległy trening może zmienić faktyczny model |
| Katalog | `automl/catalog.py` | Publikacja lineage do DataHub; `env="PROD"` jest stałą demonstracji, nie dowodem wdrożenia na produkcję |
| Wykonania | `run_mvp()` | Sekwencja w jednym procesie workspace, bez trwałej kolejki, odzyskiwania i izolacji zadań |
| Bezpieczeństwo | `compose.demo.yaml` | Hasła demonstracyjne, MLflow bez logowania, szerokie klucze magazynu, wyłączona autoryzacja GMS |
| Testy | `tests/`, `scaffold/tests/` | Sprawdzenia obrazów, usług, szablonu i kompatybilności; nie dowodzą izolacji użytkowników |
| Dostarczanie | Brak `.github/` w przeglądanym drzewie | Brak repozytoryjnej konfiguracji CI; ustawień ochrony zdalnej gałęzi nie sprawdzano |

Nie poprawiamy tych problemów przy okazji pisania planu. Trafiają do specyfikacji
przyrostów. Historyczny raport [walidacji](../validation.md) potwierdza działanie
demonstracji i zachowanie danych po migracji, nie gotowość korporacyjną.

## Granice produktu

Pierwszy cel: jedna organizacja, wiele zespołów/projektów/użytkowników,
kontrolowana praca na danych tabelarycznych, wsadowe obliczenia Python/SQL,
eksperymenty MLflow, modele ML i regułowe, analiza/XAI, Git, wersjonowane wydania.

Pierwsze konektory: pliki CSV/Parquet i odczyt z PostgreSQL przez zapytanie.
Architektura konektorów ma dopuszczać kolejne formaty, API i magazyny; nie
obiecuje ich implementacji ani wspólnego schematu tabeli dla każdego typu danych.

Poza pierwszym przekrojem: własny odpowiednik Spark/Photon, hurtownia SQL,
strumieniowanie czasu rzeczywistego, feature store, GPU, serving online z SLA,
marketplace, jednoczesna edycja notebooka, pełne IDE w przeglądarce, air-gap,
wielu niezależnych klientów SaaS i pełna migracja wszystkich funkcji Databricks.
Rozszerzenia wymagają osobnych uzasadnień i specyfikacji.

## Wymagania funkcjonalne

| ID | Wymaganie | Minimalny dowód odbioru | Etap |
|---|---|---|---|
| FR-01 | Tożsamości, zespoły, projekty, właściciele i uprawnienia egzekwowane po stronie serwera | Dostęp odmówiony przez API i SDK do projektu bez uprawnienia; zmiana roli działa bez polegania na UI | S1, rozszerzenia S3/S5 |
| FR-02 | Katalog obiektów oddzielający definicję, wersję i wykonanie | Edycja definicji tworzy nową wersję; stara pozostaje czytelna | S1 |
| FR-03 | Connection, Dataset i DatasetVersion dla plików i zapytań | Zmienione dane pod tym samym adresem dają nową wersję, wcześniejsza odtwarza się ze snapshotu | S2 |
| FR-04 | Transformacje jako wersjonowane Python/SQL z kontraktem I/O i testami jakości | Dwie wersje transformacji współistnieją i mają różne powiązane wyniki | S2 |
| FR-05 | Flow oraz trwałe wykonania w izolowanych workerach | Zadanie przeżywa restart sterowania; ponowienie nie publikuje podwójnego wyniku | S2/S3 |
| FR-06 | Eksperymenty i modele ML oraz nie-ML | Model uczony i regułowy korzystają z katalogu, historii, porównań i uprawnień; `fit` nie jest obowiązkowe | S4 |
| FR-07 | Analizy, ewaluacje i XAI jako wersjonowane definicje i wyniki | Raport wskazuje model, dane, metodę i parametry; brak obsługi XAI jest jawny | S4 |
| FR-08 | Pełne pochodzenie wyniku i ocena odtwarzalności | Z wyniku dochodzimy do konkretnych wersji danych, kodu, konfiguracji, runtime i aktora | S2–S5 |
| FR-09 | Git, praca lokalna i Jupyter zgodne z GUI | Edycja z GUI daje czytelny diff; zmiana z Git jest importowana bez utraty tożsamości obiektów | S3 |
| FR-10 | Kontrolowane wydania, promocja i rollback | Autor nie zatwierdza własnego wydania; produkcja nie czyta roboczej gałęzi ani aliasu `candidate` | S5 |
| FR-11 | Spójny interfejs roboczy, nie tylko linki do usług | Z katalogu można przejść do Flow, uruchomienia, eksperymentu, raportu i wydania w jednym kontekście | S1–S5 |
| FR-12 | Audyt, retencja, eksport i odtworzenie operacyjne | Odtworzenie backupu zachowuje relacje; usunięte zgodnie z polityką dane nie są prezentowane jako dostępne do replay | S1–S6 |

## Inwarianty przekrojowe

- Nie istnieje „gotowy wynik” bez zatwierdzonego manifestu rzeczywistych wejść.
- Nie istnieje dostęp do artefaktu wynikający wyłącznie ze znajomości jego URI/ID.
- Uprawnienie do modelu nie oznacza dostępu do jego danych treningowych.
- Uprawnienie do uruchomienia modelu nie oznacza uprawnienia do pobrania modelu.
- Zmiana gałęzi, aliasu, połączenia lub zasad dostępu nie zmienia historii runu.
- Historia uprawnień nie daje prawa do przyszłego odczytu; replay sprawdza
  aktualne uprawnienia oraz dostępność wszystkich zależności.
- Wynik eksperymentu nie staje się produkcyjny przez zmianę etykiety w UI.
- Operacja obejmująca Git, bazę i magazyn obiektowy nie jest udawaną wspólną
  transakcją; częściowe błędy muszą być wykrywalne i naprawialne.

## Role do zweryfikowania z właścicielem produktu

Tożsamość może mieć wiele ról, ale serwer egzekwuje konflikt obowiązków dla
konkretnego wydania. Pierwsza implementacja potrzebuje przede wszystkim
uprawnień, nie sztywnego zakodowania nazw stanowisk.

| Rola | Zakres, nie automatyczny dostęp do wszystkiego |
|---|---|
| Właściciel projektu | Członkostwo, polityki projektu, odpowiedzialność za zasoby |
| Autor/analityk | Definicje, eksperymenty, uruchomienia dev na dostępnych danych |
| Odbiorca | Odczyt udostępnionych metadanych/wyników, osobne zgody na eksport i wykonanie |
| Recenzent | Ocena wyników, zgoda na konkretny digest wydania; nie własnego autorstwa |
| Operator | Wdrożenie zatwierdzonego wydania, zatrzymanie/rollback; bez edycji kodu produkcji |
| Audytor | Odczyt przyznanego zakresu historii, nie domyślny podgląd danych |
| Administrator platformy | Eksploatacja; dostęp do danych wymaga odrębnego grantu lub audytowanego break-glass |
| Tożsamość zadania | Krótkotrwałe prawa do konkretnych wejść/wyjść i środowiska |

Firma musi wskazać rzeczywistych właścicieli i recenzentów przed pilotażem.
Obecna współpraca użytkownik–asystent nie zastępuje niezależnego audytu ani
organizacyjnego podziału obowiązków.
