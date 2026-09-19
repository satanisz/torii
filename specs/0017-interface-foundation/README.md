# SPEC-0017 — wspólny interfejs Torii i identyfikacja

Rewizja 0.1, 2026-09-19. Status: **Accepted (delegated)**.
Podstawa: [mandat użytkownika](../../docs/platform/delivery-mandate.md).
Zakres: SP-01/02, projektowanie SP-00. Wymagania FR-11, NFR-01/07/10.
Logo źródłowe i jego pochodzenie: [materiał marki](../../docs/brand/README.md).
Ta specyfikacja nie generuje nowych grafik ani nie implementuje UI.

## Cel i architektura informacji

Jeden interfejs pracy z obiektami i ich historią. W pierwszym przyroście
przechodzimy login → projekty → katalog → obiekt → draft/wersja.
Nie budujemy panelu linków/iframe do MLflow, MinIO i DataHub.

| Route UI | Widok i funkcja | API / dostęp |
|---|---|---|
| `/login` | Wejście przez OIDC, stan błędu/dostawca niedostępny | `/auth/login`; brak lokalnego formularza haseł |
| `/projects` | Widoczne projekty i utworzenie, jeśli uprawnione | session, list/create projects |
| `/projects/:id/objects` | Katalog z kind/state/q i paginacją cursor | listObjects; brak globalnych liczników |
| `/projects/:id/objects/:objectId` | Metadane, typ, właściciel projektu, stan | getProject/getObject; uprawnienia z kontekstu, nie z created_by |
| `.../draft` | Formularz definicji, walidacja i zapis warunkowy | getDraft/replaceDraft; reader tylko odczyt |
| `.../versions` i `.../versions/:versionId` | Historia i nieedytowalny szczegół wersji, porównanie | listVersions/getVersion |
| `/projects/:id/access` | Lista członkostw, role, dodanie po principal ID | owner-only GET/PUT access-policy z ETag |
| `/projects/:id/audit` | Minimalna historia zmian z paginacją | owner-only audit API |

Powłoka: stała nawigacja, breadcrumb projektu/obiektu, identyfikacja użytkownika
i jawny znacznik środowiska. Aktywne są tylko dostarczone funkcje. Flow, modele,
analizy i wydania dojdą w swoich przyrostach z tymi samymi wzorcami.
Route nie jest dowodem uprawnienia; serwer decyduje o dostępie do każdego zasobu.

S1 potrzebuje kontraktu effective permissions dla przycisków. Propozycja:
`getProject` zwraca `my_role`, a session `can_create_project`; UI mapuje role
według SPEC-0001. To informacja do ergonomii, nie token uprawnień. Po 403/404
UI odświeża kontekst i nie powtarza automatycznie zabronionego zapisu.

## Wzorce wspólne

- Teksty UI po polsku, identyfikatory techniczne i kody błędów niezmienne;
  teksty zebrane poza komponentami, aby później dodać język bez zmiany API.
- Tabele: nazwa, typ, ostatnia wersja, stan, autor/czas. Nazwa czytelna,
  trwałe ID dostępne do skopiowania; nie wymagamy pracy na UUID w głównej nawigacji.
- Formularz definicji ma sekcje odpowiadające schema, bez dowolnego edytora
  „config JSON” jako jedynego sposobu pracy. Widok surowego JSON do inspekcji.
- SQL i nazwa modułu Python są tekstem definicji, nie wykonują się po podglądzie.
  Etykieta „Definicja — niewykonana” zapobiega myleniu jej z DatasetVersion/Run.
- Każdy ekran: loading, empty, success, forbidden/not-found, error/retry;
  draft dodatkowo dirty, saving, saved, conflict i archived/read-only.
- Bez optymistycznego sukcesu finalizacji lub zmiany grantów przed potwierdzeniem
  API. Double-click blokowany w UI, lecz bezpieczeństwo retry wynika z kontraktu API.
- Nie zapisujemy tokenów, danych i draftów w localStorage. Edycja do potwierdzenia
  może pozostać w pamięci karty; opuszczenie dirty formularza wymaga ostrzeżenia.
- Toast nie jest jedynym nośnikiem błędu. Formularz wskazuje pole i summary,
  globalny błąd pokazuje request ID; brak echo sekretu lub stack trace.

## Konflikt i błędy

412: pokazujemy, że zmieniła się rewizja. Zachowujemy lokalny tekst w pamięci,
po ponownej autoryzacji pobieramy wersję serwera i pokazujemy różnice.
Użytkownik świadomie łączy zmiany i zapisuje na nowym ETag. Nie wysyłamy cichego
force-save. 409: pokazujemy konkretny konflikt biznesowy, bez bezsensownego retry.
422: błędy po JSON Pointer mapowane na pola. 429/503: respektujemy Retry-After;
automatycznie ponawiamy tylko bezpieczne odczyty z ograniczonym backoff.
Mutacje ponawiamy wyłącznie według kontraktu idempotencji albo decyzji użytkownika.

401: odnawiamy sesję przez ustalony flow logowania, bez zapisu „na później”
pod inną tożsamością. 403/404 po utracie dostępu: usuwamy dane z cache widoku,
nie pozostawiamy cudzych danych w panelu porównania. Nie da się cofnąć wcześniej
pobranych bajtów, dlatego UI nie obiecuje takiej ochrony.

## Marka i dostępność

Ciemny granat i koral/błękit z logo są inspiracją, nie precyzyjnie pobraną paletą.
S1: jeden dopracowany jasny motyw roboczy z ciemną nawigacją, tekstową nazwą
Torii i referencją znaku. Pełny przełącznik motywów nie jest warunkiem katalogu.
Nie używamy dużego JPG jako tła tabel. Wektory/favikona mogą być osobnym zadaniem
po przyjęciu specyfikacji; oryginał pozostaje niezmieniony.

Tokeny semantyczne: surface/background/text/muted/border/focus oraz
primary/success/warning/danger. Kolory DEV/TEST/PROD mają również tekst i ikonę.
Typografia systemowa, bez zewnętrznego CDN fontów; body 16 px, gęsta tabela
nie mniej niż 14 px przy zachowaniu zoom. Pola/akcje keyboard-accessible,
widoczny focus, etykiety programowe, dialog z prawidłowym zarządzaniem focusem.

Cel dostępności: zakres WCAG 2.2 AA dla dostarczanych ścieżek, sprawdzany
automatycznie i ręcznie. Tekst standardowy co najmniej 4,5:1, duży 3:1,
istotne nietekstowe kontrolki/focus co najmniej 3:1. Nie polegamy tylko na
kolorze. Wymagania referencyjne:
[WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/).
Nie deklarujemy zgodności całego produktu na podstawie samego pomiaru kontrastu.

Projektujemy desktop od 1280 px; przy 1024 px nawigacja się zwija. Zoom 200%
nie może blokować akcji. Długie tabele mają własny scroll, nazwy/pola bez
utraty znaczenia. UI mobilne do budowy dużego Flow nie jest zakresem S1.

## Kryteria odbioru — testy jeszcze niewykonane

| AC | Scenariusz odbioru | Powiązanie |
|---|---|---|
| AC-01 | A loguje się i przechodzi projekty → obiekt → wersje bez opuszczenia kontekstu Torii; E nie widzi P1 | FR-11, NFR-01 |
| AC-02 | Reader ma odczyt bez pozornie działających akcji; ręczne API nadal odrzuca write | NFR-01, SPEC-0001 AC-02 |
| AC-03 | Dwa klienty zapisują draft; 412 daje porównanie bez zgubienia tekstu i bez force-save | SPEC-0001 AC-04/13 |
| AC-04 | Formularz mapuje 422 na pola, request ID dostępny przy 503, retry nie dubluje finalizacji | NFR-07, SPEC-0001 AC-06/08 |
| AC-05 | Nawigacja, formularze, tabela i dialog obsłużone wyłącznie klawiaturą, przy zoom 200% i z odczytem etykiet | NFR-10 |
| AC-06 | Pomiar tokenów i stanów focus/error spełnia progi kontrastu; stan rozpoznawalny bez koloru | NFR-10 |
| AC-07 | Nieaktywny moduł nie udaje gotowej funkcji; definicja nie jest nazywana zbiorem utrwalonych danych ani wykonaniem | FR-11 |
| AC-08 | Logout/utrata grantu czyści wrażliwy cache widoku; token/body nie trafiają do localStorage i telemetrii | NFR-01/09 |

## Realizacja, review i wycofanie

SPEC-0017 definiuje wspólne wzorce; szczegółowe AC każdej funkcji pozostają
w jej SPEC. Komponenty/testy powstają po Accepted w SP-01/02. Review UX poprzedza
merge, lecz nie zastępuje E2E z API. Assety marki wymagają osobnego zatwierdzenia
wariantu przed publikacją. Cofnięcie UI używa zgodnego API/kontraktu; nie cofa
danych ani finalizowanych wersji. Aktualnie do akceptacji: nawigacja, zakres
motywu/marki i powyższe zachowanie; brak gotowego prototypu graficznego.
