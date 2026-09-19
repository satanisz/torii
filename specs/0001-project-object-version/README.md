# SPEC-0001: projekty, uprawnienia i wersje definicji

Status: **Accepted (delegated)**. Rewizja: 0.4 (semantyka; format OpenAPI 0.2.0).
Data: 2026-09-19. Podstawa: [mandat użytkownika](../../docs/platform/delivery-mandate.md).
Implementacja/testy runtime: do wykonania; brak statusu Verified.
Kontrola schematów i przykładów jest osobnym dowodem specyfikacji, nie funkcji.

Przyrost [B1](increment-b1.md): transakcje projektów bez endpointów HTTP.
Rewizja 0.4 precyzuje zegar TTL receipt; nie zmienia schematu bazy ani wire.
Przyrost [B2a1](increment-b2a1.md): wewnętrzne identity/flow/session persistence,
przyjęty osobno po review. Bez JWT/OIDC/HTTP; cały SPEC nadal nie jest Verified.
Wykonane dowody częściowe: [B1](../../docs/platform/sp-01-b1-evidence.md) i
[B2a1](../../docs/platform/sp-01-b2a1-evidence.md). Poniższa macierz opisuje pełne
scenariusze produktu, nie zastępuje raportów ograniczonych przyrostów.
Przyrost [B2a2](increment-b2a2.md): offline podpisy JWT, ścisłe claims i publiczne
klucze, bez transportu OIDC, cache ani integracji logowania. D02 lokalnego profilu
przyjęte po review exact-tag źródeł; nadal potrzebne realne Keycloak E2E.
Dowód komponentu offline: [raport B2a2](../../docs/platform/sp-01-b2a2-evidence.md).
Przyrost [B2a3](increment-b2a3.md): bounded GET discovery/JWKS i cache kluczy,
przyjęty osobno po review. Code exchange/revocation wymagają B2a4; HTTP/login
E2E i odbiór SP-01 nadal pozostają osobnymi bramkami.
Dowody ograniczonego komponentu: [raport B2a3](../../docs/platform/sp-01-b2a3-evidence.md).
Przyrost [B2a4a](increment-b2a4a.md): czyste komunikaty OAuth, bez I/O;
[raport B2a4a](../../docs/platform/sp-01-b2a4a-evidence.md). Transport POST z
polityką logowania i orchestration pozostają kolejnymi krokami, nie zaliczonym loginem.

Wymagania: FR-01, FR-02, część FR-11/FR-12, NFR-01/04/07/08/09/10.
ADR: [0001](../../adr/0001-platform-boundaries.md),
[0002](../../adr/0002-git-and-authority.md),
[0003](../../adr/0003-reproducibility-and-releases.md).

## Problem i wartość

Torii nie ma własnego katalogu, stabilnych tożsamości obiektów ani kontroli
dostępu do projektu. Nie można bezpiecznie budować wspólnego Flow na samych
ścieżkach plików i nazwach MLflow. Ten przyrost ustanawia minimum domeny
i pokazuje je w prostym, rzeczywiście działającym interfejsie.

## Zakres

- Jedna organizacja i testowy OIDC; co najmniej dwie osoby w P1 i osoba w P2.
- Tworzenie projektu przez uprawnioną osobę i członkostwo z jawnymi grantami.
- Utworzenie obiektu typu Dataset lub Transformation, edycja draftu,
  finalizacja wersji **definicji**, historia i archiwizacja obiektu.
- Minimalne walidowane schematy obu definicji, bez dowolnego JSON jako modelu
  produktu. DatasetDefinitionVersion nie jest snapshotem DatasetVersion.
- API i UI: lista projektów, katalog, szczegóły, draft, wersje, odmowa/konflikt.
- Trwała baza z migracją i audytem zmian; klient API do testu niezależnego od UI.

Poza zakresem: upload i dostęp do bajtów danych, wykonanie transformacji,
podgląd plików, MLflow, graf Flow, Git sync, model/XAI, approvals i wdrożenia.
UI wyraźnie komunikuje „definicja — niewykonana”; nie oferuje fikcyjnego Run.
Udostępnianie między projektami to osobny przyrost; w tym zakresie odrzucamy
referencje między projektami. Nie wprowadzamy hasła współdzielonego przez zespół.

## Kontrakty rewizji 0.3

| Artefakt | Co określa |
|---|---|
| [OpenAPI 3.1](contracts/openapi.json) | 21 operacji, request/response, security, parametry i błędy |
| [Schema definicji](contracts/definitions.schema.json) | Typowane Dataset/Transformation, Python/SQL i źródła logiczne |
| [Przykłady](contracts/examples.json) | Pozytywne/negatywne payloady oraz oczekiwane bajty JCS |
| [Uprawnienia i API](access-and-api.md) | OIDC/sesja, role, błędy, ETag, idempotencja, limity i reguły domeny |
| [Dane i testy](data-and-tests.md) | Model relacyjny, ograniczenia, transakcje, digest i macierz AC |
| [Walidator specyfikacji](validate_contracts.py) | Powtarzalna kontrola schematów/przykładów bez uruchamiania platformy |

Pliki JSON są kanonicznym źródłem formatu; dokumenty określają semantykę,
której schema nie egzekwuje (ACL, referencje, transakcje, CSRF i unikatowość portów).
Sprzeczność blokuje akceptację; nie wybieramy wygodniejszej interpretacji w kodzie.
Żaden z tych artefaktów nie jest zatwierdzony samym faktem jego zapisania.

## Inwarianty i proponowane zachowanie

1. Aktor wynika ze zweryfikowanej tożsamości; parametr `owner_id` nie nadaje praw.
2. Utworzenie projektu atomowo nadaje właścicielowi początkowe uprawnienia.
   Nadawanie grantów wymaga osobnego prawa; autor nie eskaluje sam swojej roli.
3. Listy i wyszukiwanie filtrują prawa przed paginacją i obliczaniem liczników.
   Nie wolno ujawniać istnienia obiektu projektu niedostępnego użytkownikowi.
4. Nieaktualna rewizja draftu daje konflikt; backend nie stosuje last-write-wins.
   Finalizacja wskazuje oczekiwaną rewizję, aby nie opublikować cudzej edycji.
5. Finalizacja zapisuje wersję i audyt atomowo. Nie ma PUT/PATCH treści wersji.
6. Tożsamy retry z tym samym idempotency key w ustalonym okresie zwraca ten sam
   rezultat bez nowej wersji ani nowego zdarzenia audytu zmiany. Żądania i odmowy
   mogą mieć osobne zdarzenia dostępowe. Ten sam klucz z innym payloadem to konflikt.
   Zakres klucza obejmuje aktora, projekt i operację; retencja wynosi 24 h.
7. Archiwizacja blokuje edycję/publikację, ale zachowuje historię dla uprawnionych.
   Wyścig archiwizacji z finalizacją ma serializowany, testowany wynik.
8. Uprawnienia sprawdzamy dla każdej operacji, również starej wersji.
   Żaden ID/ETag nie jest tokenem dostępu. Cofnięcie prawa działa przy następnym
   żądaniu; dla S1 nie stosujemy cache autoryzacji, który wydłuża to okno.
9. Audyt nie zawiera sekretów ani niepotrzebnej pełnej kopii payloadu.
   Niedostępny zapis audytu zmiany blokuje commit tej zmiany.
10. Opisy/definicje są niezaufane. Walidacja nie importuje Python, nie wykonuje
    SQL, Git hooks, template expressions ani aktywnego HTML.

## Scenariusze akceptacyjne

Każdy scenariusz obejmuje sprawdzenie stanu trwałego, nie tylko odpowiedź UI.
Poniższe nazwy testów są planowane, żaden taki test jeszcze nie istnieje.

| AC | Given / When / Then | Planowany test |
|---|---|---|
| AC-01 | Osoba z prawem tworzenia projektu tworzy P1; otrzymuje członkostwo właściciela i jedno zdarzenie audytu w tej samej transakcji | `project_creation` |
| AC-02 | Autor A ma write w P1, B ma read; A tworzy definicję, B ją czyta, lecz próba edycji B nie zmienia stanu | `project_roles` |
| AC-03 | E ma tylko P2; lista, szczegóły, wersje, filtrowanie i bezpośrednie żądanie do P1 nie ujawniają P1 ani metadanych jego obiektów | `cross_project_denied` |
| AC-04 | Dwa klienty odczytały revision 1; po zapisie A drugi zapis ma konflikt; zapis A nie zostaje utracony | `draft_conflict` |
| AC-05 | Istnieje v1; zmieniony draft daje v2; payload/digest v1 pozostają identyczne, bez endpointu nadpisania | `immutable_definition_version` |
| AC-06 | Dwa równoległe żądania finalizacji mają ten sam klucz i payload; powstaje jedna wersja i jeden audit event; zmiana payloadu z tym kluczem daje konflikt | `idempotent_finalize` |
| AC-07 | Błąd bazy/audytu występuje w finalizacji; nie ma częściowej wersji; bezpieczny retry może zakończyć operację | `atomic_finalize_failure` |
| AC-08 | Schemat nieobsługiwany, błędny typ pola, nadmiarowy payload lub odwołanie do innego projektu; brak zapisu i stabilny, nieujawniający danych błąd | `definition_validation` |
| AC-09 | B miał read; właściciel odbiera grant; następne żądanie z nadal poprawną sesją nie daje dostępu do starej ani nowej wersji | `grant_revocation` |
| AC-10 | E wysyła podmieniony actor/owner/project; nie dostaje prawa ani nie może nadać sobie roli właściciela | `identity_and_privilege_escalation` |
| AC-11 | Obiekt z v1 jest archiwizowany; uprawniony czyta historię, ale nie edytuje; wyścig z finalizacją nie omija reguły | `archive_race` |
| AC-12 | Usługi API/bazy restartują; członkostwo, wersje i audyt zachowują się zgodnie z zatwierdzonym stanem | `metadata_restart` |
| AC-13 | UI katalogu/detail/draft obsługiwane klawiaturą pokazuje właściwy projekt, wersję, brak prawa i konflikt; te same próby przez surowy klient API dają zgodne decyzje | `ui_api_parity` |
| AC-14 | Token wygasły, podmieniony issuer/audience albo brak sesji; operacja odrzucona, brak danych i zmian; payload HTML/Python nie wykonuje się | `untrusted_input_and_authentication` |
| AC-15 | Przed migracją i po niej testowa kopia danych; restore poprzedniej wersji zachowuje ID, grants, payloady i audyt; kontynuacja pracy nie gubi historii | `migration_restore` |

## Powiązanie wymagań z dowodami

| Wymaganie | Kryteria | Status |
|---|---|---|
| FR-01, NFR-01 | AC-01/02/03/09/10/14 | Nie wykonano |
| FR-02, NFR-07 | AC-04/05/06/08/11/15 | Nie wykonano |
| FR-11 (część), NFR-10 | AC-13 | Nie wykonano |
| FR-12 (część), NFR-04 | AC-01/07/12/15 | Nie wykonano |
| NFR-08/09 (część) | AC-07/10/14 oraz przegląd logów/correlation ID/redakcji | Nie wykonano |

Plan testów: domenowe inwarianty i property-based testy wersjonowania,
kontraktowe przykłady OpenAPI, integracja z prawdziwym PostgreSQL i testowym
IdP, konkurencyjne transakcje, E2E UI plus klient API, migracja/restore.
Docelowe lokalizacje (do utworzenia w implementacji):
`tests/acceptance/test_spec_0001.py`, `tests/integration/`, `apps/web/tests/`.
Macierz rozszerza dokument danych i testów; kontrole schematów nie zaliczają AC runtime.

## Plan implementacji po akceptacji

1. Baseline CI i testowy projekt usług po osobnej mini-SPEC procesu dostarczania.
2. Typy domenowe i testy kontraktów/inwariantów, migracja PostgreSQL.
3. OIDC, polityka grants, audyt, repozytoria transakcyjne; testy negatywne.
4. API z walidacją, kontrolą konkurencji, idempotencją i błędami.
5. Minimalny UI podłączony do API, E2E i zachowanie przy awarii/konflikcie.
6. Dowody kryteriów, przegląd niezależny i demonstracja wielu użytkowników.

## Migracja i wycofanie

Nowa baza platformy, bez zmiany tabel MLflow, obiektów MinIO i istniejących
workspace. Pierwsza migracja może tworzyć pusty schema, ale kolejne muszą
przejść upgrade z wcześniejszego fixture. Cofnięcie aplikacji wymaga zgodnego
schema albo odtworzenia w nowej bazie; nie obiecujemy bezstratnego down-migration.
Przy rollback stosujemy uzgodnione okno zapisu, żeby nie porzucić nowych danych.

Przyłączenie obecnej demonstracji jest późniejszą SPEC migracji/importu.
Nie przeklasyfikowujemy historycznych rekordów DataHub `PROD` na rzeczywiście
zatwierdzone wydania produkcyjne.

## Przyjęty baseline i granice akceptacji

Przygotowano rekomendacje D-04/D-05: testowy Keycloak/OIDC, role reader/editor/owner,
pełna polityka do 100 członków na projekt w S1, JCS/SHA-256, ETag i transakcje
serializowane per projekt. Limity i dokładny format podano w kontraktach.
Zakres oraz SPEC-0002/0017 objęto mandatem delegowanej realizacji.
Przegląd techniczny kontraktów prowadzi oddzielny agent; nie zastępuje audytu
firmowego i nie ustanawia polityki firmy.

Zakres SP-01 dopuszczony do implementacji po przeglądzie technicznym.
Żadne AC runtime nie otrzymuje PASS przez samą akceptację kontraktów.

## Historia

- 0.3: przegląd niezależnego agenta wykrył potrzebę powiązania OIDC z inicjującą
  przeglądarką oraz kontroli bieżącej widoczności przy createProject replay.
  Doprecyzowano również binding pełnej kolekcji w cursor. Integrator przyjął
  zmiany przed kodem odpowiednich ścieżek, w granicach mandatu. Bez zmiany
  pól request/response kontraktu maszynowego 0.2.0.

- 0.1: szkic domeny, 15 AC i otwarte pytania.
- 0.2: konkretne kontrakty API/schema, role/sesja, transakcje, limity i walidacja
  offline. Archiwizacja owner-only, no-op dla identycznego digestu, osobna
  polityka ACL i pełna rewizja reprezentacji obiektu. Accepted (delegated)
  na podstawie mandatu z 2026-09-19.
