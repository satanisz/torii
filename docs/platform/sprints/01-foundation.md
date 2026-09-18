# SP-01 — platforma, tożsamość i pierwszy działający ekran

Status: Planned; **nie Ready**. Zależność: odebrany [SP-00](00-contracts.md).
Specyfikacje wymagane przed kodem: Accepted SPEC-0001, SPEC-0002 i SPEC-0017.
Cel: użytkownik loguje się do Torii i widzi wyłącznie dostępne mu projekty.
To pierwszy pionowy przyrost obejmujący infrastrukturę, API, bazę i UI.

## Backlog planowany

Wszystkie pozycje M, status Planned, owner konkretnej osoby i estymata do
ustalenia na planningu. I = infrastruktura, B = backend, F = frontend, Q = QA.
Numer zadania nie narzuca wykonywania niezależnych prac sekwencyjnie; przy
jednej osobie nie zakładamy równoległej realizacji trzech torów.

| ID | Tor | Zakres | Zależność | Kontrakt / dowód |
|---|---|---|---|---|
| SP01-01 | I/Q | Szkielet repo modułów, locki, typowanie/lint, walidacja kontraktów, testy i skan sekretów/zależności | SP-00 | SPEC-0002; powtarzalny build na świeżym środowisku, test granic importów |
| SP01-02 | I | Izolowany profil dev/test: baza platformy, IdP, ingress do UI/API, role i konfiguracja | SP01-01 | SPEC-0002; start/readiness/stop, bez kolizji portów i bez dostępu testów do starych wolumenów |
| SP01-03 | B/Q | Migracje projektów, principal/grants i audytu; fixtures P1/P2 | SP01-01/02 | SPEC-0001 AC-01/12/15 w zakresie projektów; transakcja nie pozostawia właściciela bez projektu lub odwrotnie |
| SP01-04 | B/Q | Uwierzytelnianie OIDC, polityka praw, list/create project i członkostwo | SP01-03 | SPEC-0001 AC-01/03/09/10/14 w zakresie istniejących endpointów; brak zaufania do actor z payloadu |
| SP01-05 | F | Powłoka UI i tokeny design systemu, logo/nazwa, focus, formularze i komunikaty | SP01-01; Accepted SPEC-0017 | Kontrakt komponentów i dostępności; bez atrap kolejnych modułów udających funkcje |
| SP01-06 | F/B | Login/logout, lista projektów, utworzenie i dostęp, brak sesji/uprawnień | SP01-04/05 | SPEC-0001 AC-13 w zakresie projektu; prawdziwe API, brak hardcoded użytkownika |
| SP01-07 | I/B/Q | Correlation ID, redakcja logów, health/readiness, minimalne metryki i backup/restore projektu | SP01-02/03/04 | SPEC-0002 oraz AC-12/15 częściowo; restart i restore z kontrolą grants/audytu |
| SP01-08 | Q/review | E2E wielu tożsamości, surowy klient API, skany, instrukcja dev i raport dowodów | SP01-01–07 | Wszystkie zatwierdzone AC przyrostu PASS, jawne ograniczenia; review nie jest samym screenshotem |

CI w SPEC-0002 obejmie stopniowo testy właściwe kolejnym modułom.
Konfiguracja zdalnych required checks/ochrony gałęzi wymaga wskazania repo,
uprawnień i wyraźnego zlecenia takiej zmiany. Samo utworzenie workflow nie
oznacza, że merge jest technicznie chroniony. Dopóki brak wymaganej ochrony
lub review, wynik pozostaje kandydatem do odbioru, nie zatwierdzonym release.

## Konkretny pokaz na końcu

1. Świeży testowy stos startuje według dokumentacji bez ręcznego poprawiania bazy.
2. A loguje się, tworzy P1 i nadaje B dozwolony zakres członkostwa.
3. B widzi P1; E z P2 nie widzi nazwy P1 ani metadanych przez UI i API.
4. Odebranie B dostępu blokuje kolejne żądanie, mimo nadal ważnej sesji OIDC.
5. Restart API/bazy zachowuje członkostwa i audyt. Testowy sekret nie wycieka
   do logów. Żądania mają identyfikator korelacji.
6. Wylogowanie/wygaśnięcie sesji prowadzi do przewidzianego ekranu i odmowy API.

Dokładne kody HTTP, reguły sesji i role zamraża SP-00. Pokaz nie jest pozwoleniem
na podjęcie tych decyzji dopiero w trakcie implementacji.

## Granica odbioru i ryzyka

Nie ma jeszcze danych, wersji obiektów, Runu ani Flow. Moduły niegotowe nie
powinny mieć aktywnych przycisków sugerujących działanie. To nie jest
ukończenie całej SPEC-0001; jej pełne AC są odbierane dopiero w SP-02.

Największe ryzyka: sesja OIDC kontra autoryzacja grantów, wycieki przez listy,
uzależnienie API od ML dependencies i kolizje ze starym stosem. Każde ma test
lub dowód konfiguracji. Jeżeli cel jest za duży, wydzielamy dodatkową iterację;
nie odkładamy testów praw dostępu do czasu ukończenia katalogu.

## Wycofanie

Zatrzymujemy wyłącznie nowe zasoby platformy, zachowując ich dane i audyt.
Nie wykonujemy globalnego czyszczenia Docker ani `down -v` na starym stosie.
Testy korzystają z jawnie własnych fixture/zasobów; ich cleanup ma sprawdzony
zakres. Cofnięcie schematu dopuszczalne tylko według planu migracji/restore.

Następny przyrost: [SP-02](02-object-versions.md).
