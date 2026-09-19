# Rejestr specyfikacji Torii

Data: 2026-09-19. Numery są trwałe. Rezerwacja numeru nie oznacza, że dokument
istnieje, ma kontrakty lub jest Accepted. Nie utworzono fikcyjnych pustych SPEC.
Powiązanie ze sprintami: [plan](../docs/platform/sprint-plan.md).

| ID | Zakres | Stan dokumentu | Przygotować przed | Plan użycia |
|---|---|---|---|---|
| SPEC-0001 | Projekty, uprawnienia i wersje definicji | [Accepted (delegated) 0.2](0001-project-object-version/README.md) | SP-01 | SP-01–02 |
| SPEC-0002 | Engineering baseline: repo, CI, konfiguracja, obrazy, migracje, testowe środowiska, observability | [Accepted (delegated) 0.1](0002-engineering-baseline/README.md) | SP-01 | SP-01–02, rozszerzenia później |
| SPEC-0003 | Artefakty, CSV/Parquet, snapshoty i bezpieczny preview | Zarezerwowany; brak dokumentu | SP-03 | SP-03 |
| SPEC-0004 | Izolowane wykonania, transformacje Python, próby i recovery | Zarezerwowany; brak dokumentu | SP-04 | SP-04 |
| SPEC-0005 | Connection, SQL read-only, spójny odczyt i jakość danych | Zarezerwowany; brak dokumentu | SP-05 | SP-05 |
| SPEC-0006 | Flow DAG, porty, wersje i plan uruchomienia | Zarezerwowany; brak dokumentu | SP-06 | SP-06 |
| SPEC-0007 | Zespoły, udostępnianie między projektami i prawa do zależności | Zarezerwowany; brak dokumentu | SP-07 | SP-07; rozszerzenie dla modeli SP-10 |
| SPEC-0008 | Git, working copies, import/eksport definicji i konflikty | Zarezerwowany; brak dokumentu | SP-08 | SP-08 |
| SPEC-0009 | SDK/CLI, lokalny replay i izolowane workspace Jupyter | Zarezerwowany; brak dokumentu | SP-09 | SP-09 |
| SPEC-0010 | Eksperymenty MLflow, modele ML/nie-ML, bezpieczna publikacja | Zarezerwowany; brak dokumentu | SP-10 | SP-10 |
| SPEC-0011 | Analizy, ewaluacja, XAI, porównania i raporty | Zarezerwowany; brak dokumentu | SP-11 | SP-11 |
| SPEC-0012 | Release bundle, dowody i zatwierdzanie digestu | Zarezerwowany; brak dokumentu | SP-12 | SP-12 |
| SPEC-0013 | Deployment batch, środowiska, harmonogram i rollback | Zarezerwowany; brak dokumentu | SP-13 | SP-13 |
| SPEC-0014 | Import dziedzictwa AutoML/FrameML i odwracalna migracja | Zarezerwowany; brak dokumentu | SP-14 | SP-14 |
| SPEC-0015 | Kwalifikacja firmowego środowiska, bezpieczeństwo, wydajność, DR i eksploatacja | Zarezerwowany; brak dokumentu | SP-15; discovery od SP-00 | SP-15 |
| SPEC-0016 | Opcjonalna projekcja DataHub i reconciliation | Zarezerwowany; brak dokumentu | Przed implementacją adaptera | Kandydat po SP-11; poza obowiązkowym celem SP-11 |
| SPEC-0017 | Identyfikacja Torii i wspólne kontrakty UX/design system | [Accepted (delegated) 0.1](0017-interface-foundation/README.md) | SP-01 | SP-00 projekt; SP-01 implementacja; kolejne rozszerzenia |

SPEC-0001 obejmuje całość dwóch przyrostów; częściowy odbiór SP-01 nie nadaje
jej statusu Verified. SPEC-0002 musi być zaakceptowana przed kodem CI i
infrastruktury tak samo jak specyfikacja backendu. Zmiana ekranu wymaga AC
w specyfikacji funkcji oraz zgodności z SPEC-0017, nie tylko estetycznego review.

Jeśli pakiet jest zbyt duży na gotowy przyrost, dzielimy go przed Accepted,
rezerwując nowe ID i zachowując mapowanie do wymagań. SPEC-S2 używane w starszej
roadmapie oznacza rodzinę prac etapu S2, obecnie rozpisaną na SPEC-0003/0004/0005.
