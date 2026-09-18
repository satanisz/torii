# Torii: zasady pracy nad repozytorium

Torii jest projektowane jako wieloużytkownikowa platforma korporacyjna danych,
analiz i modeli. Obecny AutoML/Docker jest demonstracją, nie platformą produkcyjną.

## Spec Driven Development

- Przed zmianą zachowania przeczytaj `docs/platform/README.md`,
  `docs/platform/spec-driven-development.md` i specyfikację danej zmiany.
- Najpierw wymaganie i scenariusze odbioru, następnie kontrakty i plan testów,
  dopiero później implementacja. Dotyczy to także infrastruktury i migracji.
- Każda implementacja musi wskazywać identyfikator SPEC i kryteria AC.
  Naprawa błędu może rozszerzać istniejącą specyfikację; dodaj test regresyjny.
- Nie traktuj statusów Draft/Proposed jako zatwierdzenia. Nie zatwierdzaj sam
  własnej specyfikacji ani nie przypisuj użytkownikowi nieudzielonej akceptacji.
- Zmiana zakresu, modelu danych, bezpieczeństwa albo kontraktu wymaga aktualizacji
  specyfikacji przed kodem; istotna decyzja architektoniczna wymaga ADR.
- Prototyp badawczy wymaga opisanego pytania, ograniczenia czasu i kryterium
  decyzji; nie staje się automatycznie kodem produktu.
- Wynik raportuj jako zaimplementowany, zweryfikowany albo niezweryfikowany.
  Dokumentacja, test mocka i działający ekran nie dowodzą gotowości produkcyjnej.

## Granice bezpieczeństwa i odpowiedzialności

- Rozdzielaj definicję obiektu, jego niezmienną wersję i wykonanie.
- Git przechowuje kod i deklaracje; dane, modele i wyniki mają osobny magazyn.
  Sekrety nie trafiają do Git, specyfikacji, artefaktów ani logów.
- GUI, SDK, CLI i Jupyter podlegają tej samej autoryzacji backendu.
  Nie uruchamiaj kodu użytkowników w procesie API.
- Eksperyment, zatwierdzone wydanie i środowisko produkcyjne to różne pojęcia.
  Alias modelu i nazwa gałęzi nie wystarczają do odtworzenia wykonania.
- Zachowaj stare importy, artefakty, workspace i wolumeny, dopóki zatwierdzona
  specyfikacja migracji nie przewiduje zmiany. Nie uruchamiaj dwóch stosów
  zapisujących jednocześnie do tych samych wolumenów.
- Nie modyfikuj ignorowanego `.env`, działających usług, zdalnego repozytorium
  ani zasad ochrony gałęzi w ramach samego planowania/przeglądu.
- Obowiązujące ustawienia stacji opisuje `docs/local-installation.md`.

Plan architektury jest propozycją do przeglądu. Reguła pracy spec-first wynika
z bezpośredniego wymagania właściciela produktu i obowiązuje już teraz.
