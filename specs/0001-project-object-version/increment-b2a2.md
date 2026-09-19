# SPEC-0001 B2a2 — offline JWT i publiczny zestaw kluczy

Status: Accepted (delegated), 2026-09-19. Wydzielony z [B2](increment-b2.md).
Agent contract_review przejrzał przed kodem; przyjęto po uściśleniu clock,
liczenia węzłów/głębokości, display_name i niezaufanego kid hint. Podstawa:
mandat użytkownika, nie akceptacja własna autora ani audyt ludzki.
B2a1 pozostaje przyjętą warstwą persistence.
Ten przyrost realizuje część B2-AC01 (SPEC-0001 AC-10/14), nie transport OIDC,
cache/rotation online, callback, nowe HTTP routes, DB ani login E2E.
Transport discovery/JWKS/code exchange będzie osobnym B2a3 przed B2b.

## Profil i granica zaufania

Wybieramy dla lokalnego Keycloak osobne, wzajemnie wykluczające się reguły
access i ID token. Nie jest to uniwersalny profil wszystkich dostawców.
Przegląd exact-tag26.7.4 oraz metadanych lokalnego przypiętego obrazu przez
agenta infra potwierdza profil źródłowy D02: domyślne RS256/JOSE JWT,
payload Bearer vs ID, ID aud/azp klienta, iat/nonce, at_hash w Code+openid.
Źródła: [DefaultTokenManager](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/jose/jws/DefaultTokenManager.java#L199),
[TokenUtil](https://github.com/keycloak/keycloak/blob/26.7.4/core/src/main/java/org/keycloak/util/TokenUtil.java#L49),
[TokenManager](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/TokenManager.java#L1314),
[Code response](https://github.com/keycloak/keycloak/blob/26.7.4/services/src/main/java/org/keycloak/protocol/oidc/grants/OAuth2GrantTypeBase.java#L147).
Repo mapper dodaje torii-api do access audience, nie usuwa innych audiences.
To dowód kodu/konfiguracji, NIE obserwacja tokenu ani runtime realm; zgodność
rzeczywistego Code+PKCE trzeba później sprawdzić w izolowanym E2E.
Przyjęto D02 dla tego lokalnego profilu źródłowego i wyłącznie część D06
poniżej, bez nowych pól wire/config. Realny profil nadal wymaga testu E2E.

Zaufany issuer/client_id/audience pochodzą z ustawień serwera. Klucze muszą
pochodzić z zaufanej konfiguracji lub przyszłego ograniczonego transportu;
samo sparsowanie JWKS nie dowodzi ich pochodzenia. Żadnego pobierania URL
z nagłówka JWT, przyjmowania JWK z tokena ani klucza z requestu.
Verifier zwraca Identity dopiero po kompletnym podpisie i semantyce. Nie nadaje
grantów ani nie zapisuje principal; aplikacja później wywoła B2a1/B1.

## Publiczne API modułów

- `security/oidc_keys.py`: `decode_object(data: bytes, *, limit: int) ->
  dict[str, object]` (wewnętrzny strict JSON, bezpieczny ValueError),
  `decode_segment(value: str, *, limit: int) -> bytes` (kanoniczne base64url,
  bezpieczny ValueError), `valid_kid(value: object) -> bool`.
- `SigningKeys.from_jwks(data: bytes, *, issuer: str) -> SigningKeys`:
  niemutowalny publiczny zestaw związany z issuer; `.issuer`,
  `.key_for(kid: str) -> RSAPublicKey | None`. Repr nie pokazuje surowego JWKS.
- `security/oidc_tokens.py`: `token_key_id(token: str) -> str`, WYŁĄCZNIE
  niezaufany hint do przyszłego ograniczonego lookup, nigdy identity.
  Sprawdza compact/canonical/limity, ścisły JSON i zamknięty header; nie
  sprawdza podpisu ani semantyki claims i nie może służyć do auth.
- `TokenVerifier(issuer: str, client_id: str, audience: str, *,
  clock: Callable[[], float] = time.time)`; zegar jest testowym/server-owned
  dependency, nigdy wartością requestu. `.verify_access(token, keys) -> Identity`;
  `.verify_login(id_token, access_token, nonce_hash, keys) -> Identity`.
  Login wymaga obu poprawnych tokenów i związania z zużytym flow B2a1.
  Brak publicznego decode-without-signature ani pominięcia nonce.

## Parsowanie i klucze

1. JWT to exact str ASCII, max16384 bajtów, dokładnie3 niepuste segmenty JWS
   compact; wyłącznie canonical base64url bez padding i niezerowych pad bits.
   Header max2048 decoded bytes, payload max12288, signature max512.
   Brak JWE/detached payload, kompresji i nieobsługiwanych rozszerzeń.
2. JSON UTF-8 object, bez BOM, duplicate keys na dowolnej głębokości, NaN/Inf,
   overflow do Inf, surrogate codepoints; max depth32 (root object depth1),
   max2048 węzłów łącznie (każdy kontener, skalarna wartość i klucz liczony raz;
   głębokość rośnie wyłącznie przy kontenerze). Liczby z JSON mogą
   być finite int/float; wymagane NumericDate mają osobną ścisłą regułę niżej.
   Każdy literal liczbowy ma max128 znaków (minus/kropka/e/E/znak wykładnika
   wliczone), sprawdzone w parse_int/parse_float PRZED konwersją. To dodatkowy
   limit lokalnego profilu, nie zależność od globalnego Python int digit limit.
   Refinement przeszedł niezależny review contract_review przed zmianą parsera;
   testy128/129 dla int/minus/scientific float i krótki overflow1e309 wymagane.
   Parser nigdy nie zwraca błędu z treścią danych/chained context.
3. Header ma dokładnie `alg`, `kid`, `typ`; alg=`RS256`, typ=`JWT`.
   kid to1..128 printable ASCII0x21..0x7e, dokładne porównanie. `crit`, `jku`,
   `jwk`, `x5u`, `x5c`, `b64` i wszystkie inne header fields są niedopuszczone.
4. JWKS max65536 bytes, root dokładnie `{keys:[...]}`,1..32 pozycji.
   Każda pozycja object z poprawnym kid i niepustym string kty; powtórzony kid
   w całym zestawie ->503, także między sig i enc. Prywatne/symetryczne pola
   `d,p,q,dp,dq,qi,oth,k` w dowolnym JWK ->503, nie wolno ich ignorować.
   Obecne use/alg muszą być niepustymi stringami przed filtrowaniem.
5. Wybieramy RSA z use nieobecnym lub `sig`, alg nieobecnym lub `RS256`;
   pozostałe rodzaje/przeznaczenia/algorytmy pomijamy, nie używamy jako fallback.
   Dla wybranego klucza key_ops nieobecne lub dokładnie `["verify"]`.
   n/e wymagane canonical base64urlUInt bez wiodącego zera, modulus nieparzysty
   2048..4096 bits, exponent65537. To ograniczenie lokalnego profilu.
   Klucz konstruuje biblioteka cryptography. x5c/x5t/inne metadane ignorowane
   w ramach limitów JSON, nigdy jako alternatywne źródło klucza ani URL.
   Cały nowy zestaw musi się poprawnie parsować i mieć co najmniej1 wybrany klucz.
6. Zestaw jest niemutowalny; nowa instancja reprezentuje pełne zastąpienie,
   nie append. Nie wprowadzamy TTL ani cache tutaj. Weryfikator wymaga issuer
   zestawu równym konfiguracji. Nieznany kid w przekazanym zestawie ->401.

## Podpis i claims

Podpis sprawdza przypięty PyJWT `PyJWS` z serwerowym algorithms=[RS256],
verify_signature=True i publicznym RSA z przefiltrowanego zestawu. Nie piszemy
własnego RSA/JWS. Claim parsing jest ścisły przed podpisem, ale claimów nie
używamy do Identity ani autoryzacji przed sukcesem kryptografii.

- Wspólne required: iss,sub,aud,exp,typ. iss dokładnie configured issuer;
  sub spełnia Identity B2a1 (1..255 ASCII0x21..0x7e, case-sensitive).
  NumericDate exp i obecne iat/nbf to exact int (nie bool, float ani string),
  zakres0..2^53−1. Zegar exact int/float, finite w zakresie0..2^53−1,
  walidowany po podpisie; zły zegar lub zwykły wyjątek clock503 (bez chaining).
  Login pobiera jeden wspólny now po obu weryfikacjach podpisu i do obu
  zestawów claims stosuje ten sam czas.
  Ważność: exp > now−30; nbf <= now+30; iat <= now+30. Jeśli iat/nbf obecne,
  wymagamy iat < exp i nbf < exp. Brak dodatkowego max-age iat w tym przyroście.
- aud to niepusty string lub lista1..16 unikalnych niepustych stringów,
  każdy do256 znaków bez control/surrogates. ID: dokładnie client_id (string
  lub jednoelementowa lista); dodatkowe audiences odrzucone. Access: zawiera
  configured audience; inne poprawne audiences dozwolone (np. account).
- Access: payload typ=`Bearer`. iat opcjonalne. azp jeśli obecne ma być
  dokładnie client_id; brak azp dozwolony w tym lokalnym profilu. Brak wnioskowania
  tożsamości/praw z email, realm_access, roles, groups ani scope.
  Nazwa z access name/preferred_username normalizowana regułami B2a1.
- ID w login: payload typ=`ID`, iat wymagane; azp jeśli obecne =client_id.
  nonce wymagane i canonical credential43 B2a1; SHA256 ASCII nonce równe
  canonical lowerhex64 nonce_hash z flow, compare_digest. Zły hash input503,
  zły/missing token nonce401. Access i ID muszą mieć identyczne issuer/sub.
  Nazwę Identity wybieramy z ID (name/preferred_username) regułami B2a1.
- at_hash jeśli występuje w ID: exact canonical base64url dla16bytes, równe
  lewej połowie SHA256 ASCII całego otrzymanego access token (RS256).
  Brak at_hash dozwolony dla Code flow; obecny niepoprawny odrzuca login.
  Metoda login dodatkowo sprawdza access token, nawet jeśli at_hash brak.
- Nazwy innych claims mogą istnieć w ramach limitów parsera; ignorujemy je.
  Bez zwracania raw claims, tokenów, subject/nazwy w repr lub błędzie.
  Config: issuer exact str1..2048 bez NUL/surrogates, client/audience poprawne
 1..256 non-control string, różne od siebie; URL waliduje dotychczasowe Settings.

## Błędy, testy i odbiór

Credential/format/header/signature/claims/unknown kid -> DomainError401
`unauthorized`, bez różnic i bez exception cause/context/payload. Zły config,
JWKS, keyset issuer lub clock oraz operacyjne błędy kryptografii
(TypeError/ValueError/OSError) -> DomainError503 `identity_unavailable`.
InvalidTokenError z PyJWT to401, InvalidKeyError/pozostałe PyJWTError to503.
Nie logujemy raw wyjątków, tokenów, kluczy/JWKS ani nazw/subject.

AC lokalnego B2a2 (wszystkie wymagają testów):

1. Prawdziwie podpisane syntetyczne RSA JWT: access, ID+access z nonce/at_hash;
   invalid signature/tampering/none/HS256/key confusion/ID-as-Bearer odmawiają.
2. Granice parsera, duplicate keys, Unicode, depth/nodes/sizes/pad bits; reguły
   JWKS, małe/duże/private/enc/key_ops keys, duplicate kid i zastąpienie zestawu.
3. Required/types/time/skew/audience/azp/issuer/sub i nonce/at_hash bindings;
   dokładne granice, ten sam kid z innym kluczem nie omija podpisu.
4. Fault injection kryptografii/clock: bezpieczne błędy, brak secret markerów
   w repr/traceback/exception chain, brak DB/network imports i nowych tras.
5. B1/B2a1 regresje, Ruff/strict mypy, kontrakty i końcowy niezależny review.
   Testy używają ephemeral kluczy generowanych w pamięci, nie utrwalają private
   PEM/JWT/JWKS fixture ani nie używają firmowego/running IdP. Syntetyczny podpis
   jest realną kryptografią, ale nie dowodzi discovery, loginu Keycloak czy E2E.

Źródła kierunku: [RFC8725 §3.8–3.12](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.8),
[OIDC Core §3.1.3.7–8](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation),
[PyJWT2.14 API](https://pyjwt.readthedocs.io/en/stable/api.html#jwt.api_jws.PyJWS).
Limity i węższy lokalny profil są decyzjami Torii, nie twierdzeniem o wymogach
wszystkich implementacji tych standardów.
