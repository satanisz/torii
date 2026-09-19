# Torii — plan platformy korporacyjnej

Data: 2026-09-19. Status: **baseline dopuszczony do lokalnej realizacji**.
Zakres zgody: [mandat użytkownika](delivery-mandate.md), stan: [dziennik](delivery-progress.md).
Punkt odniesienia kodu: `fbd4b1f` / `2f94f77` na `main`.

## Cel produktu

Torii ma umożliwiać zespołom korporacyjnym budowanie, współdzielenie,
odtwarzanie i kontrolowane uruchamianie procesów danych, analiz oraz modeli.
Ma zastępować uzgodnioną część zastosowań Databricks, bez wymagania jego usług.
Nie deklarujemy zgodności funkcjonalnej z całym Databricks ani gotowości
regulacyjnej wynikającej z samego wyboru technologii.

Najważniejsze pytanie odbiorowe: **czy za pół roku potrafimy ustalić, kto,
z jakich danych, jakim kodem i modelem, w jakim środowisku oraz za czyją zgodą
wytworzył konkretny wynik — i czy możemy go rzeczywiście odtworzyć?**

## Ustalenia użytkownika a propozycje

Potwierdzone w rozmowie:

- nazwa produktu Torii, rozwój obecnego repozytorium;
- dane, transformacje, modele, eksperymenty oraz analizy/XAI jako osobne byty;
- obsługa także modeli niestanowiących ML;
- jeden spójny interfejs, z możliwością pracy w Pythonie, Git i Jupyter;
- korporacyjne współdzielenie, śledzenie danych/kodu/eksperymentów;
- wyraźne oddzielenie budowy, eksperymentowania i produkcji;
- Spec Driven Development przed każdą implementacją.
- preferencja modułowej budowy, przekazane logo jako kierunek identyfikacji.

Baseline kontraktów, ról i technologii objęto mandatem autonomicznej realizacji.
Parametry firmowe pozostają propozycjami: nie wybrano dostawcy tożsamości ani
infrastruktury firmy. Keycloak jest lokalnym IdP developerskim.

## Jak czytać pakiet

| Dokument | Co rozstrzyga |
|---|---|
| [Stan i wymagania](requirements.md) | Co istnieje, czego brakuje, zakres produktu i identyfikatory wymagań |
| [Model domenowy](domain-model.md) | Obiekty, wersje, wykonania, lineage, odtwarzanie i Git |
| [Architektura](architecture.md) | Moduły, granice zaufania, integracje i wspólny interfejs |
| [Proces SDD](spec-driven-development.md) | Specyfikacje, przegląd, testy, zmiany, warunki wejścia i ukończenia |
| [Bezpieczeństwo i jakość](security-and-quality.md) | Zagrożenia, kontrole i dowody wymagane przed pilotażem |
| [Plan realizacji](roadmap.md) | Etapy, zależności, scenariusz odbiorowy, decyzje i ryzyka |
| [Plan sprintów](sprint-plan.md) | Zintegrowane przyrosty infrastruktury, backendu i frontendu; szczegółowo SP-00–02 |
| [SP-00: pakiet do review](sp-00-review.md) | Konkretne kontrakty, rekomendacje i dowody kontroli specyfikacji |
| [Rejestr specyfikacji](../../specs/README.md) | Istniejąca SPEC-0001 i jawne rezerwacje kolejnych numerów |
| [Logo i identyfikacja](../brand/README.md) | Oryginał od użytkownika i zakres przygotowania do UI |
| [SPEC-0001](../../specs/0001-project-object-version/README.md) | Pierwsza konkretna specyfikacja: projekty, katalog obiektów i wersje |
| [ADR-0001](../../adr/0001-platform-boundaries.md) | Granice platformy i sposób rozbudowy obecnego repozytorium |
| [ADR-0002](../../adr/0002-git-and-authority.md) | Repozytoria i jednoznaczne źródła prawdy |
| [ADR-0003](../../adr/0003-reproducibility-and-releases.md) | Odtwarzalność, wersje i wydania |

## Co oznacza pierwszy działający produkt

Pierwszy przekrój produktu ma obsłużyć wiele tożsamości i pełny proces od danych
do zatwierdzonego wyniku. Ma mieć niewiele konektorów i typów zadań, ale rzeczywiste
kontrole dostępu, historię, obsługę błędów i odtworzenie.

Lokalny Docker będzie środowiskiem deweloperskim i demonstracyjnym tej samej
architektury. Nie oznacza produktu jednoosobowego. Podział dev/test/prod będzie
widoczny w domenie od początku; symulacja produkcji lokalnie nie uprawnia do
przetwarzania rzeczywistych danych produkcyjnych.

## Stan tego dostarczenia

Aktualizacja realizacyjna: [dziennik](delivery-progress.md) jest źródłem bieżącego
stanu; opis poniżej zachowuje punkt odniesienia końca planowania SP-00.
Pierwsze fundamenty FastAPI, UI i odizolowanej infrastruktury są w realizacji,
nie oznacza to ukończenia SP-01 ani gotowości produkcyjnej.

Powstał pakiet planistyczny i zasady pracy w `AGENTS.md`. W SP-00 przygotowano
OpenAPI/JSON Schema, przykłady i ich walidator offline, SPEC-0001 0.2 oraz
SPEC-0002/0017 0.1 do review. Nie powstały backend, frontend, migracje ani
nowe mechanizmy ochronne runtime.
Pakiet rozszerzono o prognozowany plan sprintów, karty SP-00–02, rejestr SPEC
i niezmienioną kopię przekazanego logo. Preferencja modularności nie oznacza
akceptacji wszystkich szczegółów ADR ani Definition of Ready dla implementacji.
Nie zmieniono działającej instalacji Docker, danych ani `.env`.
Testy odbiorowe wymienione w planie są **planowane, nie wykonane**.

Aktualizacja: po przygotowaniu kontraktów użytkownik zlecił realizację sprintów.
Przeglądy techniczne, testy i dowody pozostają bramkami każdego przyrostu;
nie wymagamy projektowania każdego przyszłego adaptera przed pierwszym kodem.
