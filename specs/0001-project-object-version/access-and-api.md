# SPEC-0001 — tożsamość, prawa i semantyka API

Rewizja 0.2, In review; brak akceptacji. Normatywna propozycja dla SP-01/02.
Kontrakt maszynowy: [OpenAPI](contracts/openapi.json).
Schemat treści definicji: [JSON Schema](contracts/definitions.schema.json).

## Tożsamość i sesja

Jedna organizacja instalacji. Principal jest identyfikowany parą OIDC
`issuer + sub`, nigdy samym emailem. Aktywny principal i granty są w bazie Torii.
Pierwsze dozwolone logowanie provisionuje principal bez członkostw. Prawo
`project.create` jest osobnym grantem globalnym, przyznawanym podczas bootstrapu
lub administrowania; nie wynika z treści tokena przesłanej przez użytkownika.

Proponowany testowy IdP: Keycloak przez OIDC discovery. Dostawca firmowy pozostaje
wymienny. Przeglądarka używa backendowej sesji po Authorization Code + PKCE S256,
state i nonce; JWT/refresh token nie trafiają do localStorage ani JavaScript UI.
Tokeny odświeżania, jeżeli użyte, pozostają szyfrowane po stronie serwera.

- Cookie `__Host-torii-session`: losowy opaque ID, Secure, HttpOnly, SameSite=Lax,
  Path=/, bez Domain. Sesja: maksymalnie 8 h, bezczynność 30 min; rotacja przy login.
- Żądania cookie modyfikujące stan wymagają nagłówka `X-CSRF-Token` powiązanego
  z sesją oraz zgodnego Origin. `GET /api/v1/session` dostarcza token CSRF
  uprawnionej przeglądarce; odpowiedzi sesyjne i danych mają `Cache-Control: no-store`.
- SDK używa `Authorization: Bearer` z audience `torii-api`. Akceptujemy wyłącznie
  access token: allowlist issuer/algorytmu, podpis/JWKS, audience, exp/nbf;
  tolerancja zegara 30 s. Testowy access token żyje 5 min. ID token nie jest access tokenem.
- Równoczesne cookie sesji i Bearer daje 400 `ambiguous_credentials`.
  Dla Bearer bez cookie CSRF nie jest wymagany; granty są nadal sprawdzane w bazie.
- Logout usuwa sesję natychmiast i próbuje unieważnić delegację IdP;
  awaria IdP nie przywraca lokalnej sesji. Jawne GET logout jest niedozwolone.
- Login: `GET /auth/login` (303 do IdP), callback: `GET /auth/callback`
  (303 na `/projects` albo stały ekran błędu). State/nonce/PKCE są jednorazowe,
  z TTL 5 min. Brak dowolnego parametru redirect URL, brak open redirect.
- Brak dostępu do IdP/JWKS bez ważnego klucza z cache zamyka nowe logowania
  i walidację nieznanego klucza. Nie wyłączamy weryfikacji na czas awarii.
  Cache znanych kluczy maks. 5 min; klucz o nieznanym `kid` wymusza ograniczony
  częstotliwością refresh. Usunięty klucz nie jest używany po odświeżeniu.

Każda operacja sprawdza aktywność principal i aktualne członkostwo. Odebranie
grantu blokuje żądania autoryzowane po commit tej zmiany; wcześniej rozpoczęty
odczyt może się zakończyć. Timeout API 15 s ogranicza okno takich odczytów.
Nie obiecujemy cofnięcia danych już pobranych przez użytkownika.

## Macierz praw S1

Brak członkostwa = brak dostępu, również dla administratora technicznego.
Role są projektem polityki aplikacji, nie nazwami ról SQL.

| Operacja | reader | editor | owner |
|---|---|---|---|
| Odczyt projektu, katalogu, draftu, wersji | tak | tak | tak |
| Utworzenie obiektu, rename, edycja draftu, finalizacja | nie | tak | tak |
| Archiwizacja obiektu | nie | nie | tak |
| Lista i zmiana członkostw | nie | nie | tak |
| Odczyt audytu projektu | nie | nie | tak |
| Nadanie owner innemu aktywnemu principal | nie | nie | tak |
| Usunięcie/degradacja ostatniego owner | nie | nie | nie |
| Edycja opublikowanej wersji lub trwałe usunięcie historii | nie | nie | nie |

Creator otrzymuje owner w tej samej transakcji co projekt. Samo `created_by`
obiektu nie nadaje dodatkowych praw. Owner może zrezygnować, jeśli pozostaje
inny owner. Uprawnienia reader/editor/owner nie oznaczają zgody na produkcję.
Role recenzenta/operatora oraz współdzielenie między projektami dojdą osobno.
S1 ogranicza projekt do 100 członków. Pełna polityka jest osobnym zasobem
`GET/PUT /api/v1/projects/{project_id}/access-policy`: lista principal/role,
revision i mocny ETag. PUT atomowo zastępuje tę listę, bez duplicate principal,
z co najmniej jednym aktywnym owner. Identyczna polityka to no-op. Widok
stronicowany memberships służy odczytowi, nie używa wspólnego ETag różnych stron.
W S1 wybór członka używa znanego principal ID; brak przeszukiwalnego globalnego
katalogu osób. Nieistniejący/nieaktywny principal daje ogólne 404, bez emaila.

## Wspólne reguły HTTP

JSON UTF-8, limit body 256 KiB przed parsowaniem, maks. głębokość JSON 32.
Nazwy projektów/obiektów 1–120 znaków bez skrajnych białych znaków, opis do
4000 znaków; dopuszczalne identyczne nazwy, tożsamość wynika z UUID.
Endpoint bez requestBody odrzuca niepusty body jako 400 zamiast go ignorować.
Nieznane pola odrzucamy, duplicate keys i niepoprawny JSON: 400. Nie wykonujemy
deklaracji Python/SQL. Głębokie/duże dane: 413; zły Content-Type: 415.
Serwer generuje UUIDv4 i czas UTC, nie przyjmuje actor, project, digest, status
ani version number z pól wejściowych. `kind` jest niezmienne po utworzeniu obiektu.

Listy: `limit` 1–100, domyślnie 50; nieprzezroczysty podpisany cursor, TTL 15 min,
powiązany z principal, projektem, filtrem i typem listy. Sortowanie `(created_at,id)`
rosnąco; wersje `(number,id)` rosnąco; audit `(occurred_at,id)` rosnąco.
Lista członkostw używa `(created_at,principal_id)` rosnąco. Brak total count.
Filtr nazw `q` to literalny case-insensitive substring, 1–100 znaków, nie regex.
Przy paginacji stale sprawdzamy bieżące ACL; nie gwarantujemy snapshotu listy
między stronami. Dodane później rekordy mogą trafić na kolejną stronę.

Cursor obcego aktora, uszkodzony lub wygasły: 400 `invalid_cursor` bez rozróżnienia.
Filtry i limity nie mogą wpływać na zakres praw. Brak nagłówka autoryzacji: 401.
Zasób nieistniejący lub niewidoczny: identyczne 404. Użytkownik znający projekt,
lecz bez prawa do operacji: 403. Nieznana metoda: 405.

Pozostałe błędy: 422 `validation_failed` (z bezpiecznymi JSON Pointer pól),
409 konflikt biznesowy lub klucza idempotencji, 412 nieaktualny ETag,
428 brak If-Match, 429 limit żądań, 503 brak wymaganej zależności.
Model błędu: `application/problem+json`, type `urn:torii:problem:<code>`,
title/status/code/request_id/errors; bez SQL, tokenów, tracebacks i wartości wejść.
Każda odpowiedź ma serwerowy `X-Request-ID`; nie logujemy dowolnej treści
dostarczonego przez klienta nagłówka jako zaufanego ID.

## ETag, transakcje i idempotencja

- ETag draftu: `"draft:<object_uuid>:<revision>"`; całego obiektu:
  `"object:<object_uuid>:<revision>"`; polityki: `"acl:<project_uuid>:<revision>"`.
- PUT draft, PATCH object, archive, finalizacja oraz PUT access-policy
  wymagają pojedynczego mocnego If-Match, bez wildcard i list. Słaby lub błędny
  ETag: 400; poprawny, lecz stary: 412. Finalizacja porównuje ETag draftu.
- Utworzenie obiektu atomowo zakłada draft revision 1. Finalizacja zwiększa
  licznik wersji, ale nie revision draftu, bo jego treść się nie zmieniła.
- Revision obiektu rośnie także przy zmianie draft_revision lub latest_version_id,
  aby mocny ETag odpowiadał całej reprezentacji GET object. ETag polityki obejmuje
  jej pełną listę posortowaną po principal_id, nie stronę kolekcji memberships.
- Opublikowanie identycznego digestu tego samego obiektu zwraca istniejącą
  wersję 200, bez nowego zdarzenia publikacji; nowy digest daje 201 i nową wersję.
  Porównanie obejmuje canonical bytes, nie tylko hash. Draft i metadane obiektu
  są odrębne: rename nie zmienia treści/historycznego digestu definicji.
  latest_version_id oznacza wersję o najwyższym numerze, nie ostatnio zwrócony
  receipt; finalizacja wcześniejszego identycznego payloadu nie cofa tego wskaźnika.
- POST projektu/obiektu, finalizacja, archive i zmiany członkostw wymagają
  `Idempotency-Key`: UUIDv4. Klucz żyje 24 h od commit; zakres = principal,
  operacja i projekt (organizacja przy create project).
- Fingerprint obejmuje metodę, kanoniczną ścieżkę, If-Match i JCS body
  (pusty body jako null). Ten sam klucz i inny fingerprint daje 409.
- Kolejność: uwierzytelnienie, widoczność/prawo operacji, walidacja obwiedni,
  sprawdzenie idempotencji, sprawdzenie If-Match, reguły domeny, zapis.
  Retry zatwierdzonej operacji zwraca jej status/body i ETag/Location, nawet jeśli
  ETag jest już historyczny; świeży X-Request-ID identyfikuje retry. Nie omija ACL.
- Każda mutacja projektu bierze row lock projektu, autoryzuje ponownie i zapisuje
  stan + audyt + receipt idempotencji w jednej transakcji. W S1 serializujemy
  mutacje per projekt dla prostoty poprawności; koszt mierzymy przed zmianą modelu.
- Identyczny PUT draft jest no-op bez nowej revision; ten sam efekt PATCH metadata
  jest no-op. Stare If-Match nadal daje 412. Błędy 4xx/5xx nie zajmują klucza
  idempotencji na 24 h. Lock timeout: 503 z Retry-After, bez częściowego zapisu.
- Archiwizacja tylko active → archived. Historyczne wersje pozostają czytelne.
  Nowa mutacja archived obiektu daje 409 `object_archived`; powtórzenie archive
  z nowym kluczem też 409. Retry starego zatwierdzonego klucza jest odczytem receipt.

## Walidacja semantyczna definicji

`source.binding` i `connection_binding` są nazwami logicznymi, nie sekretami
ani ścieżkami hosta. S1 przechowuje deklarację niezwiązaną z realnym źródłem.
Moduł/callable Python jest nazwą, nie dowodem istnienia kodu ani gotowości runu.
Parametry w S1: string/bool/bezpieczny integer, bez dowolnego zagnieżdżonego JSON.
Typy i formaty rozszerza nowa wersja schematu, nie `additionalProperties: true`.

Porty mają unikatowe nazwy w obrębie inputs i outputs. Opcjonalny
`dataset_object_id` na porcie input może wskazać wyłącznie aktywny Dataset
w tym samym projekcie. Nieobecność oznacza unbound. Draft/finalizacja sprawdzają
referencje w transakcji. Archiwizacja źródła nie przepisuje starych wersji;
przyszłe wykonanie musi sprawdzić aktualne wiązania. Cross-project reference
daje 422 z ogólnym `invalid_reference`, bez informacji o obcym obiekcie.

## Podstawy wybranych formatów

Deterministyczne kodowanie definicji oprzemy o
[JCS / RFC 8785](https://www.rfc-editor.org/rfc/rfc8785), bez własnej normalizacji
Unicode. Wspólny format błędów opiera się na
[Problem Details / RFC 9457](https://www.rfc-editor.org/rfc/rfc9457).
Integracja dostawcy tożsamości wykorzystuje
[OIDC w Keycloak](https://www.keycloak.org/securing-apps/oidc-layers).
Zasady i wartości limitów powyżej są propozycją Torii, nie wymaganiami tych źródeł.
