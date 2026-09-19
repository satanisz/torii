# SP-00 — pakiet do przeglądu i akceptacji

Data: 2026-09-19. Status przy sporządzeniu: **In review**.
Aktualizacja: [mandat użytkownika](delivery-mandate.md) dopuszcza baseline
do lokalnej realizacji. Poniższe wyniki dokumentują stan sprzed implementacji.
Commit baseline planu i logo: `a7b19a5`.
Poniższe rozszerzenie przygotowano w working tree po tym commicie; bez push.

## Wynik

| Obszar | Artefakt | Stan |
|---|---|---|
| Backend i domena | [SPEC-0001 0.2](../../specs/0001-project-object-version/README.md), OpenAPI/JSON Schema, macierz ról i transakcji | Przygotowane, kontrola schematów PASS; wymaga review |
| Infrastruktura | [SPEC-0002 0.1](../../specs/0002-engineering-baseline/README.md) | Topologia, CI, sekrety, migracje i restore opisane; brak implementacji |
| Frontend | [SPEC-0017 0.1](../../specs/0017-interface-foundation/README.md) | Nawigacja, stany, role, konflikty i dostępność opisane; brak UI/prototypu |
| Ryzyka techniczne | [EXP-01–03](sp-00-technical-trials.md) | Przygotowane zakresy prób runner/storage/MLflow; nie przeprowadzono |

Wnioski samoprzeglądu wprowadzone do kontraktu: strong ETag obejmuje całą
reprezentację obiektu, a edycja polityki ma odrębny pełny zasób zamiast ETag
wspólnego dla różnych stron członkostw. Powtórzenie identycznej definicji
nie tworzy sztucznej wersji. Receipt idempotencji nie omija bieżących uprawnień.
To przegląd autora specyfikacji, nie niezależny audyt.

## Rekomendacje wymagające akceptacji

1. Modularny control plane Python/FastAPI + PostgreSQL; projekty użytkowników
   nie są wykonywane w API. React/TypeScript jako oddzielny frontend.
2. Keycloak/OIDC do dev, sesja backendowa dla UI, Bearer dla SDK; role
   reader/editor/owner. W pierwszym przyroście maks. 100 członków projektu.
3. Nieprzepisywalne wersje definicji, JCS/SHA-256, jawne ETag/konflikty,
   transakcje serializowane per projekt i receipt retry z retencją 24 h.
4. Nowy odizolowany stos dev/test, bez zmiany historycznych wolumenów/.env;
   toolchain i obrazy przypinane w buildzie SP-01, kontrole CI przed jego odbiorem.
5. Pierwszy UI: projekty, katalog, definicje/wersje i uprawnienia; jeden jasny
   motyw roboczy z ciemną nawigacją, motyw/logo jako referencja, bez własnego IDE.

Akceptacja powinna wskazać SPEC-0001 0.2, SPEC-0002 0.1, SPEC-0017 0.1 oraz
zakres ADR-0001/0002/0003. Oznacza zgodę na opisany przyrost, nie udzielenie
zgody na używanie danych firmy, deployment produkcyjny, push lub zmianę
ochrony zdalnej gałęzi. Brak formalnej akceptacji nie uniemożliwia przeglądu
i poprawienia specyfikacji, ale blokuje implementację aplikacji.

## Dowody kontroli specyfikacji

Wykonano:

```powershell
uv run --python 3.12 --no-project specs/0001-project-object-version/validate_contracts.py
```

Wynik: OpenAPI 3.1, 21 unikatowych operacji, poprawna schema dwóch typów,
5 poprawnych i 13 odrzucanych definicji, 8 przypadków request API, 2 wzorce JCS — PASS.
Python i Node dały te same bajty/hash dla dwóch jawnych wektorów przykładowych:

| Wektor | SHA-256 |
|---|---|
| csv-order-independent | `86ebac4657d6c6b5f49d8260f63a4135a43c4500ad880a0b919cadda902d6c36` |
| sql-string-preserved | `151f4925ff091c022dadd940b9cf8bb5ade3d88bcf1ee77e0fe81ea267716538` |

Kontrola pomocnicza: Ruff 0.14.5 — PASS; odnośniki lokalne w 33 dokumentach
Markdown — PASS; `git diff --check` — PASS. Narzędzia sesji: Node v24.15.0,
uv 0.11.19, Python wybierany przez `uv --python 3.12`; dokładne zależności
bezpośrednie walidatora zapisano w jego nagłówku. To nie lock runtime produktu.

To ograniczony test zgodności przykładów, nie certyfikacja wszystkich przypadków
JCS. Kontrola ujawniła, że przestarzałe `validate_spec` biblioteki pomijało bazowy
URI referencji; walidator używa `validate` i poprawnie rozwiązuje lokalne schema.
Pakiety narzędziowe zainstalowano przez uv w jego izolowanym cache, bez zmiany
runtime działającej demonstracji i bez instalacji globalnej.

Nie wykonano: testów serwera/API, OIDC, PostgreSQL, migracji, bezpieczeństwa
runtime, CI ani UI — tych implementacji jeszcze nie ma. Żadne AC produktu nie
otrzymuje PASS na podstawie tego raportu. Nie zmodyfikowano obrazów, usług,
połączeń, danych ani oryginalnego logo.

## Status prac SP-00

| Zadanie | Stan faktyczny |
|---|---|
| SP00-01 | Zakres i ADR opisane; preferencja modularności potwierdzona, formalna akceptacja baseline pozostaje otwarta |
| SP00-02/03 | Kontrakty i macierz praw przygotowane; przykłady zwalidowane, wymagany przegląd |
| SP00-04 | Specyfikacja infrastruktury w review; topologia nieuruchomiona |
| SP00-05 | Specyfikacja UX w review; graficzny walkthrough i warianty assetów niewykonane |
| SP00-06 | Macierz AC/threat model przygotowane; niezależny reviewer do wskazania |
| SP00-07 | Zakresy trzech prób zapisane; akceptacja i wykonanie przed zależnymi sprintami |
| SP00-08 | Oczekuje na akceptację rewizji, reviewerów i pojemność SP-01 |
| SP00-09 | Opcjonalne warianty logo nieprzygotowane; oryginał zachowany |

SP-00 nie jest jeszcze odebrany, SP-01 nie jest Ready. Kolejny krok to review
tych konkretnych decyzji i ewentualne poprawki, a nie ponowne planowanie całej
platformy. Firma będzie potrzebna przed rzeczywistym wdrożeniem; do dalszego
dopracowania tych kontraktów nie potrzeba chmury ani dodatkowych kont.
