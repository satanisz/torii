# SP-01 — platforma, tożsamość i pierwszy działający ekran

Rewizja planu: **0.2, 2026-10-10**. Status: **In progress, odbiór otwarty**;
start na podstawie [mandatu](../delivery-mandate.md) i kontraktów [SP-00](00-contracts.md).
Ta aktualizacja porządkuje plan, nie potwierdza nowej implementacji ani odbioru.
Baseline SPEC-0001, SPEC-0002 i SPEC-0017 jest Accepted (delegated); pozostałe
fragmenty B2 wymagają własnego przeglądu przed kodem.
Cel: użytkownik loguje się do Torii i widzi wyłącznie dostępne mu projekty.
To pierwszy pionowy przyrost obejmujący infrastrukturę, API, bazę i UI.
Powiązania: [plan sprintów](../sprint-plan.md),
[kierunek platformy obiektów](../enterprise-object-platform.md).

## Stan techniczny na 2026-10-10

Odczyt kodu i [dziennika](../delivery-progress.md), bez ponownego uruchamiania
testów lub usług podczas aktualizacji planu:

- [Fabryka API](../../../apps/api/src/torii_api/app.py) wystawia tylko
  `/health/live` i `/health/ready`. Ścieżki produktu w OpenAPI nie są jeszcze
  podłączonymi endpointami.
- Istnieją trwałe serwisy projektów, członkostw, polityk, audytu i idempotencji
  oraz migracja PostgreSQL. B1 ma zapisane dowody rzeczywistych transakcji;
  nie powtarzamy jego implementacji w kolejnym przyroście.
- B2a1–B2a4c dostarczyły stan sesji/flow, JWT/JWKS, transport discovery/cache,
  komunikaty OAuth oraz ograniczony POST i politykę logowania procesu.
  [Dowód B2a4b](../sp-01-b2a4b-evidence.md) obejmuje komponent z kontrolowanym
  transportem, nie realne logowanie. [B2](../../../specs/0001-project-object-version/increment-b2.md)
  pozostaje Proposed poza osobno przyjętymi fragmentami.
  [Orkiestracja SP01-04b](../sp-01-b2a4c-evidence.md) składa te komponenty
  z rzeczywistą bazą; HTTP i rzeczywisty IdP nadal należą do B2b.
- [Frontend enterprise](../../../apps/web/README.md) ma powłokę, projekty,
  dostęp i audyt oraz rzeczywisty klient HTTP. Czeka na podłączenie backendu;
  testy z odpowiedziami mockowanymi nie zaliczają integracji.
- [Stos dev/test](../../../deploy/platform/evidence.md) i CI istnieją,
  ale pełny odbiór auth/UI, odtworzenia, metryk, retencji i pozostałych bramek
  operacyjnych jest otwarty. Demo SPEC-0018 i finanse SPEC-0019 są osobnymi
  profilami i nie zaliczają SP-01.

## Backlog z zachowaniem dotychczasowych ID

M = wymagane w uzgodnionym zakresie sprintu. I = infrastruktura, B = backend,
F = frontend, Q = QA. Ownerzy i estymaty pozostałej pracy wymagają planningu.
Status „częściowo” nie jest odbiorem zadania ani całej specyfikacji.

| ID | Tor | Stan | Istniejący rezultat i pozostała praca | Kontrakt / dowód |
|---|---|---|---|---|
| SP01-01 | I/Q | Częściowo | Locki, lint/types, kontrakty, testy i CI istnieją; domknąć powtarzalny build oraz wymagane skany/SBOM/licencje | SPEC-0002; dowody dla ocenianego commita, nie sam plik workflow |
| SP01-02 | I | Częściowo | Izolowane DB/IdP/API/web/gateway i role istnieją; domknąć pełny start/bootstrap/E2E oraz instrukcję nowej instancji | SPEC-0002; start/readiness/stop i izolacja od starych zasobów |
| SP01-03 | B/Q | Implementacja podstaw z dowodami B1/B2a1; odbiór otwarty | Zachować migrację, serwisy i fixtures; potwierdzić restart/restore oraz użycie przez chronione HTTP | SPEC-0001 AC-01/12/15 w zakresie projektów |
| SP01-04 | B/Q | Częściowo | Zachować B1 i B2a1–B2a4c; dokończyć uwierzytelnianie HTTP i trasy projektów | SPEC-0001 AC-01/03/09/10/14; B2-AC01–06 w odpowiednim zakresie |
| SP01-05 | F | Implementacja powłoki z testami; odbiór otwarty | Zachować komponenty i formularze; sprawdzić focus, komunikaty i dostępność w rzeczywistym przepływie | SPEC-0017; testy UI nie zastępują odbioru z API |
| SP01-06 | F/B | Klient UI gotowy do integracji | Podłączyć login/logout, sesję, projekty, politykę dostępu i audyt do rzeczywistego backendu | SPEC-0001 AC-13; brak hardcoded użytkownika i obejść auth |
| SP01-07 | I/B/Q | Częściowo | Request ID, health/readiness i część redakcji istnieją; domknąć metryki/retencję, limiter, restart i restore | SPEC-0002 oraz SPEC-0001 AC-12/15; osobny dowód restore |
| SP01-08 | Q/review | Odbiór planowany | Przeprowadzić pełną macierz wielu tożsamości/UI/surowego API i przegląd dowodów | Wszystkie wymagane AC przyrostu PASS; niespełnione bramki pozostają jawne |

## Kolejność pozostałych przyrostów

Poniższe podzadania rozwijają istniejące ID. Ich zapis nie nadaje statusu
Accepted nowym decyzjom transportu, orkiestracji ani kontraktom HTTP.

| ID | Zakres do wykonania | Zależność | Dowód odbioru |
|---|---|---|---|
| SP01-04a | B2a4b: zaimplementowany ograniczony POST wymiany kodu i revocation oraz polityka logowania procesu | Istniejące B2a3/B2a4a | [Raport komponentu](../sp-01-b2a4b-evidence.md): fixed URL, brak retry/redirect/proxy env, limity i redakcja; bez realnego loginu |
| SP01-04b | B2a4c: zaimplementowana wewnętrzna orkiestracja flow, tokenów, sesji i best-effort revoke | SP01-04a oraz istniejące B2a1/B2a2 | [Raport](../sp-01-b2a4c-evidence.md): real PG, callback zużyty raz, brak sesji po złym JWT, join/kompensacja i jawne commit-unknown; bez HTTP/UI |
| SP01-04c | B2b: middleware tożsamości, cookie/CSRF/Origin, login/callback/session/logout, chronione trasy projektów/polityk/memberships/audytu | SP01-04b; review części HTTP B2 | Macierz ról, cofnięcie praw, ETag/idempotencja i błędy zgodne z B1/OpenAPI; brak zaufania do actor z payloadu |
| SP01-06a | Powtarzalny bootstrap syntetycznej organizacji i uprawnienia create; integracja istniejącego UI z trasami | SP01-04c; SP01-02/05 | Sam login nie przyznaje grantów; nowy izolowany stos obsługuje A/B/E, create, edycję polityki i audyt bez ręcznej zmiany DB |
| SP01-07a | Domknięcie limitera, logów/metryk o ograniczonej liczbie etykiet, retencji oraz restart/backup/restore | Kontrakty SP01-04c; istniejący profil dev/test | Weryfikacja sekretów w dowodach; restore do nowej bazy zachowuje ID/grants/audyt; restart nie zastępuje restore |
| SP01-08a | Pełne E2E realnego IdP, przeglądarek i surowego API oraz awarii IdP, wygaśnięcia i revocation | SP01-06a | B2-AC05/06/07 w zakresie integracji; ID token odrzucony jako Bearer, obcy projekt niewidoczny, wylogowanie skuteczne mimo awarii IdP |
| SP01-08b | Regresja B1/B2a, brakujące skany/NFR/UX, instrukcja obsługi i zbiorczy przegląd AC | SP01-07a/08a oraz SP01-01 | Raport z commitami, spec, topologią, PASS/SKIP i brakami; decyzja o odbiorze SP-01 przed zależną implementacją SP-02 |

Niezależne prace nad dowodami infrastruktury i dostępnymi komponentami UI
mogą postępować równolegle. Nie zastępują odbioru z rzeczywistym backendem.

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

W tym przyroście enterprise nie ma jeszcze danych, wersji obiektów, Runu ani
Flow. Moduły niegotowe nie powinny mieć aktywnych przycisków sugerujących działanie. To nie jest
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
