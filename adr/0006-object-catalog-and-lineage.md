# ADR-0006 Katalog obiektów i graf pochodzenia

2026-10-10. Status: Proposed. Zlecenie użytkownika dotyczy planu sprintów
platformy enterprise; nie oznacza przyjęcia nowych kontraktów implementacji.
Rozszerza ADR-0001/0002/0003, zachowując osobny profil demo ADR-0004/0005.

## Problem

Dashboard NII prezentuje wynik, ale nie zapewnia wspólnej pracy nad katalogiem
danych, transformacji i eksperymentów. Potrzebujemy trwałej tożsamości obiektów,
niezmiennych wersji i dowodów faktycznego wykonania, czytelnych także w grafie.

## Proponowana decyzja

1. PostgreSQL pozostaje źródłem prawdy metadanych i relacji Torii; artefakty
   przechowujemy osobno. Graf UI jest autoryzowaną, ograniczoną projekcją.
2. Rozdzielamy graf deklarowanych referencji, historyczne lineage Run/Attempt
   i plan wykonywalnego Flow. Layout nie jest elementem wersji metody.
3. Katalog i graf deklaracji powstają w SP-02, faktyczne wersje danych w SP-03,
   a lineage wykonania w SP-04. Pełny edytor planów pozostaje SP-06.
4. React Flow jest rekomendowanym komponentem grafu; OpenLineage standardem
   wymiany, bez przenoszenia tam transakcyjnych reguł autoryzacji/finalizacji.
5. Dagster jest pierwszym kandydatem próby wykonania; wybór runtime wymaga
   Accepted SPEC-0004 i dowodów awarii/izolacji. Nie budujemy równoległego
   własnego schedulera DAG. Temporal jest alternatywą dla innego profilu pracy.
6. SPEC-0010 otrzyma wersjonowany protokół eksperymentu. Wąskie SP-10A pojawi
   się wcześniej, z ochroną całego projektu; sharing i pełny rejestr SP-10B później.

## Alternatywy i konsekwencje

Neo4j jako główny rejestr zwiększa koszt synchronizacji polityk i transakcji
przed wykazaniem potrzeby zapytań grafowych. DataHub może być projekcją katalogu
firmy, lecz nie zastępuje rejestru wersji i publikacji Torii. Pozostanie przy
dashboardach nie realizuje edycji obiektów ani przejścia od wyniku do źródeł.

Wybrany kierunek wymaga kontraktów krawędzi i ich widoczności, stronicowania
grafu, spójności outbox oraz jawnego stanu opóźnionej projekcji. Manifest kodu,
danych i OCI nadal jest niezbędny: sam stan grafu i metryki MLflow nie dają replay.

## Weryfikacja przed przyjęciem

Rozszerzenia SPEC-0001/0017 dla katalogu, SPEC-0003/0004/0006 dla snapshotów
i wykonań oraz SPEC-0010 dla eksperymentów mają mieć konkretne kontrakty,
testy negatywne i review przed kodem. Kryteria: zachowana historia po zmianie
definicji, brak wycieku zależności, próby crash/retry i spójny odczyt tabela/graf.

Szczegóły i źródła: [architektura obiektów](../docs/platform/enterprise-object-platform.md).
Kolejność wykonania: [jedyny plan sprintów](../docs/platform/sprint-plan.md).
