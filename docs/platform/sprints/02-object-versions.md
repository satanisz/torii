# SP-02 — katalog, drafty i niezmienne wersje

Status: Planned; nie Ready. Zależność: odebrany [SP-01](01-foundation.md).
Cel: Dataset i Transformation są obiektami Torii z historią definicji,
bez cichego nadpisywania pracy użytkowników.
Kontrakty: Accepted SPEC-0001/0002/0017, z przeglądem zmian odkrytych w SP-01.

## Backlog planowany

Wszystkie pozycje M i Planned; estymaty i konkretni ownerzy na planningu.

| ID | Tor | Zakres | Zależność | Kryteria SPEC-0001 / dowód |
|---|---|---|---|---|
| SP02-01 | Backend/QA | Typy DatasetDefinition i TransformationDefinition, schema versions, kanonizacja i constraints | SP-01 | AC-05/08; fixtures Python/JS mają ten sam payload/digest |
| SP02-02 | Backend | Utworzenie obiektu, draft/revision, list/detail, grants i archiwizacja | SP02-01 | AC-02/03/04/08/09/10/11; sprawdzenie praw obejmuje stare wersje |
| SP02-03 | Backend/QA | Atomowa finalizacja, idempotency key i audyt, zachowanie przy błędach | SP02-01/02 | AC-05/06/07/11; test prawdziwych współbieżnych transakcji PostgreSQL |
| SP02-04 | Frontend | Katalog, filtrowanie/paginacja, szczegóły i rozróżnienie definicji od danych | SP02-02 | AC-02/03/13; brak ujawnienia cudzych liczników, stan pusty i odmowa |
| SP02-05 | Frontend/backend | Formularz draftu, walidacja pól, porównanie wersji, finalizacja i rozwiązywanie konfliktu | SP02-03/04 | AC-04/05/08/13/14; błąd nie gubi edycji ani nie uruchamia treści definicji |
| SP02-06 | Infrastruktura/QA | Upgrade z SP-01, restart, restore fixture z wersjami i grantami, pomiar API katalogu | SP02-03 | AC-12/15, NFR-05 baseline; stare ID/digesty nie zmieniają się |
| SP02-07 | QA/review | Pełna macierz SPEC-0001, E2E, regresja SP-01, dokumentacja i decyzja o przyjęciu | SP02-01–06 | AC-01–15 PASS z dowodami, nie wyłącznie testy mocków |

## Pokaz na review

A tworzy DatasetDefinition v1 i definicję transformacji. B odczytuje je
w swoim zakresie uprawnień. Dwa klienty edytują ten sam draft: drugi otrzymuje
konflikt i zachowuje własny tekst do rozwiązania, nie nadpisuje pierwszego.
Finalizacja nowej wersji nie zmienia v1. Retry finalizacji daje ten sam wynik.
Awaria w transakcji nie zostawia półwersji; archiwizacja nie usuwa historii.

UI pokazuje „definicja — niewykonana”. Nie ma jeszcze snapshotu ani przycisku
treningu. Uprawnienia są identyczne przy ręcznym wywołaniu endpointów.

## Testy, wycofanie i granica zakresu

Testy: wszystkie AC SPEC-0001, testy inwariantów/property-based, konkurencja,
deserializacja niezaufanej definicji bez wykonania kodu, migracja i restore.
Każdy dowód podaje commit i topologię. Raport wydajności jest baseline lokalnym,
nie deklaracją spełnienia firmowego P1.

Wycofanie: kompatybilny schemat albo restore do nowej bazy z kontrolą okna
zapisu. Nie usuwamy nowych wersji, aby „odblokować” rollback aplikacji.
Brak operacji na dotychczasowych wolumenach MLflow/MinIO.

Poza zakresem: import danych, execution, SQL, Git sync, MLflow i XAI.
Ich specyfikacje rozszerzają obiekty poprzez walidowane kontrakty; nie dodajemy
z góry dowolnego pola `config` przyjmującego wszystko.

## Refinement i kalibracja kolejnego planu

Przed zamknięciem SP-02 przygotowujemy SPEC-0003 i zakres próby storage,
a dla SPEC-0004 pytanie o runner/izolację. Po akceptacji mini-SPEC prób można
je przeprowadzić bez danych firmy. Wyniki muszą poprzedzić przyjęcie zależnego
przyrostu implementacyjnego; nie blokują niepowiązanych zadań katalogu.

Aktualizujemy plan SP-03+ na podstawie rzeczywistego czasu testów, integracji,
review i usuwania błędów. Nie zmieniamy osiągniętych kryteriów, żeby uzasadnić
wcześniejszą estymatę. Pełne Verified SPEC-0001 wymaga wszystkich jej AC,
nie samego zamknięcia numeru sprintu.
