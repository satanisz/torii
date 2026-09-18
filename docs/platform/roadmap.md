# Plan realizacji i bramki decyzji

Status: Draft. Etapy oznaczają zależności i dowody, nie obietnicę terminu.
Estymacja nastąpi po kontraktach pierwszego przyrostu i próbach technicznych.

Rozpisanie na przyrosty infrastruktury, backendu i frontendu zawiera
[plan sprintów](sprint-plan.md). S0–S6 to etapy produktu, a SP-00–15 to
prognozowane cele iteracji; nie są to dwa równoległe harmonogramy.

## Etapy

| Etap | Zakres | Warunek wyjścia |
|---|---|---|
| S0 — baseline projektowy | Ten pakiet, przegląd wymagań/ADR, specyfikacja pierwszego przyrostu i pytania techniczne | Zaakceptowane granice i kompletna Accepted SPEC-0001; obecnie niespełnione |
| S1 — tożsamość i katalog wersji | OIDC testowy, projekty/grants, typowany rdzeń obiektów, wersje definicji, audyt, API, minimalny UI; CI według osobnej mini-SPEC | Dwie osoby współpracują, obca osoba nie widzi projektu; wersje niezmienne, konflikt nie nadpisuje pracy; AC ze SPEC-0001 przechodzą |
| S2 — dane, transformacja, wykonanie | S3 snapshoty, CSV/Parquet + read-only SQL, konektor, Python/SQL transformation, jakość, izolowany runner, próby/retry, manifest i lineage | Zmienione źródło nie psuje replay starego runu; awaria w połowie publikacji nie tworzy gotowego wyniku ani duplikatu |
| S3 — Flow, Git i praca lokalna | Edytor/lista DAG, wersje portów, prywatne working copies, diff/commit/push, import, CLI/SDK i Jupyter | Ten sam projekt działa z GUI i po clone; konflikt Git jest jawny; lokalny replay wskazuje zgodność lub przyczynę odmowy |
| S4 — modele i analizy | MLflow przez bezpieczną integrację, jeden model ML i regułowy, porównanie, EDA/ewaluacja/XAI, raporty | Brak wymagania `fit` dla reguł; model ma przypiętą wersję, raport ma pełne wejścia; SDK nie omija ACL |
| S5 — kontrolowane wydania | Release bundle, zgody, mapowanie połączeń dev/test/prod, wdrożenie batch, harmonogram, rollback | Autor nie zatwierdza własnej zmiany; nowe dane prod zapisane jako wersje wejścia; rollback nie udaje cofnięcia skutków w danych |
| S6 — kwalifikacja pilotażu | Firmowy IdP/sekrety/runtime, izolacja, TLS, retencja, restore, wydajność, supply chain, monitoring i odbiór bezpieczeństwa | Uzgodnione NFR spełnione na docelowej topologii, właściciele operacyjni wskazani, zgoda na konkretny pilotaż |

S1–S5 realizujemy z kontrolami bezpieczeństwa właściwymi danemu przyrostowi.
S6 jest kwalifikacją istniejących kontroli w realnym środowisku, a nie etapem
„dodajemy bezpieczeństwo”. Pierwszy pełny demonstrator kończy się na S5;
przydatność do rzeczywistych danych firmy wymaga również S6.

Nie budujemy najpierw wszystkich ekranów na mockach. Każdy przyrost dodaje
małą ścieżkę przez domenę, API, trwały stan, interfejs i testy. Sam prototyp UI
może służyć przeglądowi UX, ale nie jest ukończeniem funkcji.

## Scenariusz odbioru całego przekroju

Dane syntetyczne procesu operacyjnego; żadnych rzeczywistych danych firmy.
Przykład: przewidywanie opóźnienia dostawy i prosty model regułowy dla tego
samego celu. Historyczny przykład AutoGluon zostaje testem referencyjnym.

1. Właściciel tworzy projekt P1; autor A, recenzent B i operator C otrzymują
   oddzielne uprawnienia. Użytkownik E projektu P2 nie widzi danych P1.
2. A rejestruje CSV oraz zapytanie PostgreSQL, utrwala wersje, przegląda schema
   i jakość. Transformacja łączy dane i publikuje Parquet.
3. A buduje Flow, zapisuje deklaracje oraz moduły w repozytorium projektu,
   robi jawny commit i uruchamia eksperyment z GUI.
4. Model ML i model regułowy tworzą wersje. Eksperyment zapisuje wspólny zbiór
   oceny, metryki i protokół. Powstaje analiza XAI dla obsługiwanego modelu.
5. B otwiera raport, konkretne wejścia i lineage. Dostęp do raportu nie
   nadaje sam z siebie prawa do pobrania zbioru treningowego.
6. Zmiana wejścia i transformacji daje nowe wersje. Replay wcześniejszego Runu
   z lokalnego clone używa starych wejść i ustalonego runtime.
7. Konflikt równoległej edycji nie gubi pracy. Odebranie uprawnienia blokuje
   kolejne operacje z GUI, SDK i notebooka.
8. Restart workera i powtórzony komunikat nie publikują podwójnego wyniku;
   niedostępny katalog nie gubi historii runu, projekcja dogania po awarii.
9. A zgłasza release. A nie może sam go zatwierdzić. B zatwierdza digest,
   a C wdraża go do odrębnego testowego środowiska o politykach prod.
10. Run wydania używa nowej partii danych, zapisując jej konkretne wersje.
    Zmiana aliasu MLflow lub gałęzi nie zmienia używanego kodu/modelu.
11. C przywraca poprzednie wydanie; UI wyjaśnia, że już opublikowane dane nie
    zostały magicznie cofnięte. Każda decyzja pozostaje w audycie.
12. Z backupu przywracamy odizolowaną instalację, sprawdzamy relacje/digesty
    i wykonujemy replay. Usunięte zgodnie z polityką wejście daje jawny brak
    możliwości replay, bez pobierania najnowszego zamiennika.

## Najbliższa kolejność pracy specyfikacyjnej

1. Przegląd tego baseline i ADR-0001/0002/0003 przez właściciela produktu.
2. Doprecyzowanie SPEC-0001: macierz operacji i ról, OpenAPI/JSON Schema,
   schemat relacyjny z ograniczeniami, model rewizji i finalizacji, przykłady
   poprawne/niepoprawne i lista testów. Następnie review i akceptacja.
3. Krótka specyfikacja CI/review/migracji, wskazanie recenzenta i zasad merge.
4. Dopiero po Ready: implementacja S1 w małych, sprawdzalnych zmianach.
5. SPEC-S2 przed workerem, snapshotami i konektorami; pozostałe etapy otrzymują
   własne numery SPEC, kiedy zostaną rozbite na przyrosty.

`SPEC-S2` jest tu nazwą rodziny prac etapu, nie istniejącym dokumentem
ani zaakceptowanym kontraktem. W [rejestrze specyfikacji](../../specs/README.md)
odpowiadają jej rezerwacje SPEC-0003/0004/0005. Nie tworzymy pustych
„zaakceptowanych” ticketów.

## Decyzje i próby techniczne

| ID | Decyzja | Rekomendacja / kryterium rozstrzygnięcia | Kiedy |
|---|---|---|---|
| D-01 | Miejsce rozwoju | Obecne repo Torii, nowy rdzeń poza scaffold; ADR-0001 | S0 |
| D-02 | Repozytoria i źródła prawdy | Repo platformy + repo na niezależny projekt; ADR-0002 | S0 |
| D-03 | Snapshoty i wydania | Nie nadpisujemy wersji; pin wszystkich zależności, ADR-0003 | S0 |
| D-04 | Pierwszy kontrakt uprawnień/tożsamości | OIDC testowy, grants per projekt; role są zbiorem operacji, nie warunkiem w UI | Przed Accepted SPEC-0001 |
| D-05 | Wersjonowanie definicji i konkurencja | Draft z revision/ETag; finalizacja atomowa z audytem; typowane schema | Przed Accepted SPEC-0001 |
| D-06 | Execution backend | Próba Dagster i prostego runnera: izolacja, retry, cancel, odzyskanie, dynamiczne projekty, narzut operacyjny | Przed Accepted SPEC-S2 |
| D-07 | Publikacja snapshotów | Próba finalizacji po awarii, ochrony przed nadpisaniem, retencji i spójnego odczytu SQL | Przed Accepted SPEC-S2 |
| D-08 | MLflow i autoryzacja | Test API/SDK i pobrania modelu z dwóch projektów; wykluczyć obejście praw przez tracking/artifact endpoints | Przed S4 |
| D-09 | DataHub | Opcjonalna projekcja, mapowanie własności pól, brak zależności wykonania od dostępności katalogu | Przed adapterem |
| D-10 | Środowisko firmy | IdP, scheduler, magazyn, KMS/sekrety, sieć/registry i granice dev/prod | Przed S6 i prawdziwymi danymi |

Każda próba techniczna ma krótką specyfikację, dane syntetyczne, limit pracy,
wyniki i ADR. Przykładowy limit to jedna uzgodniona sesja badawcza; przekroczenie
wymaga decyzji, nie cichego rozrostu zakresu. Nie wykonano jeszcze tych prób.

## Główne ryzyka projektu

- Zakres „zastępujemy Databricks” może rosnąć bez końca: akceptujemy konkretne
  procesy, skalę i braki; nie traktujemy wszystkich funkcji konkurencji jako backlogu.
- Kod użytkownika i modele to wykonywalne, potencjalnie niebezpieczne artefakty:
  izolacja jest bramką runnera, nie kosmetyką deploymentu.
- Dublowanie katalogów i historii: rozstrzyga ADR-0002 oraz test reconciliation.
- MLflow SDK może omijać nowy interfejs: przed integracją wymagany dowód izolacji.
- Retencja danych może uniemożliwić replay: jawne poziomy gwarancji i polityka
  przechowywania zamiast obietnicy bezterminowej reprodukcji.
- Obecny stos demonstracyjny ma duży narzut usług: DataHub opcjonalny, pomiary
  przed doborem infrastruktury; brak automatycznej decyzji „wszystko na Kubernetes”.
- Brak zespołu operatorów i niezależnych recenzentów nie zostanie naprawiony
  dokumentacją ani automatycznym generowaniem kodu.

## Czego potrzebujemy od właściciela produktu

Teraz: przeglądu i akceptacji kierunku oraz pierwszego zakresu, po uzupełnieniu
kontraktów. Nie trzeba teraz uruchamiać chmury, Databricks ani kupować usług.
Szczegóły techniczne przygotowujemy jako rekomendacje z uzasadnieniem.

Przed firmowym pilotażem: wskazania pierwszego procesu i właściciela danych,
klasyfikacji/retencji, skali i krytyczności, firmowego IdP/infrastruktury,
recenzenta bezpieczeństwa i operatora. Bez tego można ukończyć demonstrator,
ale nie można uczciwie zatwierdzić wdrożenia enterprise.
