# SPEC-0001: projekty, uprawnienia i wersje definicji

Status: **Draft — niegotowa do implementacji**. Rewizja: 0.1.
Data: 2026-09-19. Właściciel akceptacji: właściciel produktu, potwierdzenie roli
wymagane. Akceptacja rewizji: brak. Implementacja/testy: nie rozpoczęto.

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

## Kontrakt do doprecyzowania w rewizji 0.2

Minimalne pola: project ID, object ID, kind, nazwa, właściciel, revision draftu,
schema version, canonical definition, digest, version ID, author i timestamp UTC.
ID to identyfikatory niezmienne, nie nazwy ani ścieżki. Typ obiektu po utworzeniu
nie jest zmieniany. Dla każdej wersji zapisujemy dokładny payload podlegający
hashowaniu; algorytm kanonizacji wymaga przykładów zgodnych dla Python i JS.

Proponowany kształt API, **jeszcze nie zamrożony kontrakt**:

- `/api/v1/projects` — lista i utworzenie projektu;
- `/api/v1/projects/{project_id}/memberships` — uprawniona zmiana członkostwa;
- `/api/v1/projects/{project_id}/objects` — lista i utworzenie obiektu;
- `/api/v1/projects/{project_id}/objects/{object_id}` — szczegóły;
- `.../draft` — odczyt i edycja z revision/ETag;
- `.../versions` — lista i finalizacja wersji definicji;
- `.../versions/{version_id}` — odczyt niezmiennego payloadu;
- `.../archive` — audytowana archiwizacja, nie fizyczne usunięcie historii.

Metody, request/response, kody błędów, paginacja, limity, schema obu typów,
macierz ról i zasady idempotency zostaną zapisane w OpenAPI/JSON Schema
z poprawnymi i błędnymi przykładami przed Accepted. Nie generujemy jeszcze
API z tego szkicu ani nie pozwalamy implementującemu zgadywać kontraktu.

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
   Zakres klucza obejmuje aktora, projekt i operację; czas retencji do ustalenia.
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
Macierz testów i typy danych zostaną rozwinięte przed akceptacją rewizji 0.2.

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

## Otwarte decyzje — blokują Ready

- D-04/D-05 z [planu](../../docs/platform/roadmap.md): konkretny testowy IdP,
  model uprawnień i tożsamości, finalizacja/kanonizacja definicji.
- Kontrakt obu typów, granice pola code/source reference oraz zakaz wykonania.
- OpenAPI/JSON Schema, constraints i indeksy bazy, limity/paginacja,
  kody błędów, czas retencji idempotency oraz zasady konfliktów.
- Polityka logów/audytu, prosty threat model tego przyrostu, CI i review owner.
- Uzgodnienie kryteriów i zapis akceptacji konkretnej rewizji.

Definition of Ready obecnie **niespełniona**. Żadne AC nie ma dowodu PASS.
Ten szkic jest następnym przedmiotem prac specyfikacyjnych, nie poleceniem
uruchomienia generatora backendu.
