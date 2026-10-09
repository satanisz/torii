# Laboratorium finansów banku w Torii

Laboratorium pokazuje analizę NII na syntetycznym wycinku portfela i księgi
głównej. Wybierasz scenariusz stóp, oglądasz miesięczny wynik odsetkowy,
wkład pozycji portfela, uzgodnienie sald i historyczne sygnały anomalii.
To pierwszy przyrost kierunku opisanego w [porównaniu platform](platform/banking-finance-research.md).

## Uruchomienie

W katalogu repozytorium Torii, przy zależnościach opisanych w
[instrukcji demo](../apps/demo/README.md):

```powershell
.\scripts\demo.ps1
```

Otwórz [Torii Finanse banku](http://127.0.0.1:18440/?view=finance).
Utwórz projekt, jeśli lista jest pusta, i wybierz zakładkę **Finanse banku**.
Nie trzeba dodawać zbioru regresyjnego, tworzyć modelu ML ani uruchamiać Dockera.

Jeśli demo było uruchomione przed aktualizacją kodu, poczekaj na koniec
wykonywanych analiz, a następnie użyj `-Action Stop` i `-Action Start`.
Launcher zachowuje dane i odmawia zatrzymania przy aktywnym wykonaniu.

## Pierwsza analiza

1. Pozostaw szok **+100 pb** (wzrost o 1 punkt procentowy) i beta depozytów **0,35**.
2. Uruchom analizę na czystych danych. Uzgodnienie porównuje salda portfela
   z odpowiadającymi kontami GL, a raport pokazuje bazowy i scenariuszowy NII.
3. Obejrzyj miesięczną zmianę i wkład pozycji. Stała stopa nie reaguje na szok;
   zmienna reaguje od wskazanego miesiąca przeszacowania. Beta 0,35 oznacza,
   że +100 pb przekłada się na +35 pb dla objętych nią depozytów.
4. Zmień szok na **0 pb**. Nowe wykonanie powinno dać zmianę NII równą zero.
5. Włącz zestaw z celową rozbieżnością. Uzgodnienie wskaże niezgodne saldo,
   a wynik będzie oznaczony jako roboczy z nieuzgodnionych danych. Osobna
   reguła wskaże celowo nietypową zmianę historycznego NII.
6. Przełącz poprzednie wykonania i pobierz eksport JSON. Zawiera wejścia,
   scenariusz, wynik, identyfikatory i hashe metody/danych. Parametry nowego
   wykonania nie zmieniają wcześniejszych raportów.

## Jak rozumieć wynik

NII jest różnicą przychodów i kosztów odsetkowych. Nie obejmuje pełnego zysku
netto banku: prowizji, kosztów działania, odpisów i podatków.

Data portfela: 2026-09-30. Projekcja: październik 2026 – wrzesień 2027.
Waluta: PLN. Konwencja: ACT/365F, rzeczywiste dni miesiąca podzielone przez 365.
Obliczenia używają Decimal i zaokrąglenia do groszy na pozycji i miesiącu.
Roczna suma jest sumą tych kwot; nie jest oddzielnym rocznym zaokrągleniem.

Salda pozostają stałe, pozycje nie zapadają w horyzoncie. Pomijamy nową
sprzedaż, amortyzację, opcje, FX, hedging, EIR/IFRS9 i modele behawioralne.
Beta jest zadaną wrażliwością, a nie wyestymowanym zachowaniem klientów.
To warunkowa projekcja NII przy założonym szoku, nie prognoza przyszłych stóp
ani regulacyjny pomiar IRRBB. Dokładną formułę zawiera
[SPEC-0019](../specs/0019-bank-finance-lab/README.md).

Anomalie są sygnałami regułowymi: NII miesiąca porównujemy z medianą
poprzednich sześciu miesięcy oraz progiem opartym na MAD i minimalnej kwocie.
Nie jest to wytrenowany model ML, rozstrzygnięcie księgowe ani dowód nadużycia.

## Trwałość i zakres

Historia finansowa jest w `apps/demo/.local/data/finance/finance.sqlite`,
a pliki wykonania w `finance/runs/`. Znajdują się w lokalnym, ignorowanym
magazynie demo. Obecny `torii.sqlite` i artefakty regresji pozostają odrębne.
Eksport finansowy jest osobny od przycisku eksportu projektu regresyjnego.

Demo jest jednoosobowe, dostępne na loopback, bez SSO i niezależnego
zatwierdzania. Nie należy używać w nim rzeczywistych danych banku.
Planowane konektory do baz, praca wielu osób, pełne harmonogramy kontraktowe,
P&L i modele prognozowania wymagają kolejnych specyfikacji i odbiorów.
