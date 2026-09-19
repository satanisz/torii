# SP01-02 — dowody infrastruktury

2026-09-19. Status: scaffolding + częściowa integracja, **nie pełny odbiór AC**.
Polecenia wykonano w working tree po `a7b19a5`; commit integracyjny dopisze root.
Docker Desktop 28.5.2, Compose 2.40.3, Linux amd64, Windows PowerShell.

## Wykonane

- Odczyt zasobów: 24 CPU, 31.06 GiB Docker, szacunkowo 18.5 GiB headroom
  po rezerwie 1 GiB. Istniejące Torii/Airflow pozostały uruchomione.
- `test-tools.ps1`: 15 PASS (identyfikatory, wyjście poza katalog, format
  sekretu, konflikt portu, procesowe nadpisanie Compose env). Bez tworzenia usług.
- Provision syntetycznej instancji `test-abcdef012345`, port 19443, nowe
  losowe sekrety i użytkownicy. ACL katalogu ograniczone do właściciela.
- `git check-ignore` realm/client secret: PASS; config nie wypisuje sekretów.
- `platform.ps1 ... -Action check`: Compose syntax/interpolation PASS.
- `platform.ps1 ... -Action preflight`: PASS, brak konfliktu portu.
- `test-compose.ps1`: 26 PASS (izolacja nazw, loopback, brak obcych wolumenów,
  przypięte obrazy, prywatne sieci, ograniczenie ścieżek sekretów i oddzielenie DSN).
- Wszystkie 6 obrazów: digest z registry inspect (patrz lock), Caddy pobrany.
- Build gateway: PASS. Config Caddy i static web walidowany w izolowanym
  kontenerze `--network none --read-only --cap-drop ALL`, UID 10001: PASS.
  Wykryto file capability upstream Caddy; usunięto w pochodnym obrazie,
  aby działał non-root na wysokim porcie bez dodawania capability.
- Po zgodzie integratora: testowy PostgreSQL 17.11 i Keycloak 26.7.4
  uruchomione na nowych wolumenach/sieciach. Bootstrap i health PASS.
  Role aplikacyjne nie są superuser/createdb/createrole. Runtime ma CONNECT
  do platformy, nie do bazy IdP; nie ma CREATE public schema.
- `test-identity.ps1`: 10 PASS na prawdziwym IdP, canonical issuer i 4 endpointy
  także przy obcym Host/Forwarded. Poprawiono KC_HOSTNAME o `/identity`, bo
  sam relative-path nie zachowywał ścieżki w pełnym publicznym hostname URL.
- Build API i migracja `0001_projects` PASS; runtime API healthy.
  Migrator używa `--no-sync`, ponieważ próba ponownej instalacji pakietu
  w runtime prawidłowo nie miała dostępu do PyPI. Zależności instalowane
  wyłącznie podczas frozen builda. API nie otrzymało sekretu migratora.
- Runtime SQL audit_events: SELECT/INSERT dozwolone, UPDATE/DELETE zabronione;
  CREATE public schema zabronione. Migracja potwierdzona alembic_version.
- Poprawiono tmpfs jako cytowany scalar YAML; dodano kontrolę regresyjną
  rozdzielenia opcji zawierających przecinek (Docker odrzucał błędny mount).
- Gateway A/B z tym samym Caddy/TLS: `test-gateway.ps1 -InternalNetwork`
  dał oczekiwany błąd połączenia hosta, Docker Ports `9443/tcp:[]`, mimo
  uruchomionego listenera i wystawionego certyfikatu localhost. Bridge ingress
  dał mapowanie `127.0.0.1:29444→9443`. Zmiana zaakceptowana przed kodem;
  tylko gateway korzysta z ingress, pozostałe sieci pozostają internal.
- `test-gateway.ps1 -Port 29444`: 3 real HTTPS denial/unavailable checks PASS,
  certyfikat zweryfikowany własnym CA (bez globalnego zaufania/skip verify).
  Obcy Host/port: 400; brak upstream: 503, Retry-After 3. Problem Details,
  no-store, własny UUIDv4 zgodny w body i header, obcy request ID nieprzyjęty.
- Syntetyczne code/state/Bearer/request-ID nie wystąpiły w error logs. Domyślny
  logger usuwa cały obiekt request, access logging gateway pozostaje wyłączony.
- Dalsze 3 gateway fixture checks PASS: niezmieniony status/body/request ID
  błędu 401 upstream, body 262144 bajty przepuszczone, 262145 → Problem Details
  413 z no-store i UUIDv4. To fixture proxy, nie dowód auth rzeczywistego API.
- Kontenery/sieć obu negatywnych prób gateway usunięte po sprawdzeniu własności;
  dane platformy/legacy nietknięte. Pozostały wyłącznie publiczne CA w `.local`.
- Ruff check obu Python helperów PASS; hostowy helper Python 3.14, zaufany
  upstream fixture w przypiętym Python 3.12. API build/runtime używa Python 3.12.

## Brakujące dowody

- Pełny stos z gateway/UI jeszcze nieodebrany; login, UI E2E i cleanup
  istniejącej testowej bazy niewykonane. DB/IdP/API pozostają healthy do dalszej
  integracji przez root; gateway powyżej był odrębnym efemerycznym testem.
- Skany obrazów/SBOM/licencji, backup/restore, negatywne tokeny issuer/audience,
  CSRF, sesje oraz pełny frontend wymagają dalszej integracji i nie są PASS.
- Logi mają limit rozmiaru, nie retencję czasową; monitoring/retencja są otwarte.
- Techniczny przegląd i testy nie są ludzkim odbiorem enterprise/production.

Nie zmieniono root `.env`, starych wolumenów ani usług. Kontenery walidatora
Caddy były efemeryczne `--rm`, bez sieci i bez dostępu do danych użytkownika.
