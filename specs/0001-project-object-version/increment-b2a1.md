# SPEC-0001 B2a1 — trwały stan tożsamości i sesji

Status: Accepted (delegated), 2026-09-19. Wydzielony przyrost B2a z [planu B2](increment-b2.md).
Agent `contract_review` niezależnie przejrzał spec przed kodem; przyjęto po
poniższych uściśleniach lock order, świeżego zegara oraz wyjątku corrupt refresh.
Podstawa: mandat użytkownika. Nie jest to audyt ludzki ani akceptacja reszty B2.
Nie zmienia wire OpenAPI ani uruchomionego stosu.

## Decyzje w tym zakresie

Przyjmujemy do lokalnego dev/test B2-D01 (sesja Torii niezależna od odświeżania
tokena: absolute8h/idle30min), D03 (principal bez grantów) i wyłącznie poniższą
część D06. Nie przyjmujemy jeszcze D02/04/05 ani transportu/token verifier/HTTP.
Brak natychmiastowego federacyjnego revoke z IdP pozostaje jawnym ograniczeniem
lokalnego profilu; przed firmowym użyciem wymaga oddzielnej decyzji i dowodu.

B2a1 dostarcza wewnętrzny adapter persistence i bezpieczne wartości. Nie może
uwierzytelniać requestów, przyjmować raw claims jako VerifiedIdentity ani wystawić
trasy/debug principal. Jego wejście issuer/sub/display jest dostarczane WYŁĄCZNIE
przez przyszły, sprawdzony adapter JWT/OIDC; testy używają jawnych syntetycznych
tożsamości. Odbiór B2a1 nie jest dowodem poprawności podpisu ani loginu.

## Kontrakty wartości i sekretów

- `Identity(issuer, subject, display_name)` jest DTO wewnętrznym, nie dowodem
  weryfikacji kryptograficznej. Store jest skonfigurowany jednym zaufanym issuer
  i odrzuca inny 401. Subject:1..255 ASCII printable (0x21..0x7e), case-sensitive,
  bez trim/normalizacji; brak fallback email. `display_name` normalizowane z
  name/preferred_username według B2 (C0/C1/surrogate/bidi controls usunięte,
  trim, max200 codepoints, ponowne rstrip po truncation; fallback `Użytkownik`).
  Identity przyjmuje tylko już znormalizowany display_name; nie modyfikuje identity.
- `SecretCodec` używa aktualnego klucza Fernet, nie własnej kryptografii.
  Independent CSPRNG32bytes -> base64url bez padding (43 znaki). Hash SHA256
  wyłącznie kanonicznych tokenów tej długości; nieprawidłowy credential ->401.
  Cipher envelope `{v:1,purpose,record_id,value}` wiąże typ pola i ID rekordu;
  zamiana ciphertext między rekordami lub CSRF/verifier/refresh ->503 i safe error.
  Kod ma stałą allowlist purpose; wartości 1..16KiB UTF-8; envelope bez sekretów
  w repr/exception/log. Żadnego plaintext w rekordach DB i zwracanych logach.
  Uściślenie z review implementacji: `InvalidToken` z decrypt oznacza corrupt;
  operacyjne TypeError/ValueError/OSError providera decrypt nie są dowodem
  corrupt, mają zwykły bezpieczny DomainError503 bez exception context.
  Dopiero błędy deserializacji/kształtu/value odszyfrowanej koperty klasyfikujemy
  jako SecretDecodeError. Nie wolno jednym except mieszać obu etapów.

## Persistence (istniejąca migracja 0001, konto runtime)

Store przyjmuje engine, SecretCodec i trusted issuer. Nie przyjmuje zegara
klienta; wszystkie terminy zależą od clock_timestamp bazy. READ COMMITTED,
transakcje przez istniejącą bezpieczną granicę (DB failure/commit ->503).
Login blokuje principal (upsert), następnie starą sesję; auth blokuje WYŁĄCZNIE
sesję, principal/grants czyta osobnym SELECT bez locku. Revoke/cleanup nie
blokują principal. Nie używać FOR UPDATE na join sesji i principal.
Created/last_seen/expires liczone jednym świeżym clock_timestamp po lockach,
nie default now() sprzed oczekiwania; ważne wyłącznie expires_at > now oraz
last_seen_at > now−30min. Nie obiecujemy cofania operacji autoryzowanej przed
commit dezaktywacji principal; kolejne sprawdzenie po commit odmawia.

1. `create_flow()` generuje state/browser/nonce/verifier, zapisuje tylko hashe
   i zaszyfrowany verifier, TTL5min; zwraca sekrety dopiero po commit. Powstaje
   niezależny flow, nie zmienia sesji. S256 challenge wylicza przyszły adapter.
2. `consume_flow(state,browser)` atomowo blokuje właściwy rekord, po locku
   sprawdza bieżący czas i binding, odszyfrowuje verifier, usuwa i commit przed
   zwrotem `ConsumedFlow(nonce_hash,verifier)`. Zły browser nie zużywa flow;
   expired/missing/used ->401 bez różnicowania. Dwa wywołania: tylko jedno
   zwraca materiał do exchange. Brak jakiegokolwiek I/O sieciowego w store.
3. `provision_identity(identity)` przy zweryfikowanej uprzednio tożsamości:
   singleton org wymagany (brak ->503), unique issuer/sub serializuje równoczesny
   upsert. Aktualizuje tylko display_name i tylko aktywny principal. Inactive
   ->401, nigdy reactivation. Nie tworzy global grant ani membership ani sesji.
4. `create_session(identity,previous_session=None,refresh_token=None)`:
   principal/upsert + nowa sesja + usunięcie wskazanej starej sesji atomowo.
   Stara sesja identyfikowana tylko poprawnym opaque credential tej przeglądarki;
   zmiana konta może zastąpić starą sesję innego principal. Brak pozostałych
   sesji w DELETE. Nieprawidłowy previous credential ignorowany (nie blokuje
   nowego poprawnego login). RefreshToken string do16KiB lub None, szyfrowany
   tylko do późniejszej revocation, nigdy automatycznie odświeżany tutaj.
   Wynik secret session_id/csrf + public principal/expiry; secret fields repr=False.
5. `authenticate_session(session_id)` bierze row lock sesji, sprawdza absolute
   i idle po locku oraz aktywnego principal z issuer równym konfiguracji store,
   odszyfrowuje CSRF, warunkowo touch
   last_seen; brak resurrection. Wynik principal_id/display_name/can_create_project,
   CSRF i expiry; prawa projektu nadal w ProjectService. Inactive/expired ->401.
6. `revoke_session(session_id)` jest wewnętrznym prymitywem dla przyszłego
   zweryfikowanego logout, nie sprawdza HTTP Origin/CSRF. Row lock, odszyfrowanie
   refresh (jeśli obecny), DELETE i commit przed zwrotem do sieciowej revocation.
   Missing/invalid ->401. Corrupt refresh nie może uniemożliwiać lokalnego revoke:
   DELETE zostaje zatwierdzony, wynik ma refresh=None i bezpieczną flagę błędu
   dla przyszłej telemetrii. Błąd DB nie jest sukcesem. Auth/CSRF fasada poza B2a1.
   Wyłącznie dedykowany `SecretDecodeError` (integralność/decode w open) jest
   tłumiony w tym miejscu; inne błędy codec/DB/commit nadal przerywają operację.
7. `cleanup_expired(limit=100)` usuwa max100 flow i max100 sesji (absolute lub
   idle); FOR UPDATE SKIP LOCKED, stabilne kolejności expiry/id, ponowna ocena
   czasu po locku. Brak uruchomienia background job w tym przyroście. Nie usuwa
   principals/projects/audit/grants/receipts, expiry działa bez cleanup.
   Limit to integer1..100, bool odrzucony 422.

Interface adaptera: `IdentityStore(engine,codec,trusted_issuer)`. Wyniki:
Flow(state,browser,nonce,verifier), ConsumedFlow(nonce_hash,verifier),
Principal(principal_id,display_name,can_create_project),
NewSession(session_id,csrf_token,principal,expires_at),
ActiveSession(principal,csrf_token,expires_at),
RevokedSession(refresh_token,secret_error); wszystkie secret fields repr=False.
Cleanup zwraca tuple(count_flows,count_sessions). Codec token helpers:
new_token()/token_hash(), seal/open(purpose,record_id,value/ciphertext),
record_id = canonical lowerhex hash64. Wyniki nie są publicznymi HTTP DTO.

Login/callback wspólny deadline, user-visible cookie/session contract, B2-D05
logout HTTP i federacyjny revoke będą osobnym przyrostem. Poprzedni app factory
pozostaje bez nowych tras. Brak migracji, seeding aktywnej bazy lub deploy.

## Wymagane dowody B2a1

- Pure tests secret generation/canonical hashes/S256 input, bound encryption,
  tampering, missing purpose/id, bounds, bez sekretów w repr/exception;
  normalizacja Unicode i oddzielenie identity od nazwy.
- Real PG: flow zapis tylko hash/cipher, TTL i wrong-browser, dwa consume,
  expiry podczas lock wait, commit failure nie zwraca consumed materiału.
- Real PG: równoczesny issuer/sub provisioning ->1principal, brak grants;
  inactive nie wraca, obcy issuer i brak org odmawiają; rollback podczas sesji
  cofa także provisioning i rotację starej sesji.
- Real PG: absolute/idle expiry, touch nie odnawia absolute, deactivate,
  logout/touch race i auth po commit revoke, sesje innych urządzeń zachowane,
  zły key/ciphertext odmowa, corrupt refresh nie blokuje DELETE, bounded cleanup.
  Regresje lock order: auth vs login z tą samą identity/starą sesją; corrupt
  refresh + błąd commit nadal daje503 i pozostawia lokalny rekord sesji.
  Review implementacji: sesja issuerA nie jest akceptowana przez store issuerB
  nad tą samą bazą/kluczem; 401 bez touch. Wewnętrzny revoke nadal może usunąć
  rekord wskazany poprawnym opaque credential (HTTP authorization osobno).
  Awaria operacyjna decrypt (TypeError/ValueError/OSError) podczas revoke daje
  zwykły503 bez sekretów/chaining i pozostawia sesję w DB; osobne testy pure/PG.
- B1 regresje; nowa instancja store czyta sesję z tym samym kluczem (NIE dowód
  restartu procesu/bazy). Wszystkie fixtures wyłącznie w istniejącym efemerycznym
  harnessie B1 z nową bazą na test, bez nowych uprawnień SQL i firmowych danych.
- Ruff/strict mypy/kontrakty/testy, niezależny review, dowody i lokalny commit.
  B2-AC01/02/JWT/real OIDC/HTTP/UI/restart/restore nadal jawnie niewykonane.
