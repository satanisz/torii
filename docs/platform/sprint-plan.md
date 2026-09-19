# Torii — plan sprintów: infrastruktura, backend i frontend

Rewizja 0.1, 2026-09-19. Status: **Draft planu dostarczania**.
Podstawa: [wymagania](requirements.md), [architektura](architecture.md),
[NFR](security-and-quality.md), [SDD](spec-driven-development.md).
Użytkownik potwierdził preferencję podejścia modułowego i przekazał logo.
Nie oznacza to akceptacji wszystkich ADR, kontraktów ani terminu dostarczenia.

## Zasady planowania

Aktualizacja priorytetu2026-09-19: użytkownik zlecił najpierw ręcznie testowalny
koncept i dopuścił ograniczenie zakresu. Osobny
[SPEC-0018](../../specs/0018-concept-demo/README.md) realizuje demo pionowe
CSV→transformacja→model→MLflow→wynik wGUI. Nie wymaga wcześniejszego ukończenia
SP-01–15 i nie zalicza ich enterpriseAC. Roadmapa poniżej zostaje celem docelowym.

Proponowany rytm: dwa tygodnie na iterację, ze wspólnym celem i demonstracją
wyniku. **Nie mnożymy liczby sprintów przez dwa tygodnie jako obietnicy terminu**:
nie znamy dostępnej przepustowości ani obsady review/utrzymania.
SP-00 jest iteracją specyfikacji i decyzji, nie sprintem kodowania produktu.

SP-00–02 mają [szczegółowe karty](sprints/00-contracts.md). SP-03–15 to
prognozowane cele do refinementu, nie zamrożone zobowiązanie wykonawcze.
Przed każdym sprintem wybieramy wyłącznie gotowe, zaakceptowane zakresy SPEC.
Jeśli zakres się nie mieści, zmniejszamy go lub dodajemy kolejną iterację;
nie skracamy testów ani nie wydłużamy sprintu pod gotową datę.

Infrastruktura, backend, frontend oraz QA/security to kompetencje i tory pracy,
nie założenie czterech dostępnych zespołów. Nie delegowano tu pracy ani nie
utworzono zewnętrznych zadań. Przy jednej osobie realizujemy zależności kolejno;
niezależna ludzka akceptacja wydania enterprise pozostaje wymogiem organizacyjnym.

Początkowo maksymalnie jeden główny przyrost w toku i jeden pakiet specyfikacji
na kolejny sprint. Roboczy budżet: do 60% pojemności na zmianę funkcji,
20% na integrację/testy/review, 20% na refinement i niepewność. To hipoteza do
korekty po SP-02, nie przelicznik godzin asystenta na etaty zespołu.
Nie wpisujemy arbitralnych story points przed rozbiciem zadań i kalibracją.

## Co dostarcza każdy sprint

Każdy wiersz to jeden cel zintegrowany. Zadania opisane poniżej są planowane,
żaden sprint implementacyjny nie jest rozpoczęty ani zaliczony.

| Sprint / etap | Cel | Infrastruktura | Backend | Frontend | Dowód na review |
|---|---|---|---|---|---|
| SP-00 / S0 | Kontrakty gotowe do pierwszego kodu | Topologia dev/test, izolacja od starego Compose, plan CI/sekretów/backupu | SPEC-0001, schemat bazy, OpenAPI, role, błędy, idempotencja | Architektura informacji, ekran projektu/obiektu, specyfikacja design systemu z logo | Przejście scenariuszy, walidacja kontraktów i jawna akceptacja; nie demo aplikacji |
| SP-01 / S1 | Zalogowany użytkownik pracuje w swoim projekcie | Osobne środowisko platformy, PostgreSQL, OIDC, CI i logi | Tożsamość, projekty, grants, audyt i health/readiness | Powłoka Torii, login/logout, lista projektów, brak dostępu | A widzi P1, E nie widzi P1 przez UI ani surowe API; restart nie gubi członkostwa |
| SP-02 / S1 | Definicje mają bezpieczne, niezmienne wersje | Migracje i restore fixture, testy konkurencji, regresja CI | Dataset/Transformation definitions, draft, wersje, archiwizacja | Katalog, formularz definicji, historia, porównanie i konflikt | Dwa klienty nie nadpisują edycji; retry finalizacji daje jedną wersję; pełne AC SPEC-0001 |
| SP-03 / S2 | Plik staje się wersją danych | S3, role per zakres, staging, izolacja parsera/preview, limity i retencja robocza | Import CSV/Parquet, manifest, digest, schema, preview | Upload, postęp, wybór wersji, schema i próbka | Zmieniony plik daje v2; v1 nadal dostępna; przerwany upload nie tworzy gotowej wersji |
| SP-04 / S2 | Wersjonowana transformacja Python wykonuje się niezależnie od UI | Worker poza API, limity, kolejka/lease, heartbeat i recovery | Run/Attempt, porty, finalizacja wyników, retry/cancel, lineage kroku | Edycja parametrów transformacji, uruchomienie, logi i próby | Restart/duplikat dispatch nie dubluje wyniku; stary worker i obcy projekt nie publikują |
| SP-05 / S2 | Zapytanie i jakość danych są częścią obiektu | Read-only konto SQL, kontrolowana sieć i sekrety, testowa baza źródła | Connection revision, spójny snapshot SQL, parametry, kontrakty jakości | Połączenia, formularz zapytania, walidacja i wyniki jakości | Zmiana tabeli nie zmienia poprzedniego snapshotu; zapis SQL i niedozwolony host odrzucone |
| SP-06 / S3 | Flow łączy rzeczywiste obiekty i wykonania | Izolacja wielu kroków, kolejki i limity projektu | DAG, wersje portów, walidacja cykli, plan i zależności kroków | Edytor Flow plus lista dostępna z klawiatury, stan kroków | CSV + SQL → transformacja → Parquet; historia prowadzi do rzeczywistych wersji wejść |
| SP-07 / S3 | Współdzielenie bez dziedziczenia nieuprawnionego dostępu | Delegacja krótkich tokenów, audyt dostępu do artefaktów | Zespoły i grants między projektami, rozdział read/download/execute | Udostępnianie, właściciel, zakres i cofnięcie praw | B widzi udostępniony wynik, lecz nie surowe dane; odebranie grantu blokuje kolejne operacje |
| SP-08 / S3 | Projekt analityczny jest zwykłym repo Git | Prywatne working copies, credentials per użytkownik, izolowany import | Manifesty, stable IDs, diff/import, commit/push i konflikty | Panel zmian, gałąź, diff, walidacja, konflikt | GUI → commit → clone/import zachowuje znaczenie i ID; repo nie wykonuje hooks przy imporcie |
| SP-09 / S3 | Ten sam projekt działa lokalnie i w Jupyter | Workspace per użytkownik, zasoby/TTL i polityka eksportu | SDK/CLI, manifest replay, weryfikacja runtime i dirty source bundle | Uruchomienie notebooka, stan workspace i raport replay | Lokalny run używa tych samych wersji; brak danych lub praw daje jawną odmowę, nie podmianę |
| SP-10 / S4 | Eksperymenty i modele ML oraz regułowe | Bezpieczny MLflow/artifacts, model execution poza API | Model capabilities, tracking, wersje, przypięta predykcja, rozszerzenie sharing | Rejestr modeli, eksperymenty, metryki i wybór konkretnej wersji | Reguły bez fit i model ML działają w tym samym katalogu; alias race i obejście ACL wykluczone |
| SP-11 / S4 | Analiza i XAI są odtwarzalnymi wynikami | Bezpieczne raporty/HTML, limity analizy i artefaktów | AnalysisVersion/Run, EDA, wspólny protokół oceny i jedna metoda XAI | Porównania, raport, parametry/metoda, lineage i brak capability | Raport wskazuje model, dane badane i tło; odmienne zbiory oceny nie są cicho porównywane |
| SP-12 / S5 | Wydanie jest zamrożone i niezależnie zatwierdzane | Rejestr buildów, podpis/provenance i kontrola publikacji | Release bundle, digest, polityka wejść, approvals i rozdział obowiązków | Diff wydania, kompletność dowodów i review | Autor nie akceptuje własnego wydania; modyfikacja pakietu wymaga nowej zgody |
| SP-13 / S5 | Kontrolowane uruchomienia batch i rollback | Odrębne środowiska/role/sekrety, scheduler, alerty | Deployment, harmonogram/strefa czasu, idempotencja wyzwalania, rollback | Widok środowisk, harmonogramów, zdrowia i cofnięcia | C wdraża zatwierdzony pakiet; nowe wejścia są wersjonowane, rollback nie udaje cofnięcia danych |
| SP-14 / S6 przygotowanie | Zachowane dziedzictwo i próbna migracja | Nowe docelowe zasoby, backup oraz środowisko próbnego restore | Import z mapowaniem historycznych ID i pochodzenia bez dopisywania approvals | Podgląd/diff importu, stan legacy i raport migracji | Oryginały niezmienione; import powtarzalny, historia zachowana, plan powrotu sprawdzony |
| SP-15 / S6 | Dowody gotowości do uzgodnionego pilotażu | Firmowy IdP, sieć, storage, monitoring, DR, skany i benchmark | Obsługa awarii, migracje i retencja na docelowej topologii | Pełny scenariusz wielu ról, dostępność i użyteczność | Uzgodnione NFR, restore/replay i przegląd security PASS; zgoda właścicieli na konkretny pilotaż |

Pełny zakres funkcjonalny demonstratora: po SP-13. Migracja dziedzictwa i
kwalifikacja wdrożenia: SP-14–15, mogą wymagać dodatkowych sprintów po odkryciach.
Zaangażowanie firmy i uzgodnienie topologii zaczynamy od SP-00; nie czekamy
z pytaniem o tożsamość, sieć i izolację do ostatniego sprintu.
DataHub ma osobną SPEC-0016 jako opcjonalna projekcja po SP-11. Brak tego
adaptera nie odbiera Torii własnego katalogu, lineage ani dowodów runów.
SP-03 potrzebuje już odizolowanego przetwarzania niezaufanego pliku przez
ustalony parser; nie czeka z tą ochroną do SP-04. SP-04 rozszerza ten zakres
o ogólne wykonywanie kodu użytkownika i trwały model prób zadań.

## Zależności i decyzje zanim pojawi się kod

| Zakres | Warunek wejścia | Krytyczna decyzja / próba |
|---|---|---|
| SP-01–02 | SP-00, Accepted SPEC-0001/0002/0017 | D-04/D-05: tożsamość, grants, transakcje, kanonizacja; wersje runtime i polityka CI |
| SP-03 | SP-02, SPEC-0003 | D-07: staging/finalizacja, retencja, uprawnienia do danych |
| SP-04 | SP-03, SPEC-0004 | D-06: runner/orchestrator, crash/retry, granica zaufania |
| SP-05–06 | SP-04, SPEC-0005/0006 | Spójność SQL, porty danych, rozwiązywanie symbolicznych wyjść przed krokiem |
| SP-07 | SP-03/04/06, SPEC-0007 | Dziedziczenie klasyfikacji, prawa do zależności, odwołanie delegacji |
| SP-08–09 | SP-06/07, SPEC-0008/0009 | Git kontra working copy, izolacja notebooka, semantyka replay i eksportu |
| SP-10–11 | SP-04/07/09, SPEC-0010/0011 | D-08: autoryzacja MLflow i artefaktów, model bez fit, bezpieczne raporty |
| SP-12–13 | SP-08/10/11, SPEC-0012/0013 | Bundle, approval, granice środowisk, scheduler i rollback |
| SP-14–15 | SP-13, SPEC-0014/0015 | D-10: warunki firmy, spójny restore, ryzyko migracji i odbiór operacyjny |

Próby techniczne dostają małą specyfikację przed wykonaniem. W SP-00 definiujemy
ich pytania i kryteria; nie budujemy po cichu niezatwierdzonego runnera.
Próby storage/runnera przygotowujemy z wyprzedzeniem SP-01–02, aby ograniczyć
ryzyko przeprojektowania obiektów. D-08 musi być rozstrzygnięta przed zobowiązaniem
do SP-10. Ujemny wynik próby zmienia ADR/plan zamiast obniżać kontrolę dostępu.

## Powiązanie wymagań z planem

Mapowanie wskazuje miejsce realizacji i weryfikacji, nie status PASS.

| Wymaganie | Sprinty weryfikujące |
|---|---|
| FR-01 | SP-01, SP-02, SP-07, SP-10, SP-12, SP-13 |
| FR-02 | SP-02, rozszerzenia SP-03, SP-10, SP-11 |
| FR-03 | SP-03, SP-05 |
| FR-04 | SP-04, SP-05 |
| FR-05 | SP-04, SP-06, SP-13 |
| FR-06 | SP-10 |
| FR-07 | SP-11 |
| FR-08 | SP-03–06, SP-09–13 |
| FR-09 | SP-08, SP-09 |
| FR-10 | SP-12, SP-13 |
| FR-11 | SP-01–13, końcowy scenariusz SP-15 |
| FR-12 | SP-01–03, SP-07, SP-09, SP-12–15 |
| NFR-01 | SP-01 i każdy kolejny endpoint, test pełny SP-15 |
| NFR-02 | SP-03 parser/preview, SP-04 worker, SP-09 notebook, SP-10 model, SP-15 |
| NFR-03 | SP-03–06, SP-09–13 |
| NFR-04 | SP-01–04, SP-12–15 |
| NFR-05 | Baseline SP-01–03; benchmark przy nowych typach obciążenia, profil P1 w SP-15 |
| NFR-06 | CI SP-01, runtime SP-04/09/10, release SP-12/13, kwalifikacja SP-15 |
| NFR-07 | Kontrakty SP-00, test zgodności od SP-01, Git/SDK SP-08/09, migracja SP-14 |
| NFR-08 | SP-01; rozszerzenia metryk/logów w każdym przyroście; alerty SP-13/15 |
| NFR-09 | Od SP-00/01, dane SP-03/05, sharing SP-07, eksport SP-09, retencja SP-14/15 |
| NFR-10 | Projekt SP-00; każdy ekran od SP-01; Flow SP-06; pełne E2E SP-15 |

## Praca na istniejącej infrastrukturze

- Aktualny Compose to demonstracja z historycznymi wolumenami. Na etapie planu
  nie zmieniamy `.env`, portów, obrazów, credentials ani działających usług.
- SP-01 ma dostarczyć jawnie osobną konfigurację dev platformy z niezależnymi
  bazą, nazwami zasobów i portami, sprawdzonymi wobec działającego stosu/Airflow.
- Testy uruchamiają zasoby efemeryczne. Nigdy nie traktują istniejących wolumenów
  MLflow/MinIO jako danych, które można wyczyścić po teście.
- Obrazy ML pozostają oddzielne od API. DataHub nie jest wymagany do startu
  pierwszego katalogu. Nie kopiujemy demonstracyjnych haseł do platformy.
- Dev/test od początku mają osobne tożsamości i konfiguracje. Topologię prod
  zatwierdza firma; lokalna demonstracja tego podziału nie jest produkcją.
- Migracja nie nadpisuje starych danych ani nie nadaje dawnym eksperymentom
  statusu zatwierdzonego wydania. Import wymaga mapowania i dowodów.

## Reguła odbioru każdego sprintu

Przyrost jest Done dopiero, gdy powiązane AC mają dowody z rzeczywistych usług,
UI i niezależnego klienta API. Obowiązują również negatywne testy praw,
współbieżności/awarii właściwe dla funkcji, migracja, logi i dokumentacja.
Mock może wspierać pracę frontendową, lecz nie jest dowodem integracji.
Nie uznajemy „backend gotowy, UI kiedyś” za pełny odbiór funkcji użytkowej.

Każda karta zadania przed wyborem do sprintu ma: ID, owner, Accepted SPEC/AC,
zależności, ryzyko i estymatę pojemności, rezultat, test/dowód i plan wycofania.
Prace czysto infrastrukturalne też mają kontrakt i sprawdzalny wynik.
Status: Planned → Ready → In progress → Review → Verified. Blocked ma konkretną
przyczynę i właściciela; Verified nie oznacza jeszcze Released/Production.

Na review pokazujemy wynik, niespełnione AC, rzeczywiste zużycie pojemności
i kolejny mały przyrost. Po SP-02 aktualizujemy prognozę na podstawie czasu
przejścia zadań, liczby odebranych pionowych funkcji, poprawek i opóźnień review.
Odstępstwa bezpieczeństwa nie są sposobem odzyskiwania terminu.

## Granice zakresu

W pierwszym przekroju: CSV/Parquet + PostgreSQL, Python/SQL, batch, jeden model
ML i regułowy, jedna metoda XAI, podstawowy Git i Jupyter. Formaty/adaptery
mają kontrakt rozszerzeń; nie implementujemy wszystkich konektorów na zapas.
Nie powstaje własny Spark/SQL warehouse, streaming, GPU serving ani pełny
edytor VS Code w przeglądarce. Dataiku inspiruje Flow i wydania; doświadczenie
pracy notebookowej może czerpać z Kaggle, bez rozszerzania zakresu do konkursów.

Artefakty: [rejestr SPEC](../../specs/README.md),
[logo i plan identyfikacji](../brand/README.md),
[SP-00](sprints/00-contracts.md), [SP-01](sprints/01-foundation.md),
[SP-02](sprints/02-object-versions.md).

## Walidacja tej rewizji planu

Sprawdzono lokalne odnośniki w 27 dokumentach Markdown, unikatowość 16 celów
sprintów i 24 zadań w kartach SP-00–02, 17 numerów w rejestrze SPEC oraz
mapowanie wszystkich 12 FR i 10 NFR. Kopia logo ma identyczny SHA-256 jak
oryginał użytkownika. `git diff --check` nie zgłosił błędów whitespace.
To kontrola spójności dokumentacji, **nie wykonanie testów produktu ani
akceptacja sprintów**. Nie zmieniono działających usług i danych; brak push.
