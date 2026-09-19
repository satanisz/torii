# SPEC-0001 B2a3 — ograniczony transport metadanych i cache OIDC

Status: Accepted (delegated), 2026-09-19. Niezależny review agenta
contract_review przed kodem; przyjęto po doprecyzowaniu odrzucania provider
cookies, aktywnego timeout oczekiwania na lock i parsera Content-Type.
Podstawa: mandat użytkownika; nie audyt ludzki ani odbiór enterprise.
Podzbiór B2-D06 / B2-AC02 / SPEC-0001 AC-14. Kontynuacja B2a1/B2a2.
Granica: tylko GET discovery/JWKS i cache. Code exchange/revocation zostają
wydzielone do B2a4 (własny kontrakt przed kodem); bez nowych tras, DB, cookies,
provisioningu, zmian Settings/env, migracji, deploy ani twierdzenia o login E2E.

## Kontrakt i granica zaufania

`security/oidc_transport.py`:

- `RealmEndpoints(issuer: str, backchannel: str)` niemutowalne, bez URL w repr.
  Parametry tylko z zaufanej konfiguracji. Oba URL <=2048 ASCII, kanoniczne:
  lowercase scheme/hostname DNS (etykiety 1..63 alnum/hyphen, nie hyphen na
  brzegach; localhost dozwolony), opcjonalny port 1..65535 bez leading zero,
  dokładna ścieżka `/identity/realms/[A-Za-z0-9_-]{1,128}`. HTTPS issuer;
  backchannel HTTPS lub dokładnie host `identity` przez HTTP. Ścieżki równe.
  Bez userinfo, query (także pustego `?`), fragment, percent encoding, backslash,
  whitespace, Unicode, dot-segments, trailing slash. IPv6 i Unicode IDN poza tym
  profilem; numeryczny host IPv4 i ASCII xn-- syntaktycznie dozwolone, bez
  dekodowania/normalizacji. Błędne ustawienie: bezpieczne503 identity_unavailable.
- Właściwości `discovery_url`, `jwks_url` są skonstruowane wyłącznie z
  backchannel: `/.well-known/openid-configuration`, `/protocol/openid-connect/certs`.
  `validate_discovery(data: bytes) -> None` używa B2a2 decode_object 64KiB;
  issuer dokładnie publiczny. Wymaga authorization_endpoint dokładnie publiczny
  `/protocol/openid-connect/auth`; token_endpoint, jwks_uri, revocation_endpoint
  dokładnie publiczny LUB backchannel z końcówkami token/certs/revoke. Pozostałe
  bounded pola ignoruje, nigdy nie pobiera URL z metadanych. Nie dowodzi zgodności
  pozostałych capabilities/algorytmów ani działania token endpoint.
- `OidcMetadataTransport(endpoints, *, transport: httpx.AsyncBaseTransport | None
  = None)` tworzy własny dedykowany AsyncClient. Opcjonalny transport wyłącznie
  seam in-process testów, nigdy env/request config. Bez auth, cookies użytkownika,
  ani przechowywania/wysyłania cookies dostawcy: Set-Cookie ignorowane przez
  odrzucającą politykę jar (nie chwilowe clear po response). Test wielu różnych
  Set-Cookie i równoległych GET: zero Cookie na wire i pusty trwały jar.
  redirectów, proxy/CA z env (`trust_env=False`); HTTPS verify=True. Limits:
  max_connections=4, max_keepalive_connections=2; timeout connect/pool2s,
  read/write5s. Brak retry. Żadnego argumentu URL w publicznych metodach.
- `async discovery(*, deadline: float) -> None`, `async jwks(*, deadline: float)
  -> SigningKeys`, `async aclose() -> None`. Deadline jest absolutnym czasem
  `asyncio.get_running_loop().time()` z jednego loopa. Każda operacja ma dodatkowo
  max5s obejmujące oczekiwanie na pool, headers, body i parsowanie; kontrola czasu
  przed i po parsowaniu. Deadline finite exact int/float (nie bool), w przyszłości;
  dodatkowo zakres0..2^53−1 przed konwersją; wyczerpany/błędny budżet odmawia
  przed I/O. Nie tworzy własnego budżetu callback. aclose jest idempotentne;
  awaria close nie zamienia zewnętrznego CancelledError w odpowiedź503.
- GET tylko status200. No-follow 3xx/304/4xx/5xx ->503. Content-Type dokładnie
  application/json lub application/jwk-set+json (parametry charset tolerowane).
  Media type case-insensitive, opcjonalnie jeden parametr charset=utf-8
  (case-insensitive, wartość może być w double quotes), whitespace wokół separatorów
  dozwolony; pozostałe parametry i powtórzony charset odrzucane.
  Pojedynczy Content-Type; Content-Encoding nieobecny lub pojedyncze identity;
  Accept-Encoding: identity i odrzucenie kompresji PRZED dekodowaniem, aby limit
  nie działał dopiero po decompression bomb. Content-Length jeśli obecny:
  pojedyncze decimal ASCII <=65536, nieujemne, bez znaku/spacji. Odczyt streaming
  do65536 bajtów, nie opiera się na deklarowanym length. Limit dotyczy surowych
  i dekodowanych bajtów równocześnie, bo inne encodings są niedozwolone.
  Walidacja nagłówków dotyczy reprezentacji dostarczonej przez HTTPX: h11 może
  normalizować jednakowe Content-Length/spacje przed adapterem. Test fake nie
  dowodzi wykrywania identycznych duplikatów na wire; różne wartości odrzuca h11.
- Po sukcesie, odmowie, timeout i cancellation wykonywana jest ograniczona
  próba zamknięcia odpowiedzi/połączenia. Doprecyzowanie przyjęte przed kodem
  po osobnym review contract_review: pojedynczy cleanup attempt ma dodatkowo
  najwyżej1s cooperative timeout, bez retry ani detached task. Może wykroczyć
  do1s poza workdeadline powyżej; to nie hard realtime return deadline.
  Dotyczy również `keys_for`, którego timeout nie zatrzymuje synchronicznie
  cleanup zależności. Przyszły callback rezerwuje1s od końcowego wspólnego
  budżetu przed przekazaniem workdeadline (bez resetowania per zależność).
  `aclose` klienta także ma1s; po błędzie jest logicznie zamknięty i kolejne
  operacje nie wykonują I/O. Idempotencja nie dowodzi fizycznego zamknięcia.
  Close failure/timeout nie daje sukcesu, ale nie przesłania zewnętrznego
  CancelledError (także przy ponownym cancel). Nie obiecujemy udanego close przy
  awarii providera ani hard limit dla transportu tłumiącego cancellation.
  httpx i parser exceptions -> wyłącznie DomainError503 identity_unavailable
  bez cause/context zależności ani URL/body. Po niezależnej reprodukcji i review
  doprecyzowano granicę CPython3.12: runtime może ponownie dołączyć wcześniej
  obsłużony wyjątek CALLERA przy powrocie z await po asyncio timeout, nawet po
  jawnym wyczyszczeniu kontekstu. Dopuszczalny jest wyłącznie ten sam istniejący
  wyjątek callera, nigdy provider exception; raise from None zawsze wyłącza jego
  wyświetlanie w traceback. Marker nie może trafić do str/repr/formatted traceback.
  Nie rozpoznajemy cancellation po ambient exception i nie zmieniamy cudzego
  wyjątku; błąd close nadal503, nie sukces. Zewnętrzne CancelledError propagowane. Brak własnych
  logów, surowych danych w repr lub telemetry. Konfiguracja zaufanej sieci/DNS
  nadal odpowiedzialnością deployment; nie jest to uniwersalny SSRF proxy.

`security/oidc_cache.py`:

- `OidcKeyCache(transport: OidcMetadataTransport)` jedna instancja per issuer,
  proces i event loop; `async keys_for(kids: tuple[str, ...], *, deadline: float)
  -> SigningKeys`. Od1do2 kid, każdy valid_kid; duplikat dozwolony. Nie token ani
  claims. Błędne hints401 unauthorized przed I/O. Caller dopiero po otrzymaniu
  snapshotu wywołuje B2a2 TokenVerifier; sam key lookup nie uwierzytelnia.
- Stałe TTL discovery i JWKS300s od zakończenia skutecznej walidacji, zegar loop
  monotoniczny. Pamięć O(1) snapshotów, bez mapy negatywnych kid. Deadline i czas
  są sprawdzane również po oczekiwaniu na lock i przed zwrotem.
- Fast path: wszystkie kid obecne w niewygasłym zestawie -> zwróć snapshot,
  nawet gdy discovery wygasło/inna operacja odświeża. Nie przedłuża TTL.
- W innym przypadku lock single-flight; po wejściu ponownie sprawdź cache.
  Brak detached task. Jeden lider odświeża, pozostali korzystają z wyniku pod
  własnymi deadline. Oczekiwanie na lock ma aktywny asyncio timeout do deadline,
  nie tylko kontrolę czasu po zdobyciu. Anulowanie lidera zamyka jego I/O i zwalnia lock; nie znosi
  ograniczenia częstotliwości. Anulowanie waitera nie anuluje lidera.
- Każda próba refresh (cold, expiry, unknown-kid, sukces/awaria/cancel) rozpoczyna
  globalny dla instancji cooldown30s PRZED pierwszym await. Także zimny outage
  nie powoduje storm. W cooldown: jeśli świeży snapshot pochodzi z ostatniej
  udanej próby, brak kid ->401; po nieudanej/niezakończonej próbie albo przy
  braku/wygasłym snapshot ->503. Znany ważny klucz nadal działa. Nie dodajemy
  harmonogramu/backoff worker ani retry wewnętrznego.
- Refresh: jeśli brak ważnego discovery, pobierz i waliduj je, potem pobierz
  JWKS. Każda część max5s ale dzieli deadline callera (w przyszłym callback
  wspólny z exchange/DB). Nie pobieraj JWKS po błędnym discovery. Ważnego
  discovery nie trzeba pobierać przy każdej rotacji.
- Pełny poprawny zestaw atomowo zastępuje poprzedni. Nie merge; usunięty klucz
  odpada natychmiast dla kolejnych lookupów, również same-kid replacement.
  Już zwrócony snapshot jest niemutowalnym wynikiem konkretnego lookupu, nie
  obietnicą retroaktywnego unieważnienia weryfikacji w toku.
- Awaria/304/malformed JWKS nie zmienia ani nie przedłuża istniejącego snapshotu;
  tylko nadal ważne znane klucze mogą działać. Brak kid po poprawnym refresh401;
  brak klucza/świeżego cache przy awarii503. Wyjątki bez kontekstu zależności,
  zgodnie z granicą runtime opisaną wyżej;
  CancelledError nie zamienia się w odpowiedź auth. Cache nie zamyka współdzielonego
  transportu; właściciel aplikacji ma jawny lifecycle aclose (podłączenie później).

## AC / plan testów przed implementacją

| AC | Dowód |
|---|---|
| A3-01 | URL/config matrix, exact issuer/endpoints, złośliwe discovery/jku/redirect nigdy nie zmieniają celu; brak wire nowych URL |
| A3-02 | HTTPX stream fake: wszystkie statusy, timeout pool/connect/read/body, wspólny workdeadline, limit64KiB/chunki, compression, duplicate headers/JSON, cancellation/close, bezpieczne wyjątki; realclock hanging close po sukcesie/body timeout/cancel i lifecycle, limit cleanup1s z tolerancją schedulera |
| A3-03 | Cache cold/success/expiry/rotation/removal/same-kid/outage/304, nieprzedłużany TTL, świeży klucz podczas awarii, brak stale kluczy |
| A3-04 | Deterministyczne współbieżne storm/single-flight, failed/cancelled cooldown, deadline waitera i cancel leadera, bounded memory bez mapy kid |
| A3-05 | Integracja fake HTTP -> public RSA keys -> real B2a2 podpis; mutant odrzucony, bez DB, brak sekretów w błędach/repr; regresje B1/B2a1/B2a2/FE i niezależny review |

Testy z asyncio.run/zdarzeniami i kontrolowanym zegarem w seam testowym; żadnego
czekania300s. Timeout streaming też sprawdzony z realnym zegarem loop.
MockTransport nie dowodzi TLS/DNS/sieci ani Keycloak E2E. Prawdziwe TLS/IdP
pozostają B2b. Bez nowej biblioteki lub lockfile. Rollback: niepodłączone moduły
można wycofać bez zmian danych; brak bypass przy awarii IdP.

Źródła techniczne (zweryfikowane2026-09-19):
[HTTPX timeout](https://www.python-httpx.org/advanced/timeouts/) rozróżnia timeout
bezczynności od deadline całej operacji; [stream/lifecycle](https://www.python-httpx.org/async/)
oraz [trust_env](https://www.python-httpx.org/environment_variables/) uzasadniają
dedykowany klient. Dokładna konfiguracja Torii pochodzi z compose.dev.yaml.
Te źródła nie są dowodem runtime tego przyrostu.
