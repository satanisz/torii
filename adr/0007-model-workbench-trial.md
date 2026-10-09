# ADR-0007 — izolowany warsztat MLflow przed integracją z katalogiem

2026-10-10. Status: Accepted (delegated), review `regulated_examples` przed kodem.
Zakres: [SPEC-0020](../specs/0020-model-workbench-trial/README.md),
wyłącznie lokalna próba EXP-03a; nie wybór docelowego IdP lub magazynu banku.

## Kontekst i decyzja

Użytkownik priorytetyzuje architekturę narzędzi do tworzenia modeli i udostępnił
Docker. Katalog wersji, wykonania i pełne logowanie Torii nadal wymagają osobnych
przyrostów. Samo dołożenie widoku wyników nie weryfikuje warsztatu modelowania.

Proponujemy uruchomić MLflow 3.14.0 jako kandydata na adapter eksperymentów,
PostgreSQL dla jego metadanych/auth oraz wymienialny lokalny backend S3 SeaweedFS.
Trening i testy wykonują osobne kontenery. Nie montujemy Docker socket ani kodu
hosta. Klient treningowy zna wyłącznie MLflow i swoje techniczne konto.
Natywne basic-auth jest przedmiotem testu, nie przejęciem polityk Torii.

Rewizja ingress (2026-10-10, Accepted delegated po review `regulated_examples`):
lokalny Docker Desktop nie publikuje
portu MLflow przy wyłącznie internal networks. Dodajemy Caddy ze stałym upstream
MLflow, na osobnej sieci ingress i API. Tylko jego port jest wystawiony na loopback.
Worker, MLflow i magazyny pozostają bez routowalnej sieci zewnętrznej. Caddy nie
dostaje sekretów, socketu ani danych użytkownika; nie jest otwartym forward proxy.
Budżet czterech usług + jednego joba nadal mieści się w 4 CPU / 4 GiB.

Torii pozostaje planowanym właścicielem Project/Object/Version/Release i ACL;
MLflow odpowiada za tracking/registry we wskazanym, przetestowanym podzbiorze.
Manifest pochodzenia jest punktem wejścia do późniejszego grafu, nie zastępczym
katalogiem ani dowodem pełnego observed-read lineage.

## Alternatywy i konsekwencje

Pełne uruchomienie legacy wnosi wiele niezależnych usług i historyczne dane.
Kontynuacja samego OAuth nie sprawdza narzędzi modelowania. Jednoczesne dodanie
Dagstera, Jupytera i Kubernetesa rozmywa pytania EXP-01/02/03. Te integracje mają
własne kontrakty i bramki; nie są warunkiem wykonania małego treningu w kontenerze.

SeaweedFS jest kandydatem do lokalnego S3 z licencją Apache-2.0. Testujemy potrzebne
operacje, nie deklarujemy całkowitej zgodności z AWS S3. Nie zmieniamy legacy MinIO.

Wynik NO-GO dla natywnego ACL/audytu oznacza konieczność zaprojektowania granicy
adaptera lub odrębnych instancji projektowych przed SPEC-0010. Nie należy tworzyć
nieograniczonego proxy ani podawać wspólnego tokenu użytkownikom.

## Źródła i decyzja po próbie

- [MLflow authentication](https://mlflow.org/docs/latest/self-hosting/security/basic-http-auth/)
- [MLflow server](https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server/)
- [SeaweedFS S3 API](https://github.com/seaweedfs/seaweedfs/wiki/Amazon-S3-API)
- [SeaweedFS](https://github.com/seaweedfs/seaweedfs)

Dowodem dla wersji będą testy uruchomionego MLflow 3.14.0, nie samo latest docs.
Wyniki i kwalifikacja podzbioru API zostaną zapisane w evidence SPEC-0020.
