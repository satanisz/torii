# SPEC-0001 — propozycja przyrostu B2: tożsamość i integracja HTTP

Status: **Proposed**, 2026-09-19. Autor propozycji: agent `contract_review`.
Wymaga niezależnego przeglądu integratora przed Accepted (delegated) i kodem.
Nie zmienia samodzielnie semantyki 0.4, OpenAPI 0.2.0 ani statusu AC runtime.

## Cel, zależności i granica

Połączyć rzeczywistą tożsamość z trwałą usługą projektów B1, bez debug identity,
uprawnień wywiedzionych z emaila/roli IdP ani sekretów w JavaScript. Obowiązują
[kanoniczne reguły](access-and-api.md), [OpenAPI](contracts/openapi.json),
[zapis i testy](data-and-tests.md), SPEC-0002 i SPEC-0017. B2 obejmuje części
SPEC-0001 AC-01/02/03/06/07/09/10/12/13/14, nie obiekty i wersje SP-02.

Zbadany punkt wyjścia: `config.py`, migracja `0001_projects`, B1 ProjectService
oraz realm generowany przez `deploy/platform/provision.ps1`. Istnieją tabele
principals/sessions/oidc_flows, ale nie ma wykonanej integracji OIDC ani HTTP
projektów. Realm ma confidential client `torii-web`, Code + S256, audience
`torii-api` tylko w access token, token 300 s, SSO idle 1800 s/max 28800 s.
Password grant, implicit i service accounts są wyłączone i pozostają wyłączone.

| Przyrost | Dostarczenie | Granica odbioru |
|---|---|---|
| B2a | Adapter discovery/JWKS/JWT/code exchange, normalizacja claims, trwałe flows/principals/sessions, testy unit i real PostgreSQL | Bez nowych tras HTTP, bez twierdzenia o działającym login UI |
| B2b | Fasada HTTP auth/session/projektów, CSRF, podłączenie istniejącego UI, izolowany bootstrap testu i real Keycloak E2E | Odbiór konkretnych ścieżek wieloużytkownikowych; nie cały SP-01 ani release enterprise |

Poza zakresem: firmowy IdP/MFA, organizacje wielodzierżawne, SCIM, admin UI,
publiczny klient OAuth dla SDK/device flow, introspection każdego żądania,
backchannel logout, refresh worker, wykonywanie kodu, dane/MLflow/Flow.
Nowa sesja nie jest zgodą na produkcję. Keycloak pozostaje lokalnym testowym IdP.

## Decyzje wymagające review przed implementacją

Poniższe rekomendacje nie są samodzielnie zatwierdzonymi zmianami kontraktu.
Integrator zapisuje rozstrzygnięcie i zgodne aktualizacje canonical/ADR/OpenAPI
przed kodem zależnej części; nie musi rozstrzygać niezależnych przyszłych etapów.

| ID | Rekomendacja i konsekwencja | Blokuje |
|---|---|---|
| B2-D01 | Sesja lokalna 8 h/30 min bez odnawiania tokenów. Refresh token, jeśli wydany, szyfrujemy wyłącznie dla best-effort revocation przy logout. Brak `offline_access`. Dezaktywacja w Torii działa przy kolejnym żądaniu, samo wylogowanie/dezaktywacja w IdP nie unieważnia istniejącej sesji Torii natychmiast. Wymaga jawnego przyjęcia lokalnego ograniczenia; przed firmowym wdrożeniem osobna decyzja o federacyjnym revoke. | B2a |
| B2-D02 | Profil lokalny: RS256, zweryfikowany access JWT z `aud=torii-api` i provider-specific oznaczeniem rodzaju `typ=Bearer` w claims. ID token: audience wyłącznie `torii-web`, nonce i osobna ścieżka walidacji. Potwierdzić profil claims/domyślny algorytm na przypiętym Keycloak; nie utożsamiać payload `typ` z JOSE `typ` ani standardem wszystkich IdP. | B2a |
| B2-D03 | Provisioning po zweryfikowanym login lub Bearer może utworzyć principal bez grantów; aktualizuje wyłącznie bezpieczne display_name, nigdy active/org/identity/uprawnień. Brak organizacji zamyka logowanie jako błąd zależności. Fixture organizacji i jawny grant tworzy oddzielny operator/harness, nigdy „pierwszy użytkownik = admin”. | B2a; bootstrap B2b |
| B2-D04 | Callback toleruje ograniczone `session_state` i `iss` z Keycloak; obecny `iss` musi być równy issuer. Pozostałe rozszerzenia OAuth ignorowane po limitach, nigdy używane jako URL/tekst błędu. Duplicate code/state/error/iss/session_state odrzucane. Dopisać parametry/limity do canonical/OpenAPI przed fasadą. | B2b |
| B2-D05 | Logout wymaga aktywnej cookie session i CSRF; Bearer-only lub brak sesji 401, cookie+Bearer 400. Po potwierdzonym DELETE: clear cookie i 204 nawet przy awarii revocation. Awaria lokalnego DELETE: 503, bez deklaracji sukcesu i bez usuwania cookie umożliwiającego retry. Wygasła/niepoprawna sesja: 401 + clear cookie. | B2b |
| B2-D06 | Zatwierdzić poniższe limity, normalizację, mapowanie błędów, czyszczenie TTL oraz kolejność walidacji. B2b osobno doprecyzuje rate limiter SPEC-0002 i zaufane źródło IP za gateway, zamiast ufać klientowskiemu X-Forwarded-For. | Odpowiednia część |

## B2a — kontrakt adapterów i trwałego stanu

### 1. OIDC, sieć i JWKS

- Konfiguracja pozostaje jawna i fail-closed: obecne `TORII_*`/`*_FILE`, profile
  dev/test, sekretne pola bez repr. Nie czytamy `.env` automatycznie i nie
  dodajemy domyślnych kluczy. HTTP do hosta `identity` jest wyłącznie istniejącym
  wyjątkiem sieci dev; HTTPS zawsze weryfikuje certyfikat, brak `verify=False`.
- Discovery ma dokładny publiczny issuer. Authorization endpoint jest publiczny;
  token/JWKS/revocation korzystają z jawnego backchannel. Adapter lokalny uznaje
  tylko dokładne origin i ścieżki skonfigurowanego realm: auth/token/certs/revoke
  pod `protocol/openid-connect/`. Dopuszcza zweryfikowany publiczny albo
  backchannel URL metadanych tych endpointów i mapuje do ustalonego celu;
  nie wykonuje dowolnego URL z discovery, JWT (`jku`/`x5u`) ani requestu.
- Dedykowany klient HTTP bez redirectów, bez proxy/netrc z otoczenia
  (`trust_env=False`), z limitami połączeń. Proponowane limity: connect 2 s,
  cała operacja z body 5 s, discovery/JWKS/token response do 64 KiB po dekodowaniu,
  do 32 JWK, JWT do 16 KiB, `kid` do 128 znaków. Nie ma automatycznego retry POST
  wymiany code ani retry revocation w tle. Cały callback mieści się w 15 s API;
  wspólny deadline obejmuje kolejne zależności, nie po 15 s dla każdej z nich.
- JWKS cache per issuer/proces najwyżej 5 min od skutecznego pobrania, zegar
  monotoniczny; discovery proponowane również maks. 5 min. Jedna współdzielona
  operacja odświeżenia, nie fetch dla każdego requestu. Nieznany `kid`: najwyżej
  jeden refresh na issuer na 30 s/proces, także po nieudanej próbie; brak
  nieograniczonego słownika negatywnych kid. Są to limity lokalnego single-worker
  profilu, nie deklaracja rozproszonego limitera.
- Sukces refresh atomowo zastępuje zestaw: usunięty klucz nie pozostaje używalny.
  Nie przedłużamy TTL po timeout/304 bez zdefiniowanej rewalidacji. Przy awarii
  można użyć znanego, niewygasłego cache; bez takiego klucza fail-closed. Po
  poprawnym refresh brak kid to niepoprawny credential, nie losowy fallback key.
  Niedostępna zależność bez ważnego cache to bezpieczne 503; nigdy 200 ani pominięcie podpisu.

### 2. Dwa rozłączne walidatory tokenów

- Korzystamy z przypiętej biblioteki kryptograficznej, nie własnego RSA/JWS.
  Serwerowa allowlist RS256, RSA co najmniej 2048 bitów, jednoznaczny kid i
  zgodne przeznaczenie klucza. `none`, HMAC/asymmetric confusion, private JWK,
  nieobsługiwane `crit`, JWE i wieloznaczne klucze są odrzucane. Nie dobieramy
  dozwolonego algorytmu na podstawie niezaufanego JWT.
- Bounded parsing odrzuca duplicate JSON keys, złe UTF-8, non-finite liczby i
  błędne typy claims/header. Claims są niezaufane do końca weryfikacji podpisu.
  Samo decode nie tworzy VerifiedIdentity. Required claims są jawne; nie
  polegamy na tym, że biblioteka sprawdza datę tylko wtedy, gdy claim istnieje.
- Obie ścieżki wymagają dokładnego issuer, poprawnego niepustego sub do 255
  znaków ASCII bez znaków sterujących, exp i prawidłowego audience. Issuer/sub
  pozostają case-sensitive, bez trim/casefold/normalizacji i bez fallback email.
  Daty są liczbami całkowitymi, nie bool/string; exp/nbf mają skew 30 s,
  obecne iat nie może być w przyszłości poza skew. Brak nbf jest dozwolony.
- Callback wymaga ID token z iat, audience zaufanego klienta, zgodnego azp
  jeśli obecny oraz nonce zgodnego z hash w zużytym flow. Podpis sprawdzamy
  także dla tokena otrzymanego bezpośrednio z token endpoint. Jeśli jest at_hash,
  sprawdzamy go względem otrzymanego access token. Lokalny adapter dodatkowo
  weryfikuje access token i zgodność issuer/sub obu tokenów oraz token_type Bearer.
- Bearer API wymaga access token audience `torii-api`; ID token, refresh token
  i token innego przeznaczenia nie przechodzą nawet z poprawnym podpisem. Nie
  przyjmujemy tokena z query/body/cookie ani tokena pozbawionego podpisu.
  Weryfikacja JWT nie nadaje żadnego prawa do projektu.

Reguły rozdzielenia rodzajów tokenów są zgodne z kierunkiem
[RFC 8725, sekcje 3.8–3.12](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.8).
Weryfikacja ID token opiera się na
[OIDC Core 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation).
Powyższe ograniczenia profilu i limity są propozycją Torii, nie uniwersalnymi
wymaganiami wszystkich implementacji OIDC.

### 3. Principal i display_name

- Jedynym kluczem mapowania jest zweryfikowane `(issuer, sub)` i pojedyncza
  organizacja z bazy. Unikatowy constraint rozstrzyga równoczesne pierwsze
  logowania; nie tworzymy dwóch principal ani nie łapiemy dowolnego błędu DB
  jako sukcesu. Inactive principal nie zostaje reaktywowany przez login/upsert.
- Wyświetlana nazwa: pierwszy poprawny string z `name`, następnie
  `preferred_username`; po sanitizacji pusty/złego typu oznacza następny wybór,
  ostatecznie stałe `Użytkownik`. Bez emaila lub surowego sub jako fallback.
  Sanitizacja: usunięcie C0/C1, surrogate i bidi-control U+061C/U+200E/U+200F/
  U+202A–U+202E/U+2066–U+2069, trim Unicode whitespace, do 200 punktów kodowych.
  Pozostałe Unicode nie jest normalizowane; to nazwa opisowa, nie identyfikator.
  UI nadal renderuje ją jako tekst, nigdy HTML.
- Aktualizacja nazwy nie zmienia ID, org, active, created_at, memberships ani
  global_grants. Brak nowych endpointów admina/people search. SQL parametryzowane,
  runtime nadal nie ma prawa zapisu organizacji/global_grants.

### 4. Jednorazowy flow i sesja

- State, nonce, browser binding, PKCE verifier, session ID i CSRF: niezależne
  wartości CSPRNG co najmniej 32 bajty, base64url bez padding. State/browser/
  nonce/session przechowywane jako SHA-256; verifier, CSRF i opcjonalny refresh
  zaszyfrowane obecnym kluczem Fernet. Szyfrowane payloady wiążą rodzaj i ID
  flow/session, aby ciphertext nie dało się zamienić pomiędzy rekordami/polami.
  Błąd odszyfrowania zamyka operację, bez logowania ciphertext lub sekretu.
- Start zapisuje flow z TTL 5 min według czasu DB, commit przed 303/cookie.
  Authorization request zawiera tylko kontrolowane client_id, redirect_uri,
  response_type=code, scope=openid profile, state, nonce i S256 challenge.
  Kolejny login rotuje cookie flow; w wielu kartach działa ostatni rozpoczęty
  flow. Nie usuwamy istniejącej sesji tylko dlatego, że rozpoczęto nowy login.
- Callback musi mieć właściwe state i cookie browser, ważny TTL oraz dokładnie
  jeden z code/error. Zużywa pasujący flow atomowym DELETE RETURNING z commit
  **przed** wymianą code. Błędny browser nie zużywa cudzego rekordu. Tylko jeden
  równoległy callback może wykonać exchange; błąd wymaga nowego login, nie replay.
  Żadnego requestu sieciowego pod otwartą transakcją/lockiem PostgreSQL.
- Po pełnej walidacji: principal + nowa sesja + unieważnienie poprzedniej sesji
  przedstawionej przez tę przeglądarkę w jednej transakcji. Inne urządzenia nie
  są wylogowywane. Cookie dopiero po commit; błąd commit nie tworzy pozornego
  login. Jeżeli uzyskano refresh token, nieudany zapis próbuje go revoke w
  pozostałym budżecie czasu, bez zatrzymywania rollback i bez logowania tokena.
- Cookie `__Host-torii-session`: Secure/HttpOnly/SameSite=Lax/Path=/, bez Domain,
  Max-Age nie dłuższe niż 8 h. DB: absolute 8 h, idle 30 min, bez odnowienia
  absolute expiry. Cookie `__Host-torii-login` ma te same atrybuty i 5 min.
  Callback usuwa login cookie także po błędzie; nigdy nie umieszcza JWT w cookie.
- Uwierzytelnienie sesji sprawdza aktywnego principal i oba terminy z DB;
  warunkowy UPDATE last_seen nie tworzy brakującego rekordu, nie ożywia sesji po
  logout/idle expiry. Odczyt i touch są spójne, po oczekiwaniu na lock termin
  sprawdzany ponownie. Idle liczymy od poprawnego uwierzytelnienia, również gdy
  późniejsza operacja domenowa dostanie 403/404. Wyścig logout/touch ma test DB.
- Logout: zweryfikowana cookie/Origin/CSRF, lokalny DELETE i commit najpierw,
  potem ograniczony best-effort POST revocation refresh token. Nie używamy
  legacy Keycloak logout z hasłem/refresh w URL. Revocation delegacji nie jest
  obietnicą zakończenia całej sesji SSO ani natychmiastowego revoke istniejących
  samowystarczalnych access JWT. [Keycloak opisuje revocation osobno od logout](https://www.keycloak.org/securing-apps/oidc-layers).
- Bounded cleanup usuwa tylko wygasłe flows/sessions w porcjach do 100 rekordów,
  bez danych biznesowych; expiry działa niezależnie od sprzątania. Nie dodajemy
  automatycznego kasowania audytu/grantów/receiptów w tym przyroście. Restart
  API z tym samym kluczem zachowuje poprawne sesje; restore wymaga ich usunięcia
  zgodnie z SPEC-0002, nie deklarujemy jeszcze wykonanego restore drill.

## B2b — fasada HTTP i integracja użytkownika

1. Udostępnić tylko login/callback, GET session, POST logout oraz siedem operacji
   ProjectService B1. Nie wystawiać niezaimplementowanych tras obiektów/wersji.
   Actor zawsze ze zweryfikowanego kontekstu, request ID z middleware; brak
   `X-User`, default principal, mock mode w runtime lub actor w payloadzie.
2. Protected API rozstrzyga credentials przed użyciem: cookie+Bearer 400
   `ambiguous_credentials`, brak/błędne 401. Odrzuca powtórzone Authorization,
   powtórzone wartości cookie sesji, Origin/CSRF i nagłówki mutacji; nie pozwala,
   aby wybór pierwszej/ostatniej wartości zmienił tożsamość. Szczegółowe kody
   składni nagłówków i parametry query wymagają tabeli przykładów przed kodem.
3. Dla cookie mutations Origin musi być pojedynczy i równy skonfigurowanemu
   public origin, nie `null`/brak; CSRF z sesji porównany bez wycieku czasowego.
   Bearer-only nie potrzebuje CSRF. No-store, nowe X-Request-ID i bezpieczne
   Problem Details obowiązują na każdej ścieżce. Brak CORS wildcard/credentials.
4. Kolejność: ograniczenia transportu -> credentials -> CSRF dla cookie write
   -> widoczność/prawo -> walidacja treści -> B1 z ponowną autoryzacją w swojej
   transakcji. FastAPI/Pydantic nie może zwrócić 422 z modelu body przed odmową
   dla niewidocznego projektu. Proponowana integracja: jawny application preflight
   prawa przed strict decode, potem istniejący serwis ponawia kontrolę wewnątrz
   transakcji/po locku; preflight nie jest cache ani gwarancją utrzymania praw.
5. Session DTO spełnia OpenAPI: principal_id/display_name/aktualny
   can_create_project, CSRF tylko dla cookie (null dla Bearer). Grant czytany
   z DB, nie claimów. Fasada zachowuje B1 ETag/Location/status/receipt; nie
   wytwarza nowego Idempotency-Key przy retry. Brak sekretów w DTO i wyjątkach.
6. Callback: 303 na `/projects` albo ustalony `/login?error=oidc`, bez odbijania
   provider error_description, code/state i redirect input. Query do 8 KiB;
   code/state/error według OpenAPI, proponowane limity iss 2048/session_state 512.
   Niepoprawny callback zawsze usuwa login cookie; duplikaty/unknown extensions
   nie są logowane ani przekazywane do token endpoint. Start login nie przyjmuje
   return_to/redirect_uri od klienta. Obie trasy bez body; brak GET logout.
7. DB/HTTP mają deadline poniżej 15 s. Anulowanie coroutine nie jest dowodem
   zatrzymania sync DB thread ani rollback; test obejmuje commit po utracie
   odpowiedzi i bezpieczny replay. Żadna odpowiedź sukcesu przed commit.
8. B2b doprecyzuje przed kodem limiter 120/min/principal, burst 30 i login
   10/min/IP z SPEC-0002, trust proxy i Retry-After; nie uzna samego limitu JWKS
   za wykonanie tego wymagania. Readiness zachowuje jawny DB/schema kontrakt;
   awaria IdP może blokować login, nie ma wyłączać już ważnych lokalnych sesji.

## Bootstrap, migracje i ślad bezpieczeństwa

- B2a powinien użyć obecnych tabel i grantów. Jeśli review wykaże konieczność
  nowej kolumny/indeksu, najpierw zmiana modelu i migracja 0002 z upgrade fixture;
  nie przepisywać uruchomionej 0001. Nie rozszerzać runtime o grant/admin/DDL.
- B2b potrzebuje powtarzalnego, jawnego bootstrapu nowej syntetycznej organizacji
  i `project.create` dla wskazanego verified issuer/sub. Harness oddziela seeding
  uprzywilejowany od runtime; fixture IdP alice/bob/eve same w sobie nic nie
  przyznają. Procedura operatorska i zabezpieczenie przed uruchomieniem na innej
  instancji muszą przejść review przed kodem, bez ręcznej edycji działającej DB.
- B2 nie dodaje endpointu mintującego SDK tokens. Surowy klient testowy otrzymuje
  token przez chroniony testowy Code+PKCE exchange, nie password grant ani
  wyprowadzenie browser tokena do localStorage. Docelowy SDK login osobno.
- Audyt mutacji projektu pozostaje atomowy z B1. Istniejąca tabela wymaga
  project_id i outcome=allowed: nie wpisywać tam fikcyjnych projektów/logowań.
  Auth telemetry ma skończone event/reason codes, request ID i ewentualnie
  zweryfikowane wewnętrzne principal ID; bez email/sub/URL/query/code/cookie/JWT,
  ciphertext, body i wyjątków bibliotek. Nie jest trwałym enterprise security
  auditem; ewentualna nowa tabela/eksport wymaga osobnego modelu i polityki awarii.
- Przy rollback wyłączyć nowe trasy/zastosować zgodny obraz, zachować projekty
  i audyt. Sekret szyfrujący sesje nie trafia do backupu razem z jawną bazą.
  Wycofanie nie obniża auth ani nie wprowadza bypass dla starego UI.

## Kryteria i plan dowodów — wszystkie planowane

| ID / powiązanie AC | Dowód wymagany |
|---|---|
| B2-AC01 / AC-10/14 | Offline testy JWT: issuer/aud/exp/nbf/iat/skew, brak required claims, alg/kid/token-kind confusion, nonce/at_hash, duplikaty JSON, złe typy i limity. Fałszywy token nie tworzy principal/sesji. |
| B2-AC02 / AC-14 | Fake HTTP: discovery/endpoint SSRF, redirect, proxy env, body deadline/limit, JWKS TTL/removal/rotation/unknown-kid storm/single-flight i outage. Mock nie zalicza realnego OIDC. |
| B2-AC03 / AC-10/14 | Real PG: flow TTL, obcy/brak browser binding, dwa callback zużywają raz, commit consume przed exchange, exchange/commit fault. DB nie zawiera jawnych state/verifier/cookie/CSRF/refresh. |
| B2-AC04 / AC-09/10/12 | Real PG: równoczesny provisioning ten sam issuer/sub, brak grantów, inactive nie wraca, display normalization, idle/absolute/session rotation, logout/touch race i sesja czytelna przez nową instancję adaptera. |
| B2-AC05 / AC-01/02/03/06/07/09/10 | HTTP + real PG: macierz ról, 403/404 i kolejność błędów bez wycieku, bieżące revoke/deactivate, idempotency/ETag/Location zgodne z B1 i OpenAPI, malformed/duplicate headers, CSRF/Origin/ambiguous credentials. |
| B2-AC06 / AC-13/14 | Real Keycloak + przeglądarki A/B/E + surowy API: login/replay/session/logout, brak uprawnień po pierwszym login, jawny grant umożliwia create; E nie widzi P1. ID token nie działa jako Bearer. IdP outage nie cofa logout ani nie tworzy nowej sesji. |
| B2-AC07 / AC-12, SPEC-0002 AC-05/06 | Restart API/DB zachowuje właściwy stan i TTL; marker sekretu nie trafia do logów/bundle/raportów. Pełny restore pozostaje osobną obowiązkową bramką, nie PASS z restartu. |

Testy najpierw, następnie małe implementacje i niezależne review B2a/B2b.
Każdy raport: commit, rewizja spec, toolchain/digesty, polecenie, liczby PASS/
SKIP, zasoby i cleanup, niespełnione AC. Ruff/mypy/unit/contract/regresje B1
obowiązują przy obu przyrostach. E2E nie używa tylko mocków ani starej instalacji.
Nowy efemeryczny stack, dokładny run ID/etykiety/porty, syntetyczne konta i
sekrety w ignorowanych plikach; guardy libpq/Docker analogiczne do B1.
Przeglądarka ufa CA tylko w profilu testowym; nie zmienia globalnego trust store.
HAR/trace/screenshots auth mogą zawierać sekrety: wyłączyć ich utrwalanie na
etapach login/exchange i przeskanować pozostałe dowody przed zapisaniem.

Zapis tej propozycji nie uruchamia usług/testów ani nie zatwierdza żadnej z
powyższych decyzji. Nadal wymagane do ukończenia SP-01 są pozostałe bramki
retencji/DR/obciążenia/metryk/skanów i jawny raport; nie oznaczać sprintu
ukończonym na podstawie samego B2a albo działającego logowania.
