# SPEC-0001 — zapis, inwarianty i plan dowodów

Rewizja 0.3, Accepted (delegated). Schemat logiczny; wykonanie migracji wymaga dowodu.

## Relacje i ograniczenia

| Relacja | Klucze i wymagane ograniczenia |
|---|---|
| organizations | UUID PK; pojedyncza organizacja instalacji |
| principals | UUID PK, org FK, UNIQUE(issuer,subject), active; email wyłącznie opisowy |
| global_grants | UNIQUE(principal_id,permission); w S1 `project.create` |
| projects | UUID PK, org FK, name, description, created_by FK, acl_revision >= 1 |
| memberships | PK(project_id,principal_id), role enum owner/editor/reader, created_at; co najmniej jeden owner egzekwowany pod lockiem projektu |
| objects | UUID PK, UNIQUE(project_id,id), project FK, kind enum, name/description, state enum, revision >= 1 całej reprezentacji, created_by |
| drafts | PK(project_id,object_id), composite FK do objects, revision >= 1, definition JSONB, updated_by/at |
| definition_versions | UUID PK, UNIQUE(project_id,id), composite FK do objects, UNIQUE(project_id,object_id,number), UNIQUE(project_id,object_id,digest), immutable canonical bytes + JSONB, schema_version, author/time |
| definition_references | project_id + version_id + target object ID; composite FK do wersji i obiektu zapewnia wspólny projekt; target kind/spójność sprawdza domena |
| audit_events | UUID PK, org/project, actor, action, target/version, outcome, UTC, request ID, minimalny delta; append-only dla roli aplikacji |
| idempotency_receipts | UNIQUE(actor,scope,operation,key), fingerprint, status/body/headers, expires_at; commit wspólny z mutacją |
| sessions / oidc_flows | Hash opaque ID, principal, TTL, CSRF/state/nonce/PKCE state, szyfrowane tokeny; brak sekretów w danych projektu |

Audyt mutacji w SP-01 zapisuje `outcome=allowed` zgodnie z enum OpenAPI;
`denied` jest zarezerwowane w kontrakcie, lecz odmowy dostępu są na tym etapie
osobną telemetrią, nie fikcyjnymi zatwierdzonymi zmianami domeny.

UUID nie jest mechanizmem autoryzacji. Referencje projektu są częścią zapytań
i kluczy obcych, nie filtrem dopisywanym dopiero w UI. Oddzielna rola migracji,
rola runtime bez DDL, UPDATE/DELETE opublikowanych wersji i edycji audytu.
Retencja/cleanup sesji/receiptów używa ograniczonego procesu, nie prawa do
usuwania danych biznesowych. Nie ustanawiamy RLS jako rzekomo działającego
zabezpieczenia; ewentualne RLS wymaga osobnego kontraktu i testów.

Wszystkie mutacje w S1 serializują się przez lock projektu. Create project
serializuje odpowiedni klucz idempotencji w zakresie organizacji i aktora.
Odwołania wejściowe i zmiany członkostwa są kontrolowane w tej samej transakcji.
Przy deadlock/timeout operacja jest wycofana; klient dostaje bezpieczne 503.

Indeksy: memberships(principal_id,project_id), objects(project_id,created_at,id),
objects(project_id,kind,state,created_at,id), versions(project_id,object_id,number),
audit(project_id,occurred_at,id), receipts(expires_at), sessions(expires_at).
Filtrowanie po nazwie ma limit i benchmark; indeks wyszukiwania dobieramy po
EXPLAIN na fixture, bez obietnicy, że zwykły B-tree obsłuży dowolny substring.

## Treść i digest

Digest to SHA-256 pełnych bajtów UTF-8 JCS samej `definition` wraz z kind
i schema_version; zapis szesnastkowy lowercase 64 znaki. Nie obejmuje nazw
wyświetlanych obiektu, ACL, actor, czasu, ID ani losowego identyfikatora wersji.
Zachowujemy canonical bytes obok JSONB i sprawdzamy zgodność przy odczycie/restore.
JCS nie sortuje tablic, nie normalizuje Unicode ani nie dodaje pominiętych pól.
Liczby w kontrakcie S1 są integerami w zakresie ±(2^53−1); bez NaN/Infinity,
duplicate keys i nieparzystych surrogate. Zmiana kolejności portów zmienia digest.

Nie deduplikujemy pomiędzy projektami ani nie ujawniamy globalnego istnienia
digestu. Ta sama definicja w różnych obiektach może mieć ten sam digest, ale
inne ID i ACL. Brak mechanizmu „pobierz dowolną wersję tylko po hashu”.

## Macierz testów runtime — wszystkie jeszcze niewykonane

| AC | Dokładny zakres dowodu | Warstwa |
|---|---|---|
| AC-01 | create project + grant owner + audit + receipt atomic; rollback i dwa identyczne POST | PostgreSQL/API |
| AC-02 | Macierz ról dla każdego endpointu, w tym metadane, membership i audit | API + UI |
| AC-03 | Cudzy project/object/version, list/filter/cursor i zgodność 404 niewidoczny/nieistniejący | API/security |
| AC-04 | Równoległy PUT draft, PATCH metadata i stale ETag; brak utraty tekstu w UI | DB/API/E2E |
| AC-05 | Brak write endpointu do wersji, odebrane prawa DB, identyczny digest daje tę samą wersję | DB/domena |
| AC-06 | Równoległy retry i inny fingerprint; replay po zmianie ETag, expiry receipt i bieżące ACL | DB/API |
| AC-07 | Fault injection przed/po version insert oraz audit/receipt insert: wszystko albo nic | DB/integracja |
| AC-08 | Przykłady schema, duplikaty portów, złe kind, cross-project/archived reference, payload limit | Kontrakt + API |
| AC-09 | Grant revoke/deactivate principal podczas sesji i retry; autoryzacja po commit odmawia | API/OIDC |
| AC-10 | Podmiana actor/owner/org; self-escalation i wyścig usunięcia dwóch ostatnich owner | API/DB |
| AC-11 | Wyścig archive/finalize, archive źródła, zachowanie wersji i błąd nowej mutacji | DB/domena |
| AC-12 | Restart API i PostgreSQL po commit oraz brak sukcesu dla utraconej transakcji | Integracja |
| AC-13 | Klawiatura, draft/versions/conflict, no-store, sesja i ta sama polityka w surowym API | E2E/UX |
| AC-14 | Exp/issuer/audience/alg/kid, CSRF/Origin, login replay, XSS tekstu/SQL/Python, błędy bez sekretów | Security |
| AC-15 | Upgrade z fixture SP-01, restore do nowej bazy, porównanie ID/ACL/canonical bytes/audit | Migracja/DR |

Regresje review 0.3: callback OIDC z poprawnym state lecz innym/brakującym
cookie przeglądarki nie tworzy sesji; równoczesne callback nie mogą zużyć flow
dwa razy. Retry createProject po odebraniu członkostwa daje 404 mimo globalnego
grantu create; cursor wersji nie przechodzi między dwoma obiektami projektu.

Fixtures: P1 z A-owner/B-editor/C-reader; P2 z E-owner; A i B mogą zmieniać
draft dla testu konkurencji. C nie zapisuje; B nie zmienia grants; E nie widzi
P1. Osobny owner D w P1 do testu konfliktu „ostatni owner”. Principal bez
globalnego grantu nie tworzy projektu. Tokeny są generowane na czas testu.

Walidacja pliku OpenAPI i przykładów JSON wykonywana w SP-00 jest kontrolą
specyfikacji. Nie zalicza AC dotyczących autoryzacji, transakcji lub UI.
Test semantyczny wymaga bazy/polityki i nie może być zastąpiony samym JSON Schema.

## Upgrade i rollback

Nowa baza platformy, brak zmian MLflow/MinIO/legacy workspace. SP-01 tworzy
projekt/principal/membership/audit/session, SP-02 dodaje obiekty i wersje.
Strategia expand-contract: najpierw kompatybilny schema, potem aplikacja,
usuwanie dopiero osobną zmianą po okresie zgodności. Nie zakładamy bezstratnej
migracji downgrade. Rollback to kompatybilny obraz lub restore do NOWEJ bazy
z oknem wstrzymania zapisów i reconciliation; nie nadpisanie istniejącej.

## Warunek review

Sprawdzić zgodność OpenAPI, schematów i powyższych reguł, przyjąć politykę
ról/sesji/retencji technicznej i zatwierdzić rewizję 0.2. Zmiana tych kontraktów
wraca do specyfikacji przed kodem. Ownerzy organizacyjni i firmowe polityki
danych pozostają wymagane przed realnym wdrożeniem, nie są tu domyślane.
