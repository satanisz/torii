# SP-03 — import i niezmienne wersje danych

Rewizja planu: **0.2, 2026-10-10**. Status: **Planned; nie Ready**.
Zależność implementacji: odebrany [SP-02](02-object-versions.md).
[SPEC-0003](../../../specs/README.md) jest zarezerwowana; dokument i Accepted
jeszcze nie istnieją. Ta karta jest planem, nie specyfikacją kontraktów ani
dowodem ich implementacji. Powiązania: [plan sprintów](../sprint-plan.md),
[kierunek platformy obiektów](../enterprise-object-platform.md).

Cel: uprawniony użytkownik importuje jeden plik CSV albo Parquet do istniejącego
obiektu Dataset, a następnie otwiera konkretną, niezmienną wersję danych wraz
ze schematem, próbką i rzeczywistym pochodzeniem importu. Zmieniony plik tworzy
nowy snapshot; wcześniejsza wersja pozostaje dostępna według tej samej polityki
uprawnień. Nie sprowadzamy wyniku do aktualizacji kafelka ani jednego „najnowszego”
pliku pod wspólnym kluczem.

## Mały przekrój przez platformę

`DatasetDefinitionVersion → import pliku → staging S3 → izolowany parser →
manifest i finalizacja → DatasetVersion → katalog / szczegóły wersji`

Definicja z SP-02 i snapshot danych są różnymi bytami. Wersja danych wskazuje
wersję definicji, zatwierdzone parametry odczytu, referencję artefaktu i jego
digest, schemat, rozmiar oraz rekord importu. Pochodzenie obejmuje tożsamość
operatora, czas, wejście importu i wersję parsera/runtime. Nazwa przesłanego
pliku jest informacją opisową; nie dowodzi pochodzenia z systemu bankowego.
Nie dopisujemy fikcyjnego lineage transformacji, której nie wykonano.

Pierwszy przekrój przyjmuje pojedyncze pliki i jawnie ograniczony podzbiór
typów tabelarycznych CSV/Parquet. Konkretne limity, kodowanie, typy, null,
daty i zachowanie przy niepoprawnych rekordach zamrozi SPEC-0003. Dane do
odbioru są syntetyczne. Konektor SQL, ogólny kod użytkownika, Flow i trening
pozostają odpowiednio w SP-05, SP-04, SP-06 i SP-10.

## Warunki przed implementacją

Przygotowanie specyfikacji i rozpoznanie storage można prowadzić podczas
SP-02. Implementacja pionowego przyrostu wymaga jego odbioru oraz:

- przygotowanej i przyjętej SPEC-0003: API, model stanów importu/publikacji,
  migracja, ACL, idempotencja, błędy, retencja staging i kryteria odbioru;
- wyniku [EXP-02](../sp-00-technical-trials.md) po osobnym przyjęciu zakresu
  próby: awarie S3/DB, ochrona opublikowanego artefaktu i reconciliation;
- wybranego profilu S3 dev/test i ADR publikacji: hash w nazwie ani sam
  versioning bucketu nie dowodzą niezmienności lub kompletności snapshotu;
- kontraktu izolacji parsera już przy pierwszym uploadzie: osobny proces
  wykonawczy z egzekwowanymi limitami i uprawnieniami, bez dostępu do hosta,
  sekretów API i sieci poza jawnie niezbędnym zakresem magazynu.

## Backlog planowany

Wszystkie poniższe zadania są Planned. Ownerzy i estymaty do wskazania przy
przyjęciu specyfikacji. SP03-AC są roboczymi identyfikatorami tej karty;
SPEC-0003 ma później otrzymać jawne mapowanie własnych kryteriów.

| ID | Tor | Zakres | Zależność | Dowód / kryteria |
|---|---|---|---|---|
| SP03-01 | Architektura/backend/QA | Przygotować SPEC-0003, kontrakty importu/DatasetVersion, model stanów i migrację; przeprowadzić przyjętą próbę EXP-02 i review ADR | Kontrakty SP-02; zakres próby przyjęty przed jej wykonaniem | Spec Accepted przed implementacją, jawne AC i decyzje z sekcji niewiadomych |
| SP03-02 | Infrastruktura/backend | Osobny magazyn S3 dev/test, ograniczone role, staging/publikacja, ochrona artefaktów i cleanup z reconciliation | SP03-01; odebrany SP-02 | SP03-AC02/03/05; runtime nie nadpisuje opublikowanego snapshotu, cleanup nie usuwa aktywnej referencji |
| SP03-03 | Backend/QA | Izolowany import CSV/Parquet: limity wejścia/dekompresji/wierszy/kolumn/czasu/pamięci, schemat i ograniczony preview bez wykonywania treści | SP03-01/02 | SP03-AC01/04/05; uszkodzony lub przekraczający limit plik kończy się kontrolowaną odmową |
| SP03-04 | Backend | Metadane DatasetVersion i rekordu importu w PostgreSQL; referencje artefaktów, digest, idempotentna finalizacja, audyt i ACL | SP03-02/03 | SP03-AC02/03/05/06; ready wyłącznie po potwierdzeniu kompletnego artefaktu, brak globalnego ujawniania hashy |
| SP03-05 | Frontend/backend | Import wewnątrz istniejącego obiektu, stany postępu/błędu, szczegóły wersji, schema/preview; zasilenie API/grafu DatasetVersion i relacjami importu | SP03-03/04 | SP03-AC01/02/04/06; trwałe metadane z API, zachowany wybór historycznej wersji |
| SP03-06 | QA/platform | Realny S3+PG+UI, awarie pomiędzy etapami publikacji, retry/konkurencja, regresja ACL, upgrade/restart/restore i instrukcja operatora | SP03-02–05 | SP03-AC01–07 PASS z dowodami oraz niezależnym review; brakujące AC blokują odbiór |

## Proponowane kryteria odbioru

| ID | Obserwowalny rezultat wymagający dowodu |
|---|---|
| SP03-AC01 | Uprawniony A importuje poprawny CSV i Parquet do istniejących obiektów; API i UI wskazują utrwalone ID wersji, schemat, próbkę oraz rekord importu. |
| SP03-AC02 | A importuje zmieniony plik do tego samego Dataset: powstaje v2, v1 zachowuje własny digest i odczytywane bajty. Zmiana wersji definicji nie zmienia wcześniejszego snapshotu. Próba nadpisania chronionego artefaktu przez runtime zostaje odrzucona. |
| SP03-AC03 | Retry tej samej finalizacji nie tworzy drugiej wersji. Awaria uploadu, parsera lub commit nie publikuje częściowego wyniku. Awaria pomiędzy S3 i PG ma udokumentowany stan odzyskania; reconciliation/cleanup nie usuwa opublikowanych ani nadal aktywnych artefaktów. |
| SP03-AC04 | Plik ponad limit, niepoprawna struktura i kosztowna dekompresja kończą się błędem o ograniczonej treści. Parser ma egzekwowane limity i nie działa w procesie API. Wartości podglądu są tekstem; treść danych nie uruchamia HTML/skryptu. |
| SP03-AC05 | E nie odczytuje metadanych, preview ani artefaktu P1 mimo znanego ID/hash/key. Cofnięcie grantu blokuje następne wydanie dostępu zgodnie z przyjętym kontraktem; ewentualne wcześniej wystawione URL mają jawny zakres i TTL. Sekrety magazynu nie trafiają do UI/logów. |
| SP03-AC06 | API i graf zawierają rzeczywiste węzły DatasetVersion i relacje importu; wybór węzła otwiera tę samą wersję co katalog. Szczegóły wskazują DatasetDefinitionVersion, parametry, operatora/czas, parser/runtime i digest. Graf rozróżnia wejściowy plik od niepotwierdzonego źródła zewnętrznego i nie ujawnia obcych zasobów. |
| SP03-AC07 | Upgrade z fixture SP-02 i restart zachowują obiekty/uprawnienia. Restore metadanych oraz potrzebnych artefaktów do odrębnego środowiska pozwala odczytać tę samą v1 i zweryfikować digest; backup samej bazy nie jest wystarczającym dowodem. |

## Pokaz na review

1. A otwiera istniejący Dataset i jego konkretną wersję definicji; importuje
   syntetyczny CSV. Otwiera v1, schemat i próbkę, następnie ten sam węzeł
   DatasetVersion w grafie i relację do rekordu importu/wersji definicji.
2. Zmienia wiersze i importuje plik ponownie do tego samego obiektu. Otwiera
   v2, wraca do v1 i potwierdza, że historyczne dane nie zostały nadpisane.
3. Importuje syntetyczny Parquet do drugiego obiektu. Te same szczegóły wersji
   i kontrole praw działają niezależnie od formatu wejścia.
4. Próba E odczytania znanej v1 przez UI i surowe API kończy się odmową bez
   ujawnienia metadanych. Test obejmuje również ścieżkę pobrania artefaktu.
5. Kontrolowana awaria między uploadem a publikacją nie tworzy wersji ready.
   Retry i reconciliation dają wynik zgodny z kontraktem, bez duplikatu.
6. Odrębny dowód restore pokazuje odtworzoną v1, zgodny digest i te same granty.

## Wycofanie i granice zmian

Wyłączenie importów nie usuwa już opublikowanych wersji. Wycofanie aplikacji
wymaga zgodności schematu albo sprawdzonego odtworzenia do nowej instancji,
z zachowaniem metadanych i powiązanych artefaktów. Cleanup obejmuje wyłącznie
własny staging według statusu, wieku i aktualnych referencji. Dane historyczne,
wolumeny demo/legacy i ich MinIO pozostają poza zakresem tego sprintu.

Rekord importu nie zastępuje ogólnego modelu Run/Attempt. SP-04 rozszerzy
wykonania o kod użytkownika, kolejkę, lease, heartbeat i lineage transformacji.
SP-03 wymaga bezpiecznego parsera już teraz; nie odkłada tej izolacji na SP-04.

## Niewiadome do rozstrzygnięcia w SP03-01

- Storage: implementacja S3 dev/test, egzekwowana ochrona opublikowanych
  obiektów, sposób referencji do wersji artefaktu i przenośność adaptera.
- Format: jawny podzbiór typów Parquet, CSV encoding/delimiter, null/date/time,
  dopuszczalne konwersje i limity. Nie zakładamy, że oba formaty mają identyczny
  zakres typów ani że preview jest pełnym profilem dużego pliku.
- Publikacja: zachowanie przy każdej awarii S3/PG, identyfikator operacji,
  współbieżna finalizacja, próby wznowienia i ochrona aktywnego stagingu.
- Dostęp: ścieżka pobrania i preview, ewentualne krótkotrwałe URL, cofnięcie
  uprawnień, audyt pobrań i brak bocznego kanału przez deduplikację/hash.
- Retencja i odtworzenie: przechowywanie wejścia i wyniku parsowania, koszty,
  cleanup, spójny backup DB+S3 oraz pomiary akceptowalnego czasu importu.

Decyzje i wyniki prób mają poprzedzać przyjęcie zależnego kontraktu. Ta karta
nie wybiera samodzielnie usługi chmurowej ani nie uruchamia eksperymentu.
