# SPEC-0001 — przyrost B1: transakcje projektów

Status: Accepted (delegated), 2026-09-19. Zakres SP-01; semantyka 0.4, bez zmiany
OpenAPI 0.2.0. Przegląd techniczny agenta `contract_review` przed implementacją:
zaakceptowano po uściśleniu TTL receipt, UUID per pole, izolacji odczytów/mutacji
i widoczności receipt przed fingerprint. Podstawa: mandat; nie audyt ludzki.

## Granica przyrostu

Implementujemy usługę aplikacyjną PostgreSQL dla create/list/get project,
list memberships, get/replace access policy oraz list audit. Nie udostępniamy
jeszcze endpointów biznesowych HTTP: zaufany `actor_id` będzie dostarczany przez
osobny adapter OIDC, nie przez payload, nagłówek debug ani fallback identity.
To dowód transakcji i autoryzacji usługi, nie odbiór API/OIDC/UI ani całego SP-01.

Usługa korzysta wyłącznie z konta runtime, istniejącej migracji 0001 i świeżego
stanu aktywnego principal/grant/membership. Każda metoda ma własną transakcję;
caller nie może przekazać własnego SQL ani połączenia z uprzywilejowaną rolą.
DTO wyjściowe odpowiadają publicznym schematom; brak pełnego rekordu DB w wyniku.

## Reguły wykonania

- Wejście body jest obiektem z uprzednio sprawdzonego strict JSON. Walidacja
  schematu (unknown fields, typy bez coercion, UUID zgodny z konkretnym polem,
  limity tekstu, U+0000; v4 wymagane dla Idempotency-Key i ID serwera)
  następuje po autoryzacji. Odrzucone dane nie trafiają do wyjątków/logów.
- `create` serializuje klucz actor/org/operation/idempotency przez transaction
  advisory lock wyliczony ze stabilnego SHA-256; kolizja oznacza tylko czekanie.
  Ponownie sprawdza uprawnienia po uzyskaniu blokady. UUID serwera są v4.
- `replace policy` blokuje wiersz projektu FOR UPDATE, następnie ponownie
  sprawdza aktywność i uprawnienia. Inne mutacje projektu muszą użyć tej samej
  kolejności. Brak członkostwa to 404, za mała rola to 403; nieaktywny actor 401.
- Poprawny syntaktycznie Idempotency-Key (UUIDv4) i If-Match są sprawdzane przed
  odczytem receipt; porównanie ETag ze stanem dopiero po sprawdzeniu receipt.
  Odpowiedź replay wymaga aktualnych praw, także widoczności utworzonego projektu
  przed porównaniem fingerprint (także przy innym payload retry).
  Fingerprint: SHA-256 JCS obiektu method/path/if_match/body, bez request ID.
- Receipt jest ważny 24 h według czasu bazy, zapisany w transakcji z mutacją
  i audytem; TTL zaczyna się przy zapisie. Wygasły receipt można zastąpić pod
  tym samym lockiem. Błędy nigdy nie zapisują receipt. No-op ACL zapisuje receipt,
  lecz nie audyt ani nową rewizję. Replay zwraca pierwotne body/status/ETag/Location.
- ACL jest pełnym zastąpieniem; niezmienieni członkowie zachowują created_at.
  Wszyscy wskazani principals należą do organizacji i są aktywni; przynajmniej
  jeden owner. Wzrost rewizji ponad bezpieczny integer odmawia 409 conflict.
  Audyt zawiera wyłącznie identyfikatory/role, nigdy nazwy/opisy ani treści danych.
- Listy stosują ACL w SQL przed filtrem, sortowaniem i limitem. Keyset pagination
  używa UTC timestamp + UUID; cursor wiąże actor, pełną ścieżkę kolekcji i q.
  q jest literalnym case-insensitive substring: %, _ i backslash nie są wildcard.
  limit 1..100 (default50); q 1..100 bez NUL; nieprawidłowy cursor to 400.
- Lock timeout/deadlock/serialization failure/unavailable DB -> bezpieczne 503,
  rollback całej transakcji. Błędy integralności nie są fałszywym sukcesem.
  Dokładna treść SQL/parametry/DSN nie pojawia się w błędzie domenowym.
- Uprawnienia sprawdzane ponownie po locku zapewniają odmowę po zakończonym revoke;
  odczyt rozpoczęty przed commit revoke może zwrócić stan sprzed tego commit.
  Dezaktywacja operatora nie jest nowym endpointem B1; invariants przyszłego
  procesu dezaktywacji wymagają osobnej specyfikacji.
- Mutacje używają READ COMMITTED: sprawdzenie po locku widzi zakończony revoke,
  nie snapshot sprzed oczekiwania. Odczyty używają read-only REPEATABLE READ,
  by body polityki i jej ETag pochodziły z jednego spójnego snapshotu.

## Dowody wymagane dla B1 (nie zastępują wszystkich AC SPEC)

1. AC-01/06/07: atomic create+owner+audit+receipt; dwa równoległe identyczne
   create tworzą jeden projekt; inny fingerprint 409; awaria audytu/receipt
   cofa całość. Odczyt z nowej instancji usługi widzi committed state.
2. AC-02/03/09/10: role matrix, nieaktywny actor, brak globalnego grantu,
   invisible/missing 404, listy i filtrowanie bez wycieku, replay po revoke
   i revoke zatwierdzony podczas oczekiwania mutacji na lock.
3. AC-06/10: stale/missing/malformed If-Match, no-op ACL, receipt replay pomimo
   zmiany rewizji, expiry, ostatni owner i równoległe próby zmiany dwóch ownerów.
4. Listy membership/audit oraz cursor context, tie timestamp, literal q;
   wyniki walidowane przeciwko kanonicznemu OpenAPI.
5. Migracje i testy real PostgreSQL na efemerycznym nowym zasobie z losowymi
   sekretami, dedykowaną etykietą/identyfikatorem; nie w istniejącej bazie
   test-abcdef012345 i nigdy w legacy. Harness usuwa wyłącznie zasoby, których
   dokładne ID i etykietę utworzenia sprawdził; bez bind root .env/legacy volume.
6. Unit/schema tests, strict mypy, Ruff, dotychczasowe regresje. Brak zmiany
   gotowości health i uruchomionej aplikacji do czasu osobnej integracji auth.
   Lokalna bramka przyjmuje jawne `-IncludePostgres`; lokalna definicja workflow
   uruchamia ten sam harness po testach jednostkowych, bez sekretów repozytorium.
   Sam zapis workflow nie oznacza uruchomienia zdalnego CI.

Braki po B1: HTTP authorization order/CSRF/OIDC, E2E, process/database restart,
restore, benchmark/rate limiting/metrics/retention/security gates. Nie zaznaczać
ich PASS na podstawie nowych testów warstwy aplikacyjnej.
