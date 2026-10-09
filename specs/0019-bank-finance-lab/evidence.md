# SPEC-0019 — dowody lokalnej weryfikacji

2026-10-09. Zakres F01–F07 zaimplementowany i zweryfikowany technicznie
w lokalnym profilu demo. Nie jest to odbiór metodyki przez bank, pomiar
regulacyjny ani gotowość środowiska enterprise. Zmiany pozostają lokalne.

## Automatyczne sprawdzenia

| Sprawdzenie | Wynik |
|---|---|
| `apps/demo/.venv/Scripts/python.exe -m pytest apps/demo/tests -q --basetemp=apps/demo/.local/pytest-finance-integrated` | 141 PASS: 54 istniejące, 61 engine, 26 finance API |
| `python -m ruff check apps/demo/src apps/demo/tests` w demo venv | PASS |
| `python -m ruff format --check apps/demo/src apps/demo/tests` w demo venv | 14 plików PASS |
| `npm run test` w apps/web | 76 PASS, w tym 8 finance |
| `npm run lint` w apps/web | PASS |
| `npm run build` w apps/web | PASS: kontrakt OpenAPI, TypeScript, Vite |
| `scripts/test-demo-launcher.ps1` | 4 testy własności procesu + 4 blokady Stop PASS |
| Lokalne odnośniki w zmienionej dokumentacji | 9 dokumentów, 46 odnośników PASS |
| `git diff --check` | PASS |

Testy backendu i Vitest uruchomiono poza sandboxem po błędach Windows ACL
w katalogach tymczasowych; eskalacje zostały zaakceptowane. Nie zmieniano
kodu aplikacji, aby obchodzić te błędy. Backend pozostawił dwa ostrzeżenia
deprecacji Starlette/httpx i anyio. Po kosmetycznej normalizacji wyświetlania
ujemnego zera ponowiono 8 testów finance, lint i typy; końcowy build obejmuje
również doprecyzowanie etykiet eksportu i analiz ML w zakładce finansowej.

## Rzeczywiste wykonania i przeglądarka

Launcher uruchomił własny proces na `127.0.0.1:18440`. W GUI utworzono projekt
**Finanse banku — NII i księga**, ID `e36a24f4-d851-4ee6-afe6-145b7c0ecb65`.
Każdy z poniższych scenariuszy uruchomiono przyciskiem formularza; backend
wykonał rzeczywisty subprocess i zapisał raport.

| Scenariusz | Wykonanie | Potwierdzony wynik |
|---|---|---|
| +100 pb, beta 0,35, czyste dane | `cdc12725-9f4c-44b0-95df-6f846db61ae6` | NII 21 399 999,99 → 21 667 123,33 PLN; delta +267 123,34 PLN; jakość passed |
| 0 pb, beta 0,35, czyste dane | `1f8eb192-78f7-4241-8251-3f2183e81096` | Delta 0,00 PLN; jakość passed |
| +100 pb, beta 0,35, celowe błędy | `8b441a54-ffc7-4302-899d-60f0fe5a617a` | Jakość blocked; różnica portfel − GL: −1 250 000 PLN; sygnał 2026-08 |

Sygnał historyczny: NII 1 172 000 PLN, mediana poprzednich sześciu miesięcy
1 807 000 PLN, odchylenie −635 000 PLN, próg 100 000 PLN. To wynik reguły.

W przeglądarce sprawdzono:

- stan trwającego wykonania i automatyczne przejście do raportu;
- wybór wcześniejszego scenariusza 0 pb oraz powrót do czystego +100 pb;
- 12 wierszy rozwiniętej tabeli miesięcznej, wykres, wkład portfeli,
  uzgodnienie i jawny status roboczy przy kwotach dla blocked;
- endpoint z linku eksportu: HTTP 200, attachment JSON i pełna zgodność
  eksportu z Run zwracanym przez historię;
- przełączenie na istniejący projekt: zachowane stare dane regresji,
  pusta historia finansowa, brak wyniku pochodzącego z innego projektu;
- bezpośredni link `?view=finance&project=ID` i odświeżenie strony;
- widok 1440 × 1000 oraz emulację 390 × 844: brak poziomego przepełnienia
  całej strony, czytelne kwoty i ostrzeżenie jakości; tabele mają własny scroll;
- brak błędów i ostrzeżeń konsoli podczas sprawdzanych ścieżek.

Zatrzymano wyłącznie proces uruchomiony przez launcher, następnie uruchomiono
go ponownie. Historia zawierała te same trzy raporty. SHA-256 z JSON całej
listy przed i po restarcie był identyczny:
`b655f27b6c3f15972a42fe414441408f86537c6c562e73a059f1f41960bb0004`.
Demo pozostawiono uruchomione do ręcznego sprawdzenia.

## Przegląd i pokrycie kryteriów

Specyfikację 0.2 doprecyzowano i poddano niezależnemu review przed kodem.
Po implementacji banking_feasibility przejrzał API/integrację i frontend,
a platform_runtime niezależnie przejrzał engine. Root sprawdził integrację,
rachunek, raporty i UI. Wszystkie końcowe przeglądy bez istotnych zastrzeżeń.

Wykryty problem API: sama zgodna koperta bez ciała raportu mogła otrzymać
succeeded. Naprawa wymusza strukturę Report, wymagane kwoty i długości list
przed atomowym zapisaniem sukcesu. Trzy przypadki uszkodzonego raportu są
objęte testami; recenzent potwierdził poprawkę.

| Kryterium | Dowód |
|---|---|
| F01 | Testy hash/snapshot, niezmienne wejścia także dla failed, prawdziwy restart |
| F02 | Ręczne fixtures silnika: ACT/365F, rounding, strony, repricing, beta, floor; GUI 0 pb |
| F03 | Testy uzgodnienia i walidacji; rzeczywisty raport blocked z różnicą GL |
| F04 | Testy poprzedniego okna bez przyszłości; sygnał historyczny w rzeczywistym raporcie |
| F05 | Testy subprocess, timeout/failure/recovery, uszkodzonego wyniku, wspólnego gate, guard i projektów |
| F06 | 8 testów UI, rzeczywiste scenariusze, historia/eksport, desktop i mobile |
| F07 | [Porównanie i źródła](../../docs/platform/banking-finance-research.md), [ADR-0005](../../adr/0005-bank-finance-workbench.md) |

## Granice odbioru

Dane są syntetyczne, jednoosobowe demo bez SSO. Brak importu ksiąg banku,
modelu kontraktowych przepływów, prognozy całego P&L, wytrenowanego modelu
anomalii i niezależnego zatwierdzania. Nie wykonywano kwalifikacji enterprise,
testu produkcyjnego restore ani testu wydajności. Pełne testy enterprise API
nie były powtarzane: ten komponent nie został zmieniony.
