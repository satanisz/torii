# Izolowane środowisko platformy Torii

SPEC-0002, SP01-02. To nowy stos **dev/test**, nie migracja działającej demonstracji
i nie profil produkcyjny. Stan testów zapisano w [evidence.md](evidence.md).
Wymaga Docker Desktop Linux, Compose >=2.24 (named build contexts), PowerShell,
4 CPU i szacunkowo co najmniej 8 GiB wolnej pamięci dla nowego stosu.

## Granice

- Własne projekty `torii-platform-dev` / `torii-platform-test-<run-id>`,
  prywatne sieci i nowe wolumeny. Jedyny port hosta: loopback 9443 (lub testowy).
- Wyłącznie gateway ma dodatkowy bridge ingress potrzebny do publikacji portu
  w Docker Desktop; app/data pozostają internal. Gateway ma domyślny Docker
  egress — nie deklarujemy firmowego outbound firewall w profilu dev.
- Nie czytamy ani nie modyfikujemy root `.env`, legacy wolumenów, Airflow,
  danych użytkownika ani trust store systemu.
- PostgreSQL 17 ma oddzielną bazę Torii i IdP. API posiada tylko login
  `torii_runtime`; migracje `torii_migrator`; Keycloak `torii_identity`.
  Konto bootstrap `postgres` nie jest przekazywane aplikacji.
- Runtime nie ma DDL. Konkretne prawa do tabel nadaje migracja API — bootstrap
  nie daje blankietowego GRANT ALL. Tokeny IdP nie nadają grantów platformy.
- Sekrety losowe, pliki Docker secrets, `.local` ignorowane przez Git i
  ograniczone ACL hosta. Realm import zawiera syntetyczne hasła i secret klienta,
  dlatego cały katalog jest prywatny. Docker Desktop nie jest firmowym vaultem.
- API nie ma Docker socket ani workspace hosta. Dockerfile/Compose przekazują
  tylko źródła aplikacji, publiczny kontrakt i konfigurację gateway; nie root repo.
- HTTPS kończy się na gateway. Prywatny HTTP gateway→API/IdP jest wyłącznie
  lokalnym wyjątkiem dev. IdP issuer zawsze pozostaje publicznym HTTPS URL.
- Admin console/master realm IdP nie jest publikowany przez gateway. Admin
  password jest przeznaczony do kontrolowanego lokalnego zarządzania w kontenerze.

## Przygotowanie i walidacja

Uruchamiaj z root repo (nie używaj gołego `docker compose up`, bo root `.env`
wybiera demonstrację). Nigdy nie wklejaj zawartości secret files do czatu/logów.
Skrypt odrzuca procesowe `TORII_COMPOSE_PROJECT`, `TORII_INSTANCE`,
`TORII_HTTPS_PORT` i `TORII_LOCAL_DIR`, także puste. Docker Compose daje im
pierwszeństwo przed `--env-file`; usuń je z bieżącego procesu zamiast omijać guard.

```powershell
./deploy/platform/test-tools.ps1
./deploy/platform/provision.ps1 -Profile dev -FixtureUsers
./deploy/platform/platform.ps1 -Action check
./deploy/platform/platform.ps1 -Action preflight
```

Provision nie uruchamia usług, nie przyznaje dostępu do projektu i odmawia
nadpisania istniejącej instancji. Nie używaj regeneracji sekretów do naprawiania
istniejącej bazy: potrzebna jest jawna procedura rotacji. `-FixtureUsers` dodaje
alice/bob/eve, z losowymi hasłami w `.local/dev/secrets/user_<name>`; są to
wyłącznie syntetyczne tożsamości. Bez tego parametru realm nie tworzy użytkowników.
Globalny grant tworzenia projektu ustanawia osobny bootstrap aplikacji.

`preflight` sprawdza wolny port, Linux Docker oraz szacuje headroom z working sets
kontenerów z rezerwą 1 GiB. To pomiar chwilowy, nie gwarancja dostępnej RAM.
Nie zatrzymuje innych usług, aby zwolnić zasoby. `up` powtarza sprawdzenie zasobów.

Po zbudowaniu API, migracji oraz UI i przeglądzie integratora:

```powershell
./deploy/platform/platform.ps1 -Action build
./deploy/platform/platform.ps1 -Action up
./deploy/platform/platform.ps1 -Action status
./deploy/platform/platform.ps1 -Action export-ca
./deploy/platform/platform.ps1 -Action stop
```

Adres: `https://localhost:9443`. CA jest własne; przeglądarka bez zaufania do niego
zgłosi błąd certyfikatu. Export zapisuje wyłącznie `.local/dev/root-ca.crt`, nie
instaluje CA. Klient testowy może użyć tego pliku jako jawnego trust anchor.
Nie wyłączaj weryfikacji TLS/issuer w aplikacji. `stop` zachowuje dane.

## Test równoległy i cleanup

```powershell
./deploy/platform/provision.ps1 -Profile test -Port 19443 -FixtureUsers
# Zapisz wypisany 12-znakowy run ID; używaj go w każdym kolejnym poleceniu.
./deploy/platform/platform.ps1 -Profile test -RunId <run-id> -Action check
./deploy/platform/test-compose.ps1 -RunId <run-id>
./deploy/platform/test-identity.ps1 -RunId <run-id>
./deploy/platform/platform.ps1 -Profile test -RunId <run-id> -Action build
./deploy/platform/platform.ps1 -Profile test -RunId <run-id> -Action up
./deploy/platform/platform.ps1 -Profile test -RunId <run-id> -Action cleanup-test -ConfirmTestDeletion
```

Cleanup odrzuca `dev`, błędny run ID i zasoby bez własnych etykiet. Niszczy tylko
bazę/wolumeny wskazanego testu po weryfikacji etykiet Compose i Torii. Bez backupu
tych danych nie odzyskasz. Lokalne secret files pozostają ignorowane na dysku;
nie ma automatycznego rekurencyjnego usuwania plików. Nigdy nie wykonuj globalnego
`docker system prune` ani cleanup demonstracji w ramach tego workflow.

Oddzielny test negatywny gateway (wymaga Docker i Python >=3.12):
`./deploy/platform/test-gateway.ps1`. Tworzy własne efemeryczne zasoby, sprawdza
zaufanie TLS, niedostępny upstream, Host, redakcję logów, limit body i zachowanie
ID/body odpowiedzi upstream; usuwa tylko swoje kontenery/sieć. Parametr
`-InternalNetwork` to diagnostyczny wariant A/B oczekujący błędu publikacji portu
w badanym Docker Desktop, nie wariant zaliczający ten sam test.

## Kontrakty i diagnostyka

Kontrakt API/env: [plan implementacji](implementation-plan.md).
API `app:create_app`, `/health/live` bez DB, `/health/ready` z kontrolą migracji.
Migrate jest jednorazowe, API czeka na sukces. IdP health jest prywatny.
Reverse proxy usuwa obce nagłówki proxy; API nie ufa dowolnemu forwarded IP.
Publiczne OIDC to realm `torii-dev`, confidential client `torii-web`, access token
audience `torii-api`, 5 minut, Authorization Code + PKCE S256. Brak password grant.

Lock obrazów: [images.lock.json](images.lock.json). Aktualizacja jest świadomą
zmianą: inspect nowego digestu, skan, build i pełna regresja. Dostępność obrazu
i pin nie dowodzą braku podatności. Wydanie enterprise wymaga skanów/SBOM,
testów auth/odmowy, backup+restore, obserwowalności i odbioru.

Logs lokalnego Compose są ograniczone rozmiarem 3×10 MiB na usługę; **nie jest to
jeszcze realizacja retencji czasowej 7 dni**. Nie włączamy access log gateway,
aby callback z authorization code nie trafiał do niego. Nie publikuj logów
bez redakcji i sprawdzenia. Błędy startu nie usprawiedliwiają `down -v` na dev.

Źródła: [Keycloak containers](https://www.keycloak.org/server/containers),
[hostname/issuer](https://www.keycloak.org/server/hostname),
[Caddy local HTTPS](https://caddyserver.com/docs/automatic-https).
