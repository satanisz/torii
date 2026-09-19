# ADR-0003: niezmienne wersje, replay i kontrolowane wydania

Status: Accepted (delegated). Data: 2026-09-19.
Podstawa: [mandat realizacji](../docs/platform/delivery-mandate.md).

## Kontekst i alternatywy

Obecna demonstracja zapisuje snapshoty i hashe, lecz używa zmiennego aliasu
modelu. Git nie zachowuje sam danych ani runtime. Sam URI/hash/recepta
pozwalają sprawdzić tożsamość, ale nie zapewniają dostępności oryginału.

Alternatywy: poleganie na najnowszych obiektach, utrwalanie wszystkich bajtów
bez polityki retencji lub jawne wersje z określoną gwarancją odtwarzania.
Pierwsza nie spełnia celu, druga nie respektuje ograniczeń danych i kosztu.

## Proponowana decyzja

Rozdzielamy obiekt, wersję i run. Snapshot jest domyślny dla importu pliku i
wyniku zapytania; zewnętrzna wersja dopuszczalna przy udokumentowanych gwarancjach.
Manifest pinujący wejścia i runtime konkretnego kroku powstaje przed jego
obliczeniami. Wyjścia wcześniejszych kroków i snapshoty nowych źródeł są
rozwiązywane po ich finalizacji, zanim ruszy krok konsumujący te dane.
Plan całego Flow może wcześniej zawierać symboliczne zależności; końcowy
manifest Runu rejestruje wszystkie faktycznie użyte wersje, bez nadpisania
historii ich rozwiązywania. Wyniki dostają finalny manifest po weryfikacji publikacji.

Alias można rozwiązać przy przygotowaniu planu, ale zapisujemy konkretną
wersję i tylko jej używamy. Release zawiera zamrożone definicje, model,
kod i runtime oraz politykę wiązania wejść. Run produkcyjny może używać nowych
danych, zawsze utrwalając ich faktyczne wersje. Approval dotyczy digestu pakietu;
zmiana pakietu wymaga nowej decyzji. Autor nie zatwierdza własnego release.

## Konsekwencje i weryfikacja

Potrzebne są retencja, integralność, zapobieganie nadpisaniu i obsługa wygaśnięcia
zależności. Gwarancja replay jest niezależna od zgodności bajtowej/numerycznej
wyniku. Modele niedeterministyczne wymagają ustalonego protokołu porównania.

Rollback przywraca wcześniejszy pakiet wdrożenia. Nie cofa automatycznie
skutków biznesowych ani zapisów w systemach zewnętrznych. Transformacje
ze skutkami ubocznymi potrzebują osobnej specyfikacji kompensacji.

Dowód: źródło, alias i gałąź zmieniają się, stary run nadal odtwarza się według
swojego manifestu. Brak starego wejścia daje jawny błąd, nie podmianę na aktualne.
