# ADR-0005 Warsztat finansów banku

2026-10-09. Status: Accepted (delegated) dla lokalnego zakresu SPEC-0019
po technicznym review platform_runtime, banking_feasibility i platform_products.
Architektura produkcyjna pozostaje kierunkiem do dalszej specyfikacji.

Użytkownik doprecyzował, że priorytetem są księga główna, portfele, prognozy
wyniku, anomalie i NII. Wybór scenariusza fraud/alertów zostaje porzucony.

## Decyzja proponowana

Torii rozwijamy jako warsztat danych i modeli dla finansów banku. Kluczowym
obiektem jest wersjonowana analiza finansowa z datą danych, scenariuszem,
metodą, uzgodnieniem i wynikami, obejmująca modele finansowe oraz ML.
MLflow zachowuje rolę trackingu eksperymentów ML; nie narzucamy treningu
ani rejestracji modelu ML deterministycznemu kalkulatorowi odsetek.

Docelowy rdzeń React/FastAPI/PostgreSQL i OIDC pozostaje. Dane wejściowe
docelowo pochodzą z konektorów read-only do bankowych baz, trafiają do
wersjonowanych snapshotów w magazynie obiektowym. Własne worker jobs
wykonują małe obliczenia; adapter firmowego schedulera/Kubernetes jest
następną granicą, nie warunkiem demonstracji.

Pierwszy przyrost SPEC-0019 to lokalny proces na syntetycznym wycinku księgi
i portfela. Współdzieli aplikację demo i jej limity, ma osobne wyniki i ekran.
Nie omija niedokończonej autoryzacji enterprise ani nie zalicza SP-01–15.

## Alternatywy i konsekwencje

Pełny produkt ALM (Oracle/SAS/OneSumX) jest właściwym kandydatem do zakupu
przy szerokich wymaganiach banku. Tutaj brak budżetu i danych firmy, więc
przejmujemy wzorzec danych/scenariuszy/śledzenia wyniku, bez odtwarzania
pełnego silnika kontraktowych i behawioralnych przepływów.

Dataiku/Databricks są wzorcami platformy analitycznej; nie zakładamy, że
sam wybór jednego z nich definiuje metodykę NII. Podobnie Kubernetes i MLflow
nie definiują kont księgowych, założeń portfela ani poprawności finansowej.

Zachowujemy istniejące demo regresji i pliki legacy. Nowy moduł nie dodaje
zależności ani zewnętrznych usług. Celowo odkładamy P&L, FTP, IFRS9, EVE,
waluty/hedging, modele zachowań klientów i produkcyjne zatwierdzanie.
Kolejne rozszerzenie wymaga osobnej SPEC i weryfikacji metodyki.
