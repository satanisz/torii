# Plan sprintów platformy obiektów Torii

Rewizja 0.2, 2026-10-10. Status: **plan proponowany po korekcie kierunku**.
Ta rewizja zastępuje kolejność rewizji 0.1. Zachowujemy istniejące ID SP,
SPEC i zadań, a dotychczasowe dowody pozostają w [dzienniku](delivery-progress.md).
Numer SP oznacza zakres backlogu; kolumna „Kolejność” określa proponowane wykonanie.

Użytkownik chce platformy enterprise z katalogiem danych, transformacji,
eksperymentów oraz grafem zależności. Potwierdził nowoczesny stos, nie edge
computing. Zlecenie dotyczy planu; nie wznawia implementacji ani automatyzacji.
Nowe kontrakty przechodzą SDD przed kodem, bez zmiany statusów Accepted na podstawie
samego planowania. Kierunek: [architektura obiektów](enterprise-object-platform.md),
[ADR-0006 Proposed](../../adr/0006-object-catalog-and-lineage.md).

## Co zmienia się w dostarczaniu

- Domyślny ekran projektu: katalog, graf i inspektor wybranej wersji.
- Graf deklarowanych zależności w SP-02, faktyczne snapshoty w SP-03,
  historia wykonania w SP-04; edytor wykonywalnego Flow w SP-06.
- Minimalny eksperyment SP-10A przed rozbudowanym sharing/Git/Jupyter.
  Pełny SP-10 wymaga również SP-10B; część A nie zalicza całej specyfikacji.
- Finanse banku to pierwszy proces użytkowy na wspólnych obiektach platformy.
  SPEC-0019 pozostaje lokalnym laboratorium i źródłem fixture, bez migracji teraz.
- Każdy przyrost obejmuje bazę/API, działający UI i dowody. Nie odkładamy
  całego interfejsu na koniec prac infrastrukturalnych.

## Stan i realny początek

SP-00 dostarczył kontrakty i baseline; nie zaczynamy go od nowa. SP-01 jest
częściowo zrealizowany, bez pełnego odbioru. Istnieją komponenty sesji/OIDC,
projekty/grants/audyt w PostgreSQL, klient web oraz osobny stos dev/test.
HTTP enterprise nadal udostępnia tylko health/live i health/ready. Ostatnim
udokumentowanym przyrostem tożsamości jest B2a4a; następne są B2a4b, orchestration,
trasy auth/session/projects i realne E2E. SP-02–15 nie mają dowodów pełnego odbioru.
Demo SPEC-0018/0019 ma osobny runtime i nie zalicza tych sprintów.

## Kolejność i odbiór przyrostów

Każdy wiersz jest planowanym celem iteracji, nie obietnicą zmieszczenia całego
zakresu w dwóch tygodniach. Zbyt duży cel dzielimy na mniejsze pionowe przyrosty
przed zobowiązaniem, zachowując nadrzędne SP i wszystkie wymagane kryteria.

| Kolejność | Zakres SP | Rezultat widoczny dla użytkownika | Zależności | Dowód końca |
|---|---|---|---|---|
| 1 | SP-01 domknięcie | Logowanie, projekty, rzeczywiste prawa, powłoka robocza | Istniejący baseline; spec brakujących części B2 | A tworzy projekt, B ma przyznany odczyt, E nie odczytuje go przez UI/API; restart i logout działają |
| 2 | SP-02 | Katalog Dataset/Transformation, draft, wersje/diff, graf deklaracji i inspektor | SP-01; rewizje SPEC-0001/0017 | v2 nie zmienia v1; konflikt nie gubi tekstu; lista i graf ujawniają ten sam dozwolony zakres |
| 3 | SP-03 | Import CSV/Parquet, niezmienne snapshoty, schema/preview, pochodzenie importu | SP-02; Accepted SPEC-0003 | Zmieniony plik daje v2; v1 dostępna; przerwany upload nie tworzy gotowego snapshotu |
| 4 | SP-04 | Jedna wersjonowana transformacja w izolowanym zadaniu; Run/Attempt, logi, lineage | SP-03; Accepted SPEC-0004 i próba adaptera | Ze zmiany kodu powstaje nowe wykonanie; crash/retry nie dubluje opublikowanych wyjść, stary worker nie finalizuje |
| 5 | SP-06 | Wykonywalny Flow na plikach: porty, walidacja, plan, stany kroków | SP-04; Accepted SPEC-0006 | Dwa kroki mają przypięte realne wejścia; cykl odrzucony; zmiana Flow nie zmienia grafu historycznego Runu |
| 6 | SP-10A | Wersjonowany eksperyment, dwie próby, porównanie na tym samym protokole, MLflow | SP-04/06; Accepted wąski SPEC-0010 i bramka D-08 | Dane/kod/runtime/protokół przypięte; wynik prowadzi do źródeł; bezpośredni dostęp do metryk/artefaktów nie omija ACL |
| 7 | SP-05 | Źródło SQL read-only i jakość; księga/portfel jako zarządzane dane | SP-03/04, rozszerzenie Flow z SP-06; SPEC-0005 | Spójny snapshot zapytania, korekta źródła daje nową wersję, zapis SQL/niedozwolony host odrzucone |
| 8 | SP-07 | Zespoły i udostępnianie między projektami | SP-03/04/06; SPEC-0007 | Odbiorca ma tylko przyznane metadane/artefakty/wykonanie; cofnięcie grantu działa także w grafie |
| 9 | SP-08 | Git working copy, diff/import/commit i konflikty | SP-06/07; SPEC-0008 | GUI i clone/import zachowują ID/wersje; brak cichego force-save oraz wykonywania hooks |
| 10 | SP-09 | SDK/CLI, replay i izolowany Jupyter | SP-08 i wykonania; SPEC-0009 | Te same obiekty/prawa co GUI; replay tworzy nowy Run i wskazuje zgodność lub konkretny brak |
| 11 | SP-10B | Pełny rejestr ModelVersion, ML i nie-ML, capabilities i sharing modeli | SP-10A/07/09; pozostały SPEC-0010 | fit opcjonalne; predict/simulate mają jawny kontrakt; dostęp do modelu nie daje dostępu do treningowych danych |
| 12 | SP-11 | Analizy/ewaluacje/XAI i raport finansowy jako wynik wspólnego Runu | SP-05/10B; SPEC-0011 | Raport wskazuje dane, metodę, scenariusz i wersje; NII/reguły z demo przeniesione dopiero z testami kontraktu/metodyki |
| 13 | SP-12 | Zamrożony release i niezależna decyzja dla digestu | SP-08/10B/11; SPEC-0012 | Autor nie zatwierdza własnego wydania; zmieniony pakiet wymaga nowej decyzji |
| 14 | SP-13 | Wdrożenie batch, środowiska, harmonogramy i rollback | SP-12; SPEC-0013 | Uruchamia się zatwierdzony pakiet, nowe wejścia mają wersje; rollback kodu nie udaje cofnięcia danych |
| 15 | SP-14 | Próbna migracja dziedzictwa i mapowanie ID | SP-13; SPEC-0014 | Import powtarzalny na kopii; stare dane/artefakty zachowane, brak dopisanych historycznych approvals |
| 16 | SP-15 | Kwalifikacja uzgodnionego pilotażu firmowego | SP-13/14; SPEC-0015 | Firmowy IdP, izolacja, restore/DR, wydajność, monitoring i odbiór właścicieli na docelowej topologii |

SP-06 może wystartować bez SQL: pierwsze wejścia są plikami. SP-05 później
rozszerza ten sam kontrakt Flow. SP-10A jest ograniczony do jednego projektu,
z prawami egzekwowanymi już w SP-01–04. Cross-project sharing i pełny rejestr
pozostają w SP-07/10B. Manifest kodu i OCI jest wymagany od SP-04; odłożenie
panelu Git/Jupyter nie pozwala uruchamiać nieprzypiętego kodu.
Model wytrenowany w SP-10A od razu stanowi niezmienny Artifact z digestem
i pochodzeniem. SP-10B dodaje pełny rejestr ModelVersion; wcześniejszy zakres
nie zapisuje modelu wyłącznie pod zmiennym aliasem.

## Pierwsze trzy sprinty do refinementu

Szczegółowe karty: [SP-01](sprints/01-foundation.md),
[SP-02](sprints/02-object-versions.md), [SP-03](sprints/03-data-snapshots.md).
Wspólne obowiązki: implementator kontraktu, implementator UI/adaptera oraz
niezależny recenzent techniczny. To role pracy, nie założenie trzech etatów.
Konkretny owner i estymata każdego zadania powstają przy wyborze do realizacji.

| Sprint | Zadania krytyczne przed odbiorem | Ryzyko do rozstrzygnięcia |
|---|---|---|
| SP-01 | Spec brakującego transportu OIDC, orchestration, cookie/CSRF i trasy HTTP; integracja istniejącego UI; E2E wielu tożsamości i restore projektu | Nie powielić ukończonych komponentów; nie uznać mocków za działające SSO |
| SP-02 | Constraints/migracja obiektów, atomowe wersje, concurrency; katalog i diff; kontrakt relacji oraz autoryzowane API grafu; inspektor i lista | Oddzielić definicję od snapshotu, layout od relacji; bez wycieku nazw/liczników przez graf |
| SP-03 | SPEC storage i wybór S3 dev, staging/finalizacja, izolowany parser, manifest i retencja, preview, graf importu, awarie/migracja | Hash nazwy pliku nie wystarcza do niezmienności; przerwany import i schema preview nie omijają granicy zaufania |

SP-02 zachowuje wszystkie AC istniejącej SPEC-0001. Graf wymaga dopisania
kontraktów i kryteriów do nowej rewizji SPEC-0001/0017 przed implementacją;
obecna Accepted rewizja nie zawiera tego rozszerzenia. SPEC-0003 i dalsze
w większości są rezerwacjami w [rejestrze](../../specs/README.md), nie gotowymi
specyfikacjami. Nie nadajemy im statusu Ready przez wpisanie do tabeli.

## Decyzje techniczne i ograniczone próby

| Decyzja | Rekomendacja | Dowód przed zależnym kodem |
|---|---|---|
| UI grafu, SP-02 | React Flow; ELK jako kandydat układu | Jeden syntetyczny podgraf, inspektor, klawiatura/lista, limit i rozwijanie; ACL w API, nie w JS |
| Metadane, SP-02 | PostgreSQL, typowane i indeksowane relacje | Wersje i krawędzie mają constraints; historia nie zmienia się po edycji draftu |
| D-07 storage, SP-03 | S3 API, snapshoty/manifesty, pierwszy format Parquet/CSV | Niezmienność, awaria finalizacji, autoryzowany preview, polityka orphan/retention; wybór dostawcy i licencji dev |
| D-06 wykonanie, SP-04 | Dagster jako pierwszy kandydat adaptera | Crash/retry/cancel i mapping Run/Attempt; izolowany kontener; Torii pilnuje idempotentnej publikacji |
| Wymiana lineage, SP-04 | OpenLineage + transactional outbox | Powtórzone/opóźnione wydarzenia nie zmieniają historii; brak zależności od zewnętrznego katalogu przy commit Runu |
| D-08 tracking, SP-10A | MLflow z przypięciem do Run/ExperimentVersion | Per-project ACL w UI/API/SDK/artifacts; awaria publikacji metryk ma jawny stan i naprawę |
| D-10 środowisko, discovery przed pilotem | Istniejący dev/test; produkcyjny runtime firmy | Właściciele IdP, sieci, storage i utrzymania; warunki izolacji, RPO/RTO i NFR zatwierdzone przed testem |

Próba ma własny zakres, timebox i kryterium go/no-go w mini-SPEC. Nie jest
instalacją kilku konkurencyjnych platform. Ograniczenia Dagstera/OpenLineage
oraz źródła opisuje [architektura obiektów](enterprise-object-platform.md).
Nie rezerwujemy teraz hardware ani płatnych usług. Plan nie zakłada dużego
klastra, Kubernetes jest kandydatem runtime firmy, a nie warunkiem SP-01/02.

## Kamienie milowe i rytm pracy

- Po SP-02: użytkownik pracuje na katalogu i grafie prawdziwych definicji/wersji.
- Po SP-04: wynik transformacji ma kompletne pochodzenie danych i kodu.
- Po SP-06/10A: pierwszy przekrój zespołowy dane → Flow → eksperyment → wynik.
- Po SP-05/07–11: rozszerzony warsztat SQL/Git/SDK/Jupyter/modeli/analiz.
- Po SP-12/13: kontrolowane wydania i operacje batch.
- Po SP-14/15: kwalifikowany pilotaż na uzgodnionej infrastrukturze.

Proponowany rytm review to dwa tygodnie. Nie oznacza terminu „16 × 2 tygodnie”:
brak ustalonej pojemności zespołu i firmowych właścicieli odbiorów. Pierwsze trzy
przyrosty służą kalibracji czasu integracji, testów i poprawiania usterek.
Jeden główny przyrost w toku, równolegle spec następnego. Roboczo 60% pojemności
na funkcję, 20% integracja/review, 20% refinement i ryzyko; proporcje sprawdzamy
po SP-02. Nie podajemy punktów ani dat pozbawionych podstaw.

## Mapowanie wymagań

Identyfikatory i zakresy [FR](requirements.md) oraz [NFR](security-and-quality.md)
pozostają. Poniższe mapowanie określa miejsce dowodów, nie status PASS.

| Wymaganie | Przyrosty weryfikujące |
|---|---|
| FR-01 | SP-01/02, SP-07, SP-10A/B, SP-12/13 |
| FR-02 | SP-02/03, SP-10A/B, SP-11 |
| FR-03 | SP-03/05 |
| FR-04 | SP-02/04/05 |
| FR-05 | SP-04/06/13 |
| FR-06 | SP-10A/B |
| FR-07 | SP-11 |
| FR-08 | Graf SP-02, realne dane/wykonania SP-03/04/06/10A, rozszerzenia SP-05/09–13 |
| FR-09 | SP-08/09 |
| FR-10 | SP-12/13 |
| FR-11 | Każdy przyrost użytkowy SP-01–13; pełna ścieżka SP-15 |
| FR-12 | SP-01–04/07/09/12–15 |
| NFR-01 | SP-01 i każdy endpoint/graf/artefakt; test pełny SP-15 |
| NFR-02 | SP-03 parser, SP-04 worker, SP-09 notebook, SP-10A/B model, SP-15 |
| NFR-03 | SP-03–06/09–13 |
| NFR-04 | SP-01–04/12–15 |
| NFR-05 | Baseline katalog/graf SP-02, nowe obciążenia w swoich przyrostach; profil firmy SP-15 |
| NFR-06 | CI od SP-01, runtime SP-04/09/10A/B, release SP-12/13, kwalifikacja SP-15 |
| NFR-07 | Kontrakty przed kodem, Git/SDK SP-08/09, migracja SP-14 |
| NFR-08 | SP-01 correlation i zdrowie, SP-04 obserwowalność Run, SP-13/15 alerty i operacje |
| NFR-09 | Każdy przyrost danych; sharing/eksport/retencja SP-07/09/14/15 |
| NFR-10 | Każdy ekran; graf/lista SP-02, Flow SP-06, pełna ścieżka SP-15 |

## Warunki wejścia i ukończenia

Definition of Ready: Accepted rewizja SPEC dla faktycznego zakresu, kontrakty
API/stanów/uprawnień, zależności, właściciel, plan testów/awarii, migracji
i wycofania. Historia akceptacji nie obejmuje automatycznie nowego zakresu.

Definition of Done: wszystkie obowiązkowe AC z dowodami, migracja i restore
adekwatne do zmiany, lint/typy/kontrakty, negatywne testy dostępu, rzeczywista
baza/storage/worker oraz UI→API E2E. Testujemy konflikt, retry, brak danych,
częściową awarię i niedostępność zależności. Niezależny przegląd techniczny
jest warunkiem lokalnego odbioru; nie nazywamy go audytem banku ani release.

Każda karta zadania ma zachowane ID, ownera, SPEC/AC, zależności, rezultat,
ryzyko, dowód i rollback. Planned → Ready → In progress → Review → Verified;
Verified nie oznacza Production. Sprint nie kończy się samym działającym
obrazkiem grafu, backendem bez UI ani screenshotem bez trwałego wykonania.

## Ochrona obecnej pracy i granice

Plan nie zmienia kodu demo/enterprise, usług, `.env`, wolumenów, danych,
portów, zdalnych gałęzi ani PAUSED automatyzacji. Obecne lokalne zmiany
SPEC-0019 pozostają zachowane. Migracja demo wymaga mapowania do wspólnych
Object/Version/Run, nie kopiowania jego SQLite API i braku autoryzacji.

Pierwszy przekrój zespołowy ma pliki, Python/batch, graf, Flow i ograniczony
eksperyment. Pełny plan nadal zawiera SQL, Git/Jupyter, modele ML/nie-ML,
analizy/XAI, wydania i kwalifikację; przesunięcie kolejności ich nie usuwa.
DataHub/SPEC-0016 pozostaje opcjonalną projekcją po ustabilizowaniu kontraktów,
a brak tej usługi nie blokuje własnego katalogu. Streaming, własny warehouse,
GPU serving, pełny ALM i edytor IDE nie są ukrytym zakresem tych sprintów.

## Weryfikacja planu

Ta rewizja podlega kontroli odnośników, spójności zależności, mapowania FR/NFR
oraz niezależnemu przeglądowi architektury. Dowody tej kontroli trafiają do
[dziennika](delivery-progress.md). Nie są to testy nowego produktu ani odbiór
sprintów. Szczegółowe SPEC i próby pozostają pracą przed implementacją.
