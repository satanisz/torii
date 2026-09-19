# ADR-0004: osobny lokalny demonstrator konceptu

Status Accepted (delegated),2026-09-19; niezależny contract_review przed kodem.
Użytkownik zmienił najbliższy cel na ręcznie testowalny koncept, bez wymagania
pełnego enterprise. Kontynuowanie wszystkich bramek SSO/DR przed danymi i modelami
nie dostarcza tej wartości. Nie wstawiamy debug identity do enterprise API.

Decyzja proponowana: jawny apps/demo FastAPI z własnym SQLite/artifacts i loopback,
reuse React build/logo/dependencies, osobny entrypoint demo.html. Realne dane,
transformacje, regresja Ridge/baseline i MLflow, ale bez multiuser/SSO/SQL
connectors/productiondeployment. SPEC-0018 jest osobnym zakresem odbioru; nie
zmienia zaliczenia enterprise sprintów. Kod domenowy demo modułowy; późniejszy
transfer do controlplane wymaga adapterów, migracji i kontroli dostępu.

Odrzucone: mock-only UI (nie testuje konceptu); auth bypass w produkcyjnym
entrypoint (miesza profile bezpieczeństwa); legacy MLflow volumes (ryzyko danych);
czekanie na pełne wszystkie enterprise sprinty (sprzeczne z nowym priorytetem).
Koszt: drugi lekki adapter storage/API do późniejszej migracji, lokalny operator
ma dostęp do całości demo. Nie nadaje się do LAN/Internet/danych firmy.
