# SP01-02 — plan implementacji izolowanego środowiska

2026-09-19. SPEC-0002 AC-01/02/03/07/08. Zapis przed kodem.
Przegląd techniczny: integrator `/root` zaakceptował topologię i poniższy
kontrakt konfiguracji w komunikacji agentów. Podstawa: mandat użytkownika.

## Zakres i kolejność

1. Przypiąć digesty PostgreSQL 17, Keycloak 26, Caddy 2, Python 3.12,
   Node 24 i uv; sprawdzić ich dostępność oraz zasoby przed pobraniem.
2. Przygotować generowanie sekretów do ignorowanego `.local/<instance>`;
   brak haseł domyślnych i nadpisywania istniejącej konfiguracji.
3. Nowy projekt Compose, osobna prywatna sieć i wolumeny: baza, IdP,
   migrator, API, statyczny web oraz TLS gateway na loopback 9443.
4. Bootstrap bazy: `torii_platform`, role `torii_migrator`, `torii_runtime`,
   `torii_identity` i oddzielna baza `torii_identity`. Runtime bez DDL;
   specyficzne uprawnienia tabel nadają migracje API, nie ogólny GRANT ALL.
5. Local IdP z PKCE S256, dokładnym redirect URI, publicznym issuer i
   kontrolowanym prywatnym backchannel. Sekrety przekazywane plikami.
6. Bezpieczny lifecycle PowerShell: jawne Compose/env/project, preflight,
   build/start po koordynacji, stop zachowujący dane i opcjonalny cleanup
   wyłącznie sprawdzonego testowego run ID. Bez globalnego Docker cleanup.
7. Walidacja statyczna/Compose, testy narzędzi, później integracja z realnym
   API. Nie zaliczamy runtime AC z samego parsowania YAML.

## Kontrakt aplikacyjny

- API: `apps/api`, `uv.lock`, `torii_api.app:create_app`, port 8000,
  `/health/live`, `/health/ready`; migracja `uv run --frozen alembic upgrade head`.
- Web: `apps/web`, `npm ci`, `npm run build`, `dist`; jeden publiczny origin.
- API otrzymuje `TORII_DATABASE_URL_FILE`, `TORII_SESSION_KEY_FILE`,
  `TORII_CURSOR_KEY_FILE`, `TORII_OIDC_CLIENT_SECRET_FILE`.
- `TORII_PUBLIC_URL=https://localhost:<port>`,
  `TORII_OIDC_ISSUER=https://localhost:<port>/identity/realms/torii-dev`,
  `TORII_OIDC_BACKCHANNEL_URL=http://identity:8080/identity/realms/torii-dev`,
  `TORII_OIDC_CLIENT_ID=torii-web`, `TORII_OIDC_AUDIENCE=torii-api`.
- Baza runtime i migrator mają różne DSN; API nie otrzymuje sekretu migratora.

## Plan testów i granice

Compose config musi odrzucać brak provisioningu; nazwy zasobów nie mogą
odwoływać się do istniejącego Torii/FrameML/Airflow. Testy narzędzi odrzucają
błędny run ID/ścieżkę oraz konflikt portu. Cleanup wymaga własnych etykiet.
Wygenerowane sekrety muszą być ignorowane przez Git i nie trafiać do config
stdout/logów. Caddy akceptuje wyłącznie localhost i usuwa nagłówki klienta
udające proxy. Brak systemowego instalowania CA.

Uruchomienie stosu wymaga koordynacji z integratorem, gotowej migracji i API.
Kontenery testowe mogą być usuwane tylko po sprawdzeniu własności; dev stop
nigdy nie kasuje wolumenów. Backup/restore aplikacji, skany oraz E2E wymagają
kolejnych dowodów i nie są tu domyślnie PASS.

## Uzupełnienie przed implementacją błędów gateway

Przegląd techniczny `/root/contract_review` wskazał możliwy wyciek query callback
w error log oraz niezgodny format błędów proxy. Integrator `/root` zaakceptował
następującą korektę w ramach SPEC-0002 AC-05/07:

- Filtr domyślnego JSON log usuwa cały obiekt request (URL, query, nagłówki).
- Własne błędy HTTP gateway: Problem Details, no-store i UUIDv4 request ID;
  `invalid_host` 400, `payload_too_large` 413, `service_unavailable` 503.
- Błędy połączenia upstream 502/504 mapujemy na 503 z Retry-After 3.
  Odpowiedzi i request ID pochodzące z API przechodzą niezmienione.
- Test izolowanego gateway z niedostępnym syntetycznym upstream sprawdza
  marker sekretu w query, bez dostępu do legacy, walidując TLS własnym CA.
- Migrator używa zbudowanego frozen venv (`uv run --frozen --no-sync`),
  aby nie instalować ani nie rozwiązywać pakietów w prywatnej sieci runtime.

## Korekta po próbie reachability — przed kodem

Integrator zaakceptował dedykowaną sieć `ingress` (bridge, nie internal),
wyłącznie dla gateway. App/data nadal internal, port nadal tylko loopback.
Cel: potwierdzić próbą A/B publikację portu Docker Desktop przy identycznym
Caddy/TLS. Nie maskujemy błędu certyfikatu przez wyłączenie weryfikacji.
Jawne ograniczenie dev: gateway otrzymuje domyślny Docker egress; nie jest to
kwalifikacja firmowego outbound firewall. Kontrole topologii mają wykluczać
dołączenie DB/IdP/API/web do ingress i publikowanie ich portów.
