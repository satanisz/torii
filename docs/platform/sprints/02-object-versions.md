# SP-02 — katalog, wersje i graf zależności

Rewizja planu 0.2, 2026-10-10. Status: Planned; nie Ready.
Zależność: odebrany [SP-01](01-foundation.md).
Cel: Dataset i Transformation są obiektami Torii z historią definicji,
bez cichego nadpisywania pracy użytkowników. Katalog ma tabelę i graf
deklarowanych referencji, z inspektorem konkretnej wersji.
Kontrakty: istniejące Accepted SPEC-0001/0002/0017 oraz nowa rewizja
SPEC-0001/0017 dla grafu, do napisania i review przed implementacją.
Ten plan nie zmienia zaakceptowanych kontraktów API ani schematów.
Kierunek: [architektura obiektów](../enterprise-object-platform.md).

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
| SP02-07 | QA/review | Pełna macierz SPEC-0001 i nowego zakresu grafu, E2E, regresja SP-01, dokumentacja | SP02-01–06, SP02-08–10 | AC-01–15 i przyjęte nowe AC PASS z dowodami, nie wyłącznie mocki |
| SP02-08 | Kontrakty/backend | Typowane referencje wersji, autoryzowane i ograniczone API upstream/downstream; odrębny layout | SP02-01/02; Accepted nowe rewizje SPEC | G-01/02/03; constraints i filtrowanie po stronie serwera |
| SP02-09 | Frontend | React Flow do odczytu referencji, inspektor, filtry i równoważna lista | SP02-04/08 | G-01/04/05; ten sam zasób w tabeli/grafie/URL, brak atrap wykonań |
| SP02-10 | Backend/QA | Testy krawędzi po nowej wersji/archiwizacji/cofnięciu praw, limity grafu i regresja finalizacji | SP02-03/08/09 | G-02/03/05; historia zachowana; brak przecieku nazw/liczników |

G-01–05 to kryteria proponowane do rewizji SPEC, nie nowe Accepted AC:

- G-01: tabela, graf i inspektor prowadzą do tego samego trwałego ID/wersji.
- G-02: krawędź przypina wersje i typ referencji. Publikacja v2 nie przepisuje
  zależności v1; usunięcie/archiwizacja ma jawną semantykę.
- G-03: osoba bez uprawnienia nie poznaje obcych węzłów, krawędzi ani liczników;
  odmowa działa także w surowym API i po odebraniu grantu.
- G-04: zależność deklarowana jest opisana jako niewykonana; pozycja węzła
  w UI nie wpływa na definicję ani digest. Nawigacja działa klawiaturą/listą.
- G-05: duży graf ładuje ograniczony fragment i rozwija sąsiedztwo. Oznaczenie
  przycięcia dotyczy limitów dozwolonego zbioru, nie istnienia ukrytych zasobów.

## Pokaz na review

A tworzy DatasetDefinition v1 i definicję transformacji. B odczytuje je
w swoim zakresie uprawnień. Dwa klienty edytują ten sam draft: drugi otrzymuje
konflikt i zachowuje własny tekst do rozwiązania, nie nadpisuje pierwszego.
Finalizacja nowej wersji nie zmienia v1. Retry finalizacji daje ten sam wynik.
Awaria w transakcji nie zostawia półwersji; archiwizacja nie usuwa historii.

UI pokazuje „definicja — niewykonana”. Nie ma jeszcze snapshotu ani przycisku
treningu. Uprawnienia są identyczne przy ręcznym wywołaniu endpointów.
Z tabeli A otwiera graf, wybiera TransformationVersion i przechodzi do
zadeklarowanej wersji DatasetDefinition. Po zmianie draftu stary graf wersji
pozostaje bez zmian. Nie jest to jeszcze graf odczytów danych.

## Testy, wycofanie i granica zakresu

Testy: wszystkie AC SPEC-0001, testy inwariantów/property-based, konkurencja,
deserializacja niezaufanej definicji bez wykonania kodu, migracja i restore.
Każdy dowód podaje commit i topologię. Raport wydajności jest baseline lokalnym,
nie deklaracją spełnienia firmowego P1.

Wycofanie: kompatybilny schemat albo restore do nowej bazy z kontrolą okna
zapisu. Nie usuwamy nowych wersji, aby „odblokować” rollback aplikacji.
Brak operacji na dotychczasowych wolumenach MLflow/MinIO.

Poza zakresem: import danych, execution, edytor wykonywalnego DAG, SQL,
Git sync, MLflow i XAI. Kontrakt wersji eksperymentu należy do SPEC-0010
przed SP-10A; nie dodajemy pustych obiektów eksperymentów do GUI.
Ich specyfikacje rozszerzają obiekty poprzez walidowane kontrakty; nie dodajemy
z góry dowolnego pola `config` przyjmującego wszystko.

## Refinement i kalibracja kolejnego planu

Przed zamknięciem SP-02 przygotowujemy SPEC-0003 i zakres próby storage,
a dla SPEC-0004 pytanie o runner/izolację. Po akceptacji mini-SPEC prób można
je przeprowadzić bez danych firmy. Wyniki muszą poprzedzić przyjęcie zależnego
przyrostu implementacyjnego; nie blokują niepowiązanych zadań katalogu.
Następny przyrost: [SP-03](03-data-snapshots.md).

Aktualizujemy plan SP-03+ na podstawie rzeczywistego czasu testów, integracji,
review i usuwania błędów. Nie zmieniamy osiągniętych kryteriów, żeby uzasadnić
wcześniejszą estymatę. Pełne Verified SPEC-0001 wymaga wszystkich jej AC,
nie samego zamknięcia numeru sprintu.
