# SPEC-0001 B2a4a — komunikaty wymiany kodu i revocation

Status: Accepted (delegated),2026-09-19. Niezależny review contract_review przed
kodem; przyjęto po doprecyzowaniu status int, kolejności code/verifier i pól
error response. Mandat użytkownika, nie akceptacja własna ani ludzki audyt.
Podzbiór B2-D06/B2-AC02, SPEC-0001 AC-10/14. B2a3 pozostaje ukończonym
komponentem GET/cache. Niniejszy przyrost jest czystą granicą komunikatów OAuth:
nie wykonuje sieci, logowania, weryfikacji podpisu, DB ani nowych tras HTTP.

## Podział pozostałego B2a4

- A4a (ta spec): form/basic encoding i bounded odpowiedzi, jawnie niezaufane DTO.
- A4b (nadal Proposed): POST transport bez retry, reuse A3 bounded lifecycle,
  jawna polityka logowania przy starcie procesu i testy braku sekretów w logach.
- Orchestration przed B2b wymaga osobnej spec: consume_flow commit przed HTTP,
  shared workdeadline z1s rezerwą cleanup, oba podpisy/nonce/at_hash/sub,
  zapis sesji po walidacji i best-effort revoke. A4a nie zalicza tych scenariuszy.

Wstępny review projektu logowania zaleca A4b jawnie wyłączyć wszystkie emitujące
loggery przypiętych httpx/httpcore przy starcie Torii (nie import side effect),
sprawdzać guard przed credentials I/O i zastąpić raw diagnostics skończonymi
zdarzeniami Torii. Koszt w całym procesie wymaga krótkiego ADR i osobnego Accepted
przed implementacją. ContextVar/per-request zmiany poziomów nie są potrzebne.
Uvicorn/gateway/APM pozostają odrębnymi powierzchniami przed B2b.
Źródłowy research ujawnił także logi samego Keycloak26.7.4: PkceUtils DEBUG
zawiera verifier, a OAuth2CodeParser WARN przy replay zawiera składniki kodu.
Przed realnymi testami login/replay potrzebny jawny zakres polityki IdP;
nie dumpować surowych logów Keycloak jako artefaktów negatywnych testów.

## Kodowanie żądań — security/oidc_requests.py

`OAuthRequests(endpoints: RealmEndpoints, client_id: str, client_secret: str)`:

- Korzysta z istniejącej niemutowalnej walidacji RealmEndpoints B2a3, nie tworzy
  własnego parsera origin. Konfiguracja wyłącznie serwerowa. Client ID1..256
  znaków; secret32..8192 bajtów UTF-8. Oba dokładne str, bez C0/C1/surrogates;
  spacje i znaki specjalne dozwolone, zachowane bez trim/normalizacji.
  Zły typ/limit/config ->503 identity_unavailable, bez wartości w błędach/repr.
- Redirect jest wyłącznie public origin z issuer + `/auth/callback`. Nie ma
  argumentu redirect/url w metodzie przyjmującej kod. Nie wyciągamy URL z JWT,
  discovery lub odpowiedzi błędu. Cele POST są skonstruowane ze zweryfikowanego
  backchannel + `/protocol/openid-connect/token` albo `/revoke`.
- `exchange(code: str, verifier: str) -> OAuthRequest`: kod1..4096 ASCII0x21..7e,
  bez spacji/controls, złe wejście401 unauthorized. Verifier jest wewnętrzną
  wartością z B2a1: canonical32B base64url43 (w tym pad bits), sprawdzany przez
  token_hash; błędny verifier503, nie próba obejścia PKCE.
  Kolejność: code401 przed verifier503 przy jednocześnie niepoprawnych wartościach.
- `revoke(refresh_token: str) -> OAuthRequest`: opaque1..16384 ASCII0x21..7e;
  błędna wewnętrzna wartość503. Nie sprawdza podpisu refresh, nie nadaje mu roli
  access token i nie dowodzi, że został wydany przez IdP.
- `OAuthRequest`: frozen/slotted pola `url: str`, `authorization: str`,
  `body: bytes`, każde repr=False. Nie jest HTTPX Request ani adapterem I/O.
  Tylko jawny odczyt sekretnego pola pozwala przyszłemu adapterowi użyć wartości;
  repr/str obiektu nie zawiera żadnego pola. Nie obiecujemy ochrony przed
  dataclasses.asdict, debuggerem lub kodem jawnie wypisującym `.body`.
- Client auth wyłącznie RFC6749 client_secret_basic: client ID i secret najpierw
  osobno application/x-www-form-urlencoded UTF-8 (quote_plus safe=''), następnie
  połączone `:` i Base64 ASCII z prefiksem `Basic `. Zwykłe HTTPX BasicAuth bez
  tej wstępnej form-encoding nie spełnia tego kontraktu dla znaków specjalnych.
  Bez drugiej metody auth w body/query i bez sekretu w URL.
- Body to urlencode stałych list par, ASCII bytes: exchange grant_type=
  authorization_code, code, redirect_uri, code_verifier; revoke token,
  token_type_hint=refresh_token. Każde pole dokładnie raz; reserved characters
  nie tworzą dodatkowych pól. Body <=65536 bytes, Content-Type przyszłego
  adaptera `application/x-www-form-urlencoded`. Brak retry/side effects.

## Odpowiedzi — security/oidc_replies.py

`TokenReply.from_response(status: int, body: bytes) -> TokenReply`:

- Zawsze bounded parser B2a2 decode_object, UTF-8 JSON<=65536 bytes z istniejącymi
  limitami depth/nodes/numbers/duplicate keys. Dokładny status int (nie bool).
  HTTP Content-Type/encoding/deadline kontroluje dopiero A4b przed parserem;
  parsowanie bytes nie jest dowodem bezpiecznego transportu ani autentyczności.
- Status200: wymagane access_token, id_token i token_type. token_type dokładny
  str case-insensitive `Bearer` (bez trim); access/id każdy1..16384 ASCII0x21..7e.
  Refresh opcjonalny: brak ->None; obecny musi być takim samym bounded opaque
  string, null/pusty/zły typ odrzucony. JWT compact/signature/claims sprawdza
  B2a2 później, nigdy ten parser. Celowo nie nazywamy DTO VerifiedIdentity.
- Obecność `error` w200 zawsze503, także obok poprawnych pól. Opcjonalne
  expires_in/refresh_expires_in, jeśli obecne, exact int0..2^53−1; scope opcjonalny
  str0..1024 ASCII0x20..7e. Inne pola ignorowane dopiero po strict bounded JSON;
  nie są zwracane ani zamieniane na grants/URL/display_name.
- Status400 z poprawnym bounded object i dokładnym `error="invalid_grant"`
  ->401 unauthorized. Inne statusy/błędy, invalid_client, malformed reply i
  błędna konfiguracja/format odpowiedzi ->503 identity_unavailable. Error text,
  error_description, error_uri oraz response headers nigdy nie są odbijane.
  Walidacja pól tokens/expires/scope dotyczy200; dla400 po strict JSON klasyfikacja
  wyłącznie po exact error, pozostałe pola ignorowane.
- Wynik frozen/slotted/factory-only z `access_token: str`, `id_token: str`,
  `refresh_token: str | None`, wszystkie repr=False. Nie ma pól roles,claims,
  expires ani email. TokenReply to NIEZAUFANE tokeny do dalszej walidacji.
- `validate_revocation_response(status: int, body: bytes) -> None`: exact int200
  (nie bool, float lub subclass),
  exact bytes0..65536; zawartość ignorowana (RFC7009 response może dotyczyć
  nieistniejącego tokena). Wszystko inne503. Nie wymaga JSON w revocation200,
  nie dowodzi SSO logout ani natychmiastowego cofnięcia access JWT.
- Błędy używają A3 raise_identity_error, bez provider cause/context/sekretów w
  formatted traceback. Pozostaje jawna granica reattach istniejącego caller
  exception przez CPython z A3; nie tłumimy cancellation ani cudzych wyjątków.

## AC i testy przed implementacją

| AC | Wymagany dowód lokalny |
|---|---|
| A4a-01 | Basic UTF-8/form golden vectors: spacje/colon/plus/percent/Unicode; odkodowanie dokładnie odtwarza dwa pola, header nie używa rawcoloncredentials |
| A4a-02 | Stałe endpointy/redirect i exact form fields, injection reserved znaków, code/verifier/refresh/config granice, body bytes limit, frozen repr bez markerów |
| A4a-03 | Token success/error/status/typy/limity/duplikaty/depth/UTF8/ambiguous200; refresh opcjonalny, expires/scope, brak projekcji grants; unsigned input nie tworzy Identity |
| A4a-04 | Revocation200 także empty/nonJSON body, reszta safe503, brak echo URL/errors i brak obietnicy federated logout |
| A4a-05 | Brak I/O/logowania/DB przez moduły, marker nieobecny w repr/str/traceback, niezależny review, regresje backend/PG/FE i kontraktów |

Testy używają wyłącznie syntetycznych stringów/bytes, bez kontaktu z IdP lub
sekretów instancji. Rollback: wycofanie niepodłączonych modułów, bez zmian danych.
Brak nowych zależności/lockfile, Settings/env, migracji, deploy lub routingu.
Nie podnosić całego B2/SP-01 do Verified na podstawie tego komponentu.

Źródła normatywne sprawdzone przez integratora podczas przygotowania:
[RFC6749 client authentication](https://www.rfc-editor.org/rfc/rfc6749.html#section-2.3.1),
[code request](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.1.3),
[token response](https://www.rfc-editor.org/rfc/rfc6749.html#section-5.1),
[RFC7009](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.2).
Dokładny profil lokalnego Keycloak nadal wymaga real Code+PKCE E2E w B2b.
[PkceUtils DEBUG](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/utils/PkceUtils.java#L112),
[OAuth2CodeParser replay WARN](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/utils/OAuth2CodeParser.java#L98).
