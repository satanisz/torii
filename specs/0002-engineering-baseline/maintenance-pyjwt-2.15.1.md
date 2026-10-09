# SPEC-0002 M-01 — aktualizacja bezpieczeństwa PyJWT

Rewizja 0.1, 2026-10-10. Status: **Accepted (delegated)**.
Niezależny review przed kodem: integrator `/root`, po odczycie kontraktu,
lokalnej ścieżki RS256 i oficjalnych advisory; autor `platform_runtime`.
Właściciel: integrator Torii. Zakres: utrzymanie zależności API, NFR-01/06/07,
bramka skanu z [SPEC-0002](README.md). Review techniczny przed zmianą pinu.

## Problem i decyzja do przeglądu

Raport `apps/api/.venv/dependency-audit-b2a4b.json` wykazał dla PyJWT 2.14.0:

- PYSEC-2026-4141 / GHSA-42vr-xj54-vc7v: rekursywny payload może wypuścić
  `RecursionError` poza kontrakt biblioteki. Potwierdzony skutek upstream to błąd
  pojedynczego wywołania, bez wykazanego crash procesu lub obejścia uwierzytelnienia.
- PYSEC-2026-4183 / GHSA-x33g-cr3x-6449: import prywatnego OKP JWK nie sprawdzał
  zgodności publicznego `x` z kluczem wyprowadzonym z prywatnego `d`.

Obie poprawki są wydane od 2.15.0. Proponowany dokładny pin to
`PyJWT[crypto]==2.15.1`, istniejące wydanie poprawkowe z 2026-09-28.
Torii zachowuje profil **RS256**, własny bounded parser JSON, odrzucanie
prywatnych pól JWKS oraz istniejące reguły issuer/audience/nonce/at_hash.
Nie dodajemy OKP/DPoP ani nowych algorytmów, profili, endpointów lub wyjątków
autoryzacji. Ustalenia upstream nie dowodzą podatności aktualnej ścieżki Torii:
nie używa ona `PyJWKClient` ani `jwt.decode(..., verify_signature=False)`.

## Granica zmiany i plan

1. Po niezależnym review i Accepted zmienić wyłącznie pin w
   `apps/api/pyproject.toml` i wykonać ukierunkowany relock PyJWT w `apps/api/uv.lock`.
   Pozostałe wersje pakietów mają pozostać identyczne; niespodziewany upgrade
   wymaga wyjaśnienia przed przyjęciem diffu. Instalacja i walidacja z frozen lock.
2. Najpierw dodać syntetyczne regresje biblioteki: głęboki payload daje
   `jwt.exceptions.DecodeError`, a nie surowy `RecursionError`; niespójne `x/d`
   dla Ed25519 i Ed448 dają `InvalidKeyError`. Dołączyć poprawne przypadki
   kontrolne. To testy upstream, nie rozszerzenie obsługiwanych algorytmów Torii.
3. Wykonać istniejące regresje granicy Torii: głębokość/rozmiar JSON,
   prywatne JWKS, RS256, token attacks i bezpieczne błędy; następnie pełne
   testy jednostkowe API, lint/typy i ponowny audyt zależności runtime.

## Kryteria odbioru

| AC | Wymagany dowód |
|---|---|
| M01-01 | Pin i lock wskazują 2.15.1; porównanie wersji locka nie wykazuje innych upgrade; frozen sync i kontrola zainstalowanej wersji przechodzą. |
| M01-02 | Dwie rodziny regresji upstream i ich poprawne kontrole przechodzą offline; nie wykonują I/O ani nie używają rzeczywistych credentials. |
| M01-03 | Istniejące testy parserów/kluczy/tokenów i pełne unit API, Ruff/mypy przechodzą; kontrakty i profil RS256 pozostają bez zmian. |
| M01-04 | Ponowny pip-audit runtime nie zgłasza obu wskazanych advisory; zapisane wersja skanera, polecenie, data i wynik. Inne zgłoszenia pozostają jawne, bez blanket ignore. |

Nie kwalifikuje to całego SP-01 ani działających obrazów: bez rebuild/deploy
ich zależności pozostają dotychczasowe. Wycofanie pinu przywróciłoby zgłoszone
luki i blokadę bramki; przy regresji zatrzymać promocję i ponownie przejrzeć
rozwiązanie. Brak zmian danych, migracji, usług, legacy lub sekretów.

Źródła oficjalne sprawdzone 2026-10-10:
[payload advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v),
[OKP advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-x33g-cr3x-6449),
[wydanie 2.15.0](https://github.com/jpadilla/pyjwt/releases/tag/2.15.0),
[wydanie 2.15.1](https://github.com/jpadilla/pyjwt/releases/tag/2.15.1).

## Dowody implementacji — 2026-10-10

Środowisko: Windows, Python 3.12.12, uv 0.11.19; katalog poleceń `apps/api`.
Testy wykonane poza sandboxem Windows ze względu na znaną blokadę asyncio.
Nie uruchamiano usług ani rzeczywistego loginu, nie zmieniano kodu verifiera.

- RED przed zmianą zależności: `python -m pytest tests/test_pyjwt_security_regressions.py -q --tb=short`
  na 2.14.0: **4 FAIL, 3 PASS**. Rekursywny payload wypuszczał `RecursionError`
  przez unsigned decode i PyJWKClient; obie krzywe przyjmowały niespójne `x/d`.
  Poprawne przypadki kontrolne przechodziły. Wejście ma stałą głębokość4096
  (około8KiB), odpowiednią dla parsera C przypiętego CPython3.12; jawny EdDSA
  w testach zapobiega pomyleniu błędu autodetekcji Ed448 z kontrolą zgodności.
- `uv lock --upgrade-package pyjwt`, następnie `uv sync --frozen`: **PASS**.
  Porównanie50 wpisów pakietów przed/po wykazało wyłącznie zmianę
  `pyjwt 2.14.0 → 2.15.1`; zainstalowana wersja potwierdzona przez `jwt.__version__`.
- GREEN: `python -m pytest tests/test_pyjwt_security_regressions.py tests/test_oidc_keys.py tests/test_oidc_tokens.py tests/test_oidc_token_attacks.py tests/test_json_envelope.py -q --tb=short`:
  **387 PASS**, w tym wszystkie7 nowych testów. Pozostały2 dotychczasowe
  ostrzeżenia Starlette/httpx i AnyIO.
- Końcowa bramka integratora: `python -m pytest -q -m 'not integration' --cov`:
  **1565 PASS, 53 deselected, 2 dotychczasowe warnings**,20.90s.
  Pełny przebieg obejmował także obecne w working tree **WIP B2a4b** oraz
  wszystkie7 nowych regresji PyJWT; nie przypisujemy całego wyniku wyłącznie
  commitowi maintenance. Ruff check/format63 plików i strict mypy32 modułów:
  **PASS**. Commit maintenance ma obejmować tylko pin/lock/test PyJWT i ten aneks;
  B2a4b jest osobnym przyrostem i commitem integratora.
- `python -m ruff check tests/test_pyjwt_security_regressions.py`,
  `python -m ruff format --check tests/test_pyjwt_security_regressions.py`,
  `python -m mypy src` (32 moduły) oraz `git diff --check`: **PASS**.
- `uv export --frozen --no-dev --no-editable --no-emit-project --output-file .venv/runtime-requirements.txt --quiet`
  i `uvx --from pip-audit==2.10.1 pip-audit --disable-pip --no-deps -r .venv/runtime-requirements.txt --format json --output .venv/dependency-audit-pyjwt-2.15.1.json`:
  **34 pakiety runtime, 0 zgłoszonych podatności**. Zachowana ogólna rekomendacja
  skanera dotycząca pełnego hashowania eksportu; bez ignorowania advisory.
  Raport lokalny SHA-256:
  `dc2233c168e022239df51d00e79b14588641cd12c31d65beca88ed8a72002ce0`.

Wynik skanu dotyczy bazy advisory z chwili wykonania, nie jest dowodem braku
wszystkich luk. Rebuild/deploy i odbiór całego SP-01 pozostają poza tym przyrostem.
