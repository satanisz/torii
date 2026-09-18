# ADR-0001: granice platformy i rozwój obecnego repozytorium

Status: Proposed. Data: 2026-09-19. Akceptujący: nie wskazano.

Aktualizacja kontekstu 2026-09-19: użytkownik potwierdził preferencję podejścia
modułowego i zlecił plan sprintów obejmujący infrastrukturę, backend i frontend.
Jest to potwierdzenie kierunku, nie formalna akceptacja wszystkich szczegółów
tego ADR ani kontraktów implementacyjnych. Status pozostaje Proposed.

## Kontekst

Repozytorium zawiera działające środowisko i demonstrację AutoML, ale nie
zawiera rdzenia platformy wieloużytkownikowej. Trzeba zachować historię,
artefakty i kompatybilność, bez uczynienia pojedynczego skryptu fundamentem API.

## Alternatywy

1. Nowe repozytorium całego produktu: czysty start, ale rozdzielona historia,
   ponowne przenoszenie infrastruktury i ryzyko dwóch konkurencyjnych Torii.
2. Rozbudowa `scaffold/.../automl/mvp.py` w aplikację: mały koszt startu,
   lecz miesza szablon projektu użytkownika z uprzywilejowaną platformą.
3. Nowy modularny rdzeń w obecnym repozytorium, zachowana demonstracja.
4. Osobny mikroserwis/repo na każdy obiekt: izolowane wydania, ale koszt
   kontraktów rozproszonych i transakcji bez wykazanej potrzeby.

## Proponowana decyzja

Wariant 3. Jeden modularny backend sterowania; osobny frontend i procesy
workerów. Moduły domenowe nie importują adapterów vendorowych. Kod projektów
użytkownika nie jest wykonywany w API. Obecny scaffold pozostaje przykładem
i źródłem testów migracji, nie miejscem dopisywania całej platformy.

## Konsekwencje i weryfikacja

Mniejszy koszt zmian kontraktów niż w sieci mikroserwisów, ale granice modułów
muszą być egzekwowane testami zależności i własnością danych. Baza platformy
ma osobną rolę i schemat migracji od bazy MLflow. Docker lokalny nie jest
topologią produkcyjną. Wydzielenie usługi możliwe po pomiarach lub wymaganiu
izolacji; wymaga nowego ADR.

Dowód S1: katalog/uprawnienia działają bez importowania AutoGluon i bez
uruchamiania DataHub. Dowód S2: kod transformacji działa tylko w workerze.
Akceptacja ADR nie zastępuje specyfikacji implementacyjnej tych etapów.
