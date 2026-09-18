# Model domenowy i odtwarzalność

Status: Draft; pojęcia i inwarianty do akceptacji przed schematem bazy/API.
Powiązane: [ADR-0002](../../adr/0002-git-and-authority.md),
[ADR-0003](../../adr/0003-reproducibility-and-releases.md).

## Trzy różne tożsamości

**Obiekt** ma trwałe ID, typ, projekt, nazwę, właściciela i politykę dostępu.
Zmiana nazwy nie zmienia ID. **Wersja** jest niezmiennym opisem konkretnego
stanu definicji lub zawartości. **Wykonanie** wskazuje wersje wejściowe,
rzeczywiste środowisko, aktora, stan, próby oraz wyjścia.

Roboczy draft może być edytowany z kontrolą współbieżności. Opublikowana wersja
nie jest nadpisywana. Nazwy, tagi i aliasy służą nawigacji, nie identyfikacji
historycznej. Zmiana ACL nie tworzy nowej wersji danych: jest audytowaną zmianą
polityki, która obowiązuje także przy odczycie starszych wersji.

Wspólna koperta obiektu nie oznacza jednej tabeli z dowolnym JSON-em.
Każdy typ ma własny walidowany kontrakt i reguły. Relacje kluczowe dla
uprawnień, wersjonowania i spójności muszą być ograniczeniami modelu/bazy.

## Katalog bytów

| Byt | Odpowiedzialność i powiązania |
|---|---|
| Organization, Principal, Team, Project | Granica organizacyjna, aktor człowiek/usługa, członkostwo, własność; pierwsze wdrożenie jednej organizacji, nie SaaS multi-tenant |
| Connection / ConnectionRevision | Definicja dostępu do systemu oraz referencja do sekretu; osobne wiązanie dla środowiska; nigdy hasło w definicji |
| Dataset / DatasetDefinitionVersion | Logiczny zbiór i sposób uzyskania danych: plik, tabela, zapytanie, API; format i parametry źródła |
| DatasetVersion | Konkretny snapshot lub wersja gwarantowana przez źródło, schema, manifest plików, pełne digesty, wielkość, pochodzenie, retencja |
| Transformation / TransformationVersion | Operacja Python/SQL/deklaratywna, wejścia/wyjścia, kod, parametry, runtime i testy kontraktu |
| Flow / FlowVersion | Graf zależności z wersjonowanymi węzłami i portami; pierwszy zakres to DAG, bez dowolnych cykli |
| Model / ModelVersion | Pakiet obliczeniowy z kontraktem i capabilities; kod reguł, model ML, statystyczny, symulacyjny lub optymalizacyjny |
| Experiment | Kontekst porównania prób, protokół ewaluacji, wersje danych i powiązane runy; metryki/parametry w MLflow |
| Analysis / AnalysisVersion | Definicja EDA, ewaluacji, XAI, testu wrażliwości albo raportu; metoda, konfiguracja i wymagane wejścia |
| Artifact | Niezmienna zawartość danych/modelu/raportu/logu, typ MIME, rozmiar, digest, lokalizacja z wersją magazynu |
| Run / StepRun / RunAttempt | Wykonanie Flow lub operacji, zależności, wersje, tożsamości, logi, stany; retry ma nową próbę, nie usuwa historii |
| Release / Approval / Deployment | Zamrożony pakiet, decyzja dla jego digestu oraz wdrożenie do konkretnego środowiska |
| AuditEvent | Kto, kiedy, co, na czym, z jakim skutkiem i kontekstem żądania; polityka przechowywania i eksportu |

`AnalysisResult` jest wynikiem runu analizy, zawierającym referencje do raportów
i innych artefaktów. `TransformationRun`, trening, predykcja i symulacja są
typami wykonania, a nie konkurencyjnymi systemami historii.

## Kontrakt danych

- Plik lokalny po zaimportowaniu nie jest wskazaniem `C:\...` dostępnym tylko
  autorowi: powstaje zarządzana kopia, chyba że polityka jawnie zabrania eksportu.
- Konektor deklaruje możliwości: schema/preview/snapshot/source-version,
  stronicowanie, partycjonowanie, limity i dostępne gwarancje spójności.
- Zapytanie ma wersjonowany tekst, parametry, wersję definicji połączenia,
  czas odczytu i opis izolacji. Sam tekst SQL nie jest wersją danych.
- Domyślnie konektor SQL utrwala wynik odczytu jako snapshot. Wielostronicowy
  odczyt wymaga spójnego snapshotu transakcyjnego lub jawnego oznaczenia
  ograniczonej spójności. Nie przedstawiamy mieszanki stanów jako jednego obrazu.
- Zewnętrzna wersja, np. snapshot tabeli, zastępuje kopię tylko przy sprawdzonej
  retencji i prawach odczytu. Wygaśnięcie wersji odbiera gwarancję replay.
- Schemat, jakość, klasyfikacja i statystyki są wersjonowane lub przypięte do
  wersji, której dotyczą. Preview nie jest automatycznie publicznym artefaktem.
- Nowy format nie musi być tabelą. Wspólne są identyfikacja, przechowywanie,
  uprawnienia i provenance; specyficzne operacje określa adapter.

Publikacja: staging upload → weryfikacja rozmiaru/digestu → finalizacja manifestu
i metadanych. Przerwany upload nie tworzy gotowej DatasetVersion. Sprzątanie
osieroconych plików jest osobnym procesem z okresem ochronnym i kontrolą referencji.
Dedup działa w granicy dozwolonego zakresu, bez ujawniania istnienia cudzych danych.

## Transformacje i modele

Moduł Python może być zwykłą funkcją z jawnymi wejściami, wyjściami i parametrami.
SDK dostarcza kontekst, nie wymusza zależności całej logiki biznesowej od GUI.
Kod, specyfikacja portów, walidacja parametrów i środowisko są częścią wersji.
Deklaratywne transformacje GUI mają ten sam walidowany format co wersje z Git.

Model deklaruje obsługiwane działania, np. `predict`, `score`, `simulate`,
`optimize`, opcjonalnie `fit` i `explain`. Każde działanie ma własny kontrakt
wejść/wyjść i błędów. Brak capability daje jawne „nieobsługiwane”, nie pusty
wynik. Model regułowy może mieć wersję bez żadnego treningu.

Adapter MLflow jest właściwy dla kompatybilnych modeli; nie wciskamy symulacji
lub optymalizacji na siłę w `predict`. Kontrakt wykonania kontenerowego może
obsługiwać pozostałe rodzaje. Pierwszy przyrost weryfikuje ML i reguły;
pozostałe capabilities muszą mieć specyfikację przed dodaniem implementacji.

XAI przypina model, badany zbiór, zbiór tła/referencyjny, metodę i jej wersję,
parametry oraz runtime. Porównanie modeli przypina ten sam protokół i zbiór
oceny; nie porównuje bez ostrzeżenia metryk policzonych na różnych danych.

## Provenance i poziomy odtworzenia

Manifest wykonania obejmuje: project/flow/version, zależności kodu z commitami
i digestami, konfigurację bez sekretów, snapshoty danych, model i metodę,
obraz OCI po digescie, lock zależności, wersje adapterów, ziarna losowe,
istotny sprzęt/runtime, actor/service identity, środowisko i wersję polityki.
Wykonanie produkcyjne wskazuje też release, approval i deployment.

Plan Flow może odwoływać się do przyszłych wyjść swoich kroków. Każdy krok
przed obliczeniami rozwiązuje te referencje do gotowych, konkretnych wersji
i utrwala własny manifest wejściowy. Końcowy manifest Runu zbiera wykonane
zależności; nie zakładamy, że ID wszystkich przyszłych wyjść są znane na starcie.

Rozróżniamy dwie cechy, zamiast jednej mylącej flagi `reproducible=true`:

| Wymiar | Wartości i znaczenie |
|---|---|
| Dostępność replay | `available`: zależności utrwalone i dostępne; `conditional`: zależność zewnętrzna nie ma gwarancji; `unavailable`: brak wymaganej zależności |
| Porównanie wyników | `bitwise`: identyczne bajty; `numerical`: zgodność według uprzednio ustalonej tolerancji; `not_verified`: brak próby |

Ponowne uruchomienie tworzy nowy Run powiązany z oryginałem. Nie zmienia wyniku
historycznego. Lokalny runner przed wykonaniem sprawdza manifest, prawa dostępu
i kompatybilność platformy. Gdy nie może spełnić kontraktu, podaje konkretną
przyczynę; nie podstawia automatycznie „najnowszych” danych/pakietów.

Praca lokalna z dostępem do firmowego magazynu, dokładny replay i eksport w pełni
offline to różne funkcje. Pierwszy zakres obejmuje dwie pierwsze, jeśli pozwala
polityka danych. Eksport offline wymaga osobnej zgody i specyfikacji.

Lineage rozróżnia graf zadeklarowany od wykonanych zależności. Wynik wskazuje
rzeczywiste wejścia i próbę, a nie tylko to, co widniało na planszy Flow.
Retencja/delecja zostawia tombstone i zmianę dostępności replay, nie fałszuje
historii. Danych objętych zakazem usunięcia nie usuwa sam garbage collector.

## Git i środowiska

Repozytorium platformy zawiera Torii. Repozytorium projektu analitycznego
zawiera wiele modułów, notebooki, testy, deklaracje obiektów i Flow oraz lock.
Stabilne ID w deklaracjach przetrwają rename/merge. Wspólny, niezależnie
wydawany kod może być pakietem w osobnym repozytorium; nie każdy węzeł Flow.

GUI ma working copy przypisaną do użytkownika i gałęzi. Drafty nie są ukrytą
drugą wersją głównej gałęzi. Użytkownik widzi diff, walidację, commit i push.
Konflikt wymaga rozwiązania; platforma nie robi cichego force-push ani nie
nadpisuje cudzej edycji. Import nie wykonuje Git hooks ani kodu repozytorium.

Run eksperymentalny z dirty worktree wymaga zapisanej paczki źródeł i digestu,
oznaczenia dirty oraz reguły retencji; bez tego nie obiecuje replay.
Release wymaga zatwierdzonego, czystego commita i zachowanych artefaktów builda.
Samo istnienie commita na zewnętrznym serwerze nie gwarantuje jego retencji.

Cykl pracy: draft → wersja → eksperyment → kandydat wydania → przegląd.
Środowisko: dev / test / prod. Nie mieszamy tych osi w jednej etykiecie statusu.
Release zamraża kod i konfigurację; może przy każdym uruchomieniu odczytywać
nowe dane produkcyjne, ale Run przypina ich faktycznie użyte wersje.
