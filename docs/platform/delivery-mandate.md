# Mandat realizacji Torii

Data: 2026-09-19. Źródło: bieżąca rozmowa z właścicielem produktu.

Użytkownik wskazał FastAPI, zaakceptował infrastrukturę i frontend, zlecił
umieszczenie logo w README, commit oraz autonomiczne przechodzenie przez
sprinty z walidacją, commitami i agentami do prostszych zadań.

## Przyjęty zakres

- FastAPI/Python jako backend, React/TypeScript jako UI; odizolowany nowy
  stos PostgreSQL/Keycloak/Caddy w lokalnym Dockerze.
- SPEC-0001 0.2, SPEC-0002 0.1, SPEC-0017 0.1 i ADR-0001/0002/0003 stanowią
  baseline do implementacji. Status **Accepted (delegated)** oznacza przyjęcie
  techniczne w granicach mandatu, nie twierdzenie, że użytkownik sprawdził
  każdą regułę HTTP, test czy decyzję architektoniczną.
- Kolejne specyfikacje i rewizje w uzgodnionej roadmapie: najpierw kontrakt,
  AC, ryzyka i plan testów; przegląd techniczny przed implementacją; dowody
  przed oznaczeniem Verified. Nie trzeba budzić użytkownika po każdy szczegół.
- Lokalne buildy, syntetyczne dane, nowe wydzielone zasoby dev/test oraz commity
  spójnych przyrostów. Agent nie robi commitów równolegle z integratorem.

## Granice

Brak zgody na push, PR, zmianę ochrony gałęzi, płatne usługi, produkcyjne
wdrożenie, rzeczywiste dane firmy ani zmianę/wykasowanie istniejących wolumenów
i root `.env`. Lokalny test nie zastępuje firmowego IdP, DR ani odbioru bezpieczeństwa.
Nie instalujemy CA globalnie. Nie obniżamy kryteriów po to, żeby zamknąć sprint.

Niezależny przegląd przez agenta nazywamy przeglądem technicznym, nie audytem
człowieka. Jeśli dalszy etap wymaga decyzji firmy, kończymy bezpieczny lokalny
zakres i raportujemy konkretną brakującą decyzję, bez fikcyjnego PASS.

## Kontynuacja i odbiór

Aktualizacja2026-09-19: użytkownik priorytetyzuje ręcznie testowalny demonstrator
konceptu i jawnie dopuszcza mniejszy zakres zamiast100%enterprise. SPEC-0018/ADR-0004
wydzielają lokalny, jednoosobowy profil bez SSO i oddzielnych firmowych danych.
To nowy cel najbliższego odbioru; nie zalicza niespełnionych AC enterprise sprintów.
SDD/review, rzeczywiste funkcje, testy i izolacja legacy nadal obowiązują.
Najpierw spójny flow CSV→transformacja→regresja→MLflow→porównanie wReact,
potem rozbudowa. Parquet/SQL/Jupyter/multiuser/rozbudowaneXAI odłożone.

Źródłem bieżącego stanu jest [dziennik realizacji](delivery-progress.md).
Każdy wpis rozróżnia implementację, wykonane kontrole i brakujące AC.
Pełen sprint jest ukończony dopiero po spełnieniu jego obowiązkowych AC.
Roadmapa nie jest obietnicą ukończenia platformy enterprise przez jedną noc.
