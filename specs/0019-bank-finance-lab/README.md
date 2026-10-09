# SPEC-0019 Laboratorium finansów banku

Data: 2026-10-09. Rewizja 0.2. Status: Accepted (delegated), do lokalnej
implementacji po technicznym review platform_runtime, banking_feasibility
i platform_products oraz zapisaniu poniższych doprecyzowań przed kodem.
Nie oznacza ludzkiego odbioru metodyki bankowej ani wdrożenia enterprise.

Implementacja lokalna F01–F07 zweryfikowana 2026-10-09;
[testy, przegląd i rzeczywiste wykonania](evidence.md).

## Cel i mandat

Użytkownik zlecił zebranie informacji o gotowych platformach i zbudowanie
konkretnego rozwiązania dla banku, powierzając dobór techniczny asystentowi.
Doprecyzował domenę: księgi główne, portfele, prognozowanie zysku, anomalie, NII.
Pierwszy przyrost obejmuje lokalne laboratorium NII i uzgodnienia danych
syntetycznych, w istniejącym profilu demo SPEC-0018. Nie zalicza sprintów
enterprise, nie zmienia kont, legacy, .env ani firmowych danych.

Pytanie odbiorowe: czy analityk finansowy potrafi porównać bazowy NII i scenariusz
stóp, wyjaśnić zmianę przez portfele oraz wykryć rozbieżność księgową?

## Zakres i inwarianty

- Nowa zakładka Finanse banku w istniejącym demo, oddzielna od regresji ML.
  Link ?view=finance&project=ID otwiera ją w wybranym istniejącym projekcie;
  nieznane ID używa dotychczasowego wyboru domyślnego.
- Dane generowane lokalnie: sześć zagregowanych pozycji aktywów/pasywów,
  odpowiadające salda kont księgi i 12 miesięcy syntetycznego wyniku odsetkowego.
  To wycinek bilansu, nie pełna księga podwójnego zapisu ani dane klientów.
- Wybór czystego zestawu lub zestawu z celową rozbieżnością księgową i skokiem
  historycznego kosztu odsetkowego. Brak importu danych firmy w tym przyroście.
- Każde wykonanie zapisuje niezmienny snapshot wejść i scenariusza, ich SHA-256,
  wersję silnika i hash kodu silnika, datę wykonania oraz wynik. Ponowienie jest
  nowym wykonaniem; nie nadpisuje poprzedniego. Brak pozornego workflow approval.
- Obliczenia w dedykowanym subprocess ze stałym modułem, timeout 30 s; brak
  eval/exec, uploadu kodu/modeli, dowolnych ścieżek i połączeń sieciowych.
- Jeden wspólny limit aktywnego wykonania dla ML i finansów. Stany nowych runów
  queued/running/succeeded/failed. Restart oznacza osierocone runy jako failed.
- Addytywne /demo-api/state.execution_active wskazuje zajęcie wspólnego gate.
  Launcher Stop sprawdza tę flagę oraz dotychczasowe aktywne runs; zapobiega
  zatrzymaniu aplikacji w trakcie obliczeń finansowych. Stare runs bez zmian.
- Obecny demo guard, loopback i ograniczenia requestów pozostają w mocy.
  Historia finansowa jest odrębna od kontraktu regresyjnego /state.
- Uzgodnienie z błędem nie zatrzymuje eksploracji scenariusza, lecz wynik ma
  quality_status=blocked i UI jawnie oznacza go jako roboczy z nieuzgodnionych
  danych. Brak możliwości przedstawienia go jako zatwierdzonego wydania.

## Metoda obliczeń

NII to przychody odsetkowe minus koszty odsetkowe, nie zysk netto banku.
Horyzont: 2026-10-01 do 2027-10-01, 12 miesięcy, PLN, ACT/365F.
Przyjmujemy stałe salda, brak zapadalności i nowej sprzedaży w horyzoncie,
bez amortyzacji, opcji, FX, hedgingu, EIR/IFRS9 i modeli behawioralnych depozytów.
Wynik jest projekcją warunkową, a nie statystyczną prognozą przyszłych stóp
ani regulacyjnym pomiarem IRRBB.

Stopa wejściowa jest rocznym ułamkiem dziesiętnym (0.06 = 6%). Dla stałej
stopy szok nie zmienia kuponu. Dla zmiennej od miesiąca repricing_month
(1..12, włącznie) stopa = max(rate_floor, annual_rate + shock_bps/10000 × beta).
Beta jest parametrem 0..1 tylko dla depozytów oszczędnościowych; pozostałe
zmienne pozycje mają beta=1. Przeszacowanie na początku wskazanego miesiąca.
Scenariusz bazowy ma shock_bps=0. Szok porównawczy: całkowite -300..300 pb,
domyślnie +100 pb. Nie nazywać tego szokiem nadzorczym.

Odsetki pozycji za miesiąc = saldo × stopa × liczba dni miesiąca / 365.
Obliczenia Decimal, HALF_UP do 0.01 PLN na pozycji i miesiącu; sumy powstają
z zaokrąglonych pozycji. Salda są dodatnie; side asset/liability określa znak
w NII. Raport wskazuje stopy, odsetki i wkład każdej pozycji w zmianę NII.
Odsetki w Contribution nie mają znaku strony; delta_nii_pln ma znak aktywa
lub pasywa. annual_rate >= rate_floor; floor stosujemy od repricing zarówno
w bazie, jak i scenariuszu. Przed repricing obowiązuje annual_rate.

Uzgodnienie porównuje sumy sald portfela i księgi po gl_account i side;
uwzględnia konta istniejące tylko po jednej stronie. Różnica = portfolio - GL,
matched gdy abs(różnica) <= 0.01 PLN. Pozycje unikalne po id, konta księgi
po (gl_account,side); wiele pozycji może mapować do jednego konta. Nieznana strona,
waluta, brak wymaganych pól lub niefinitywne liczby są błędami danych.

Anomalie historyczne: reguła na NII, bieżący miesiąc względem poprzednich
6 miesięcy. Próg max(100000 PLN, 3 × 1.4826 × MAD). Okno nie obejmuje
badanego miesiąca ani przyszłości. Zapisujemy miesiąc, obserwację, medianę,
próg i odchylenie ze znakiem. Sygnał gdy abs(odchylenie) > próg.
Historia to dokładnie 12 kolejnych miesięcy 2025-10..2026-09, rosnąco;
pierwsze sześć nie podlega ocenie. To sygnał do weryfikacji, nie model ML
ani dowód błędu. Duplikaty i brak miesiąca są błędami.

Walidacja silnika: 1..100 pozycji i 1..100 kont GL, saldo 0..1e12 PLN,
stopy i floor -1..1, kwoty historyczne 0..1e12 PLN, nazwy/ID 1..100 znaków,
liczby finite, int bez bool. Beta dotyczy tylko zmiennego pasywa.
Snapshot ma ustaloną datę/walutę; nie przyjmujemy innych zakresów czasu.

## Kontrakt API

Wszystkie endpointy pod /demo-api, JSON extra=forbid i krótkie błędy.

- GET /finance/sample -> snapshot generowany dla czystego zestawu.
- GET /projects/{project_id}/finance/runs -> lista runów danego projektu,
  od najnowszego; brak projektu daje 404.
- POST /projects/{project_id}/finance/runs -> 202;
  body {shock_bps:int=100, deposit_beta:float=0.35, inject_issues:bool=false}.
  Zakres shock_bps: -300..300 włącznie, deposit_beta: 0..1 włącznie.
  409 gdy jakikolwiek run demo trwa; brak projektu 404, błędne parametry 422.
- GET /projects/{project_id}/finance/runs/{run_id} -> pełny run danego projektu.
- GET /projects/{project_id}/finance/runs/{run_id}/export -> JSON tylko sukcesu;
  404 dla innego projektu, brakującego lub niedokończonego runu.

Run = {id,project_id,status,created_at,snapshot:Snapshot,scenario:Scenario,
manifest:Manifest,error:null|string,result:null|Report}.
Niezmienną kopertę wejść zapisujemy przy queued przed submit, także dla
przyszłego failed. Manifest silnika porównujemy z wynikiem subprocess;
niezgodność jest błędem. Result i terminalny status zapisujemy atomowo.
Eksport zawiera cały Run, w tym datę i identyfikatory.
Lista może zwracać pełne runy w małym zakresie demo. Brak auth zgodnie z0018;
sprawdzenie project_id to integralność referencji, nie izolacja użytkowników.

Snapshot = {as_of:"2026-09-30",currency:"PLN",positions:Position[],
ledger:Ledger[],history:History[]}.
Position = {id,name,gl_account,side:"asset"|"liability",balance_pln:number,
annual_rate:number,rate_type:"fixed"|"floating",repricing_month:int,
deposit_beta_applies:bool,rate_floor:number}.
Ledger = {gl_account,side,balance_pln:number}.
History = {month:"YYYY-MM",interest_income_pln:number,interest_expense_pln:number}.
Scenario = {shock_bps:int,deposit_beta:number,inject_issues:bool}.

Manifest = {engine_version:string,engine_sha256:string,input_sha256:string,
scenario_sha256:string}. Hashe z store.encode UTF-8, daty runu poza hashem.
Report = {snapshot:Snapshot,scenario:Scenario,manifest:Manifest,
assumptions:string[],quality_status:"passed"|"blocked",
reconciliation:Reconciliation[],anomalies:Anomaly[],monthly:Month[],
contributions:Contribution[],totals:Totals}.
Reconciliation = {gl_account,side,portfolio_pln,ledger_pln,difference_pln,status:"matched"|"mismatch"}.
Anomaly = {month,nii_pln,baseline_pln,threshold_pln,deviation_pln}.
Month = {month,income_base_pln,expense_base_pln,nii_base_pln,
income_scenario_pln,expense_scenario_pln,nii_scenario_pln,delta_nii_pln}.
Contribution = {position_id,name,side,balance_pln,rate_type,repricing_month,
base_interest_pln,scenario_interest_pln,delta_nii_pln,
monthly:[{month,base_rate,scenario_rate,base_interest_pln,scenario_interest_pln}]}.
Totals = {income_base_pln,expense_base_pln,nii_base_pln,
income_scenario_pln,expense_scenario_pln,nii_scenario_pln,delta_nii_pln}.
Kwoty JSON number po kalkulacji Decimal, prezentacja PLN z dwoma miejscami.

## Podział implementacji

- finance_engine.py: synthetic_snapshot(inject_issues=False),
  calculate(snapshot, scenario), build_manifest(snapshot, scenario),
  CLI python -m torii_demo.finance_engine job.json.
  Job {snapshot,scenario,output_path}; ścieżki wyłącznie wewnętrzne, output_path
  absolutny, nowy plik w tym samym katalogu co job.json, bez symlinków.
  CLI nie używa sieci, zapis output_path w trybie x. calculate daje Report.
  Subprocess nie jest sandboxem ani egzekwowaną izolacją sieci.
- finance_api.py: FinanceStore na osobnej finance.sqlite w podkatalogu
  store.root/finance; własne finance_runs snapshoty i wyniki JSON; router i
  worker orchestration współdzielą gate/pool z demo. register_finance(app,
  store, gate, pool) zwraca callback recover wywołany przy startupie.
  Każda trasa sprawdza nadrzędne store.project(); błąd submit oznacza failed
  i zwalnia gate. Recovery zmienia wyłącznie queued/running, nie terminalne.
- Finance.tsx oraz finance-types.ts/finance.css: zakładka per projekt,
  parametry, uruchomienie/polling, historia, uzgodnienie, 12 miesięcy NII,
  wkład portfeli, regułowe anomalie, założenia i eksport. Nie wymaga datasetu
  wybranego w zakładce regresji. DemoApp integrowane przez root.

## Kryteria odbioru

- F01: dane czyste i z błędem mają stabilny hash; każde wykonanie zachowuje
  snapshot/parametry/wersję kodu. Trwałość po nowej instancji store.
- F02: ręcznie policzony fixture potwierdza ACT/365F, znak kosztu, sumy,
  stałe stopy, opóźniony repricing, beta=0/1 i podłogę; szok 0 daje delta0.
- F03: czyste saldo uzgadnia się, celowa rozbieżność daje blocked; konta tylko
  po jednej stronie nie giną; duplikaty i NaN odrzucane.
- F04: anomalia wykryta regułą z danych przeszłych; przyszłe wartości nie
  zmieniają wcześniej obliczonych sygnałów. Jawna etykieta reguła.
- F05: prawdziwy subprocess/API zapisuje wynik, blokuje równoległe zadania,
  bezpiecznie raportuje błąd/timeout; restart nie udaje sukcesu. Obcy projekt
  nie pobiera wyniku przez swoją trasę. Guard i stare regresje zachowane.
- F06: UI przechodzi od parametrów do wyników i eksportu, pokazuje loading,
  błąd i historię; zmiana projektu nie miesza wyników. NII różni się od zysku,
  dane są oznaczone syntetyczne; jakość blocked widoczna przy kwotach.
- F07: przegląd platform i decyzja architektoniczna mają źródła, odróżniają
  dostępne produkty od komponentów oraz docelową platformę od lokalnego demo.

Plan testów: engine unit cases z ręcznymi kwotami, API z tymczasowym store
i prawdziwym subprocess, failure/recovery, frontend interakcje i realbrowser
smoke. Regresja istniejących demo backend/frontend, lint/types/build i linki.
Rollback: cofnięcie plików nowego modułu i rejestracji tras; nowe finance.sqlite
pozostaje zachowane, stary torii.sqlite i dane ML nie wymagają migracji.
