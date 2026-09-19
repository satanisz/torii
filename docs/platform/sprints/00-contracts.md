# SP-00 — kontrakty i przygotowanie do implementacji

Status: baseline kontraktów przyjęty do realizacji na podstawie
[mandatu](../delivery-mandate.md). Opcjonalne warianty logo i późniejsze próby
techniczne pozostają otwarte przed zależnymi sprintami, nie blokują SP-01.
Powiązania: S0, SPEC-0001/0002/0017, ADR-0001/0002/0003.
Cel: zamknąć niepewności blokujące pierwszy pionowy przyrost, nie projektować
szczegółowo wszystkich szesnastu celów roadmapy.

## Wejście

Wymagania użytkownika i pakiet planistyczny są dostępne. Preferencja modułowej
budowy potwierdzona; szczegóły ADR nadal Proposed. Nie potrzebujemy teraz
dostępu do firmy, zakupu chmury ani zmiany bieżącego Dockera.

## Backlog do wykonania w tej iteracji

M = obowiązkowe dla celu; O = opcjonalne. Właściciele oznaczają role potrzebne
do odbioru, nie automatycznie utworzone zespoły. Estymata każdej pozycji przed
wyborem implementacji; obecnie nieustalona. Tabela opisuje zakres planu.
Aktualny stan i dowody opisuje [podsumowanie SP-00](../sp-00-review.md).

| ID | Tor / priorytet | Zadanie i artefakt | Zależność | Kryterium odbioru |
|---|---|---|---|---|
| SP00-01 | Produkt / M | Zapisać zakres pierwszego procesu, granice modularności, decyzje ADR i non-goals | Brak | Właściciel rozróżnia demonstrator i wdrożenie enterprise; akceptacja ma zakres, datę i rewizję |
| SP00-02 | Backend/security / M | Pełna macierz create/read/edit/archive/grant, tożsamość OIDC, role projektowe i odmowy | SP00-01 | Dwie osoby w P1, jedna w P2; żaden nieautoryzowany odczyt/grant nie ma nieokreślonego wyniku |
| SP00-03 | Backend / M | SPEC-0001 rewizja 0.2: schematy definicji, OpenAPI, przykłady, ETag, hash, constraints, idempotency i migracja | SP00-02 | Wszystkie AC-01–15 mają kontrakt i plan testu; walidatory przyjmują poprawne przykłady i odrzucają błędne |
| SP00-04 | Infrastruktura / M | SPEC-0002: nowy stos dev/test, topologia, połączenia, sekrety, limity, porty, runtime, CI i restore | SP00-01/02 | Mapa zasobów nie wykorzystuje historycznych wolumenów ani współdzielonych haseł; plan testów jest wykonalny na opisanym profilu |
| SP00-05 | Frontend/UX / M | SPEC-0017: nawigacja, kontrakt komponentów, stany UI, formularze, klawiatura i użycie logo | SP00-01/02 | Przejście projektu → katalogu → wersji oraz odmowy/konfliktu jest zrozumiałe bez działającego backendu |
| SP00-06 | QA/security / M | Rozwinąć threat model S1, macierz testów, fixtures i wymagane kontrole CI | SP00-03/04/05 | Każde AC ma rodzaj testu i źródło dowodu; bezpieczeństwo i negatywne ścieżki nie są osobnym „później” |
| SP00-07 | Architektura / M | Przygotować zakresy prób D-06/D-07/D-08: runner, finalizacja snapshotu i autoryzacja MLflow | SP00-03/04 | Każda próba ma pytanie, limit, dane syntetyczne, go/no-go i sprint decyzji; samo napisanie planu nie udaje wyniku próby |
| SP00-08 | Review / M | Przegląd kontraktów i podział zadań SP-01/SP-02, ownerzy i pojemność | SP00-01–07 | Akceptacja SPEC-0001/0002/0017 albo jawna lista poprawek; zakres SP-01 nie przekracza ustalonej pojemności |
| SP00-09 | Marka / O | Przygotować do zatwierdzenia wariant znaku do nawigacji i favicon | SP00-05 | Zachowany oryginał, sprawdzony mały rozmiar i tła; brak publikacji niezatwierdzonego assetu |

SP00-09 nie blokuje specyfikacji domeny. W razie braku gotowych wariantów
interfejs może początkowo używać tekstowej nazwy Torii i referencyjnego znaku
zgodnie z uzgodnionym kontraktem. Nie poświęcamy kontroli dostępu na dopracowanie
efektów wizualnych. Zakres przygotowania assetów jest pracą projektową,
nie zgodą na modyfikowanie teraz przekazanego logo.

## Podział odpowiedzialności

- Właściciel produktu: scenariusz, granice i akceptacja zakresu.
- Backend/platform: kontrakty, trwałość, konfiguracja i plan eksploatacji.
- Frontend/UX: architektura informacji, czytelność i obsługa stanów.
- QA/security/reviewer: niezależny przegląd ryzyk i dowodów; osoby do wskazania.

Asystent przygotowuje rekomendacje, dokumenty i sprawdzenia. Nie podpisuje
za użytkownika Accepted ani nie zastępuje drugiej niezależnej roli ludzkiej.
Przy braku recenzenta kontynuujemy dopracowanie dokumentów, bez deklaracji
pełnego odbioru enterprise.

## Review i warunek wyjścia

Review obejmuje: przykład poprawnego i błędnego API, dwie konkurencyjne edycje,
odebranie grantu, finalizację z retry i błąd audytu. W interfejsie przechodzimy
te same sytuacje na projekcie ekranów; nie traktujemy tego jako E2E aplikacji.

SP-00 jest odebrany, gdy kontrakty i zakres implementacji są Accepted,
specyfikacje spełniają Definition of Ready, a zadania SP-01 mają właścicieli,
zależności, estymaty oraz testy. Sam ten plan sprintów nie zamyka SP-00.

Brak wymaganej decyzji oznacza dalsze refinement lub zmniejszenie zakresu,
nie generowanie kodu „na próbę”. Zmiany planu są wersjonowane w Git;
nie ma migracji danych ani potrzeby cofania usług w tej iteracji.

Następny przyrost: [SP-01](01-foundation.md).
