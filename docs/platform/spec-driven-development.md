# Spec Driven Development w Torii

Reguła spec-first: wymagana przez właściciela produktu. Szczegóły procesu:
proponowany baseline do przeglądu. Nie jest to deklaracja certyfikacji.

## Cykl zmiany

1. Opisz problem, aktora, wartość, zakres i rzeczy poza zakresem.
2. Przypisz wymagania FR/NFR i przygotuj SPEC z obserwowalnymi kryteriami AC,
   scenariuszami negatywnymi, wpływem na dane i bezpieczeństwo.
3. Zaprojektuj kontrakty, model stanów, migrację i plan testów. Dla istotnych
   decyzji zapisz ADR z alternatywami i konsekwencjami.
4. Przeprowadź przegląd i zapisz akceptację uprawnionego człowieka albo
   zastosowanie jawnego [mandatu delegowanej realizacji](delivery-mandate.md).
   Delegowana akceptacja techniczna nie zastępuje ludzkiego odbioru enterprise.
5. Rozbij zaakceptowany zakres na małe zadania; najpierw przygotuj testy
   kontraktów/inwariantów, następnie kod. Nie dopisuj wymagań po fakcie,
   aby zalegalizować nieplanowane zachowanie.
6. Zbierz wyniki CI i testów ryzyka, wykonaj przegląd zmian i pokaż odbiór.
7. Wydaj wersję wraz z dowodami, migracją, monitoringiem i sposobem wycofania.

Wnioski z implementacji mogą zmieniać specyfikację, lecz zmiana kontraktu
wraca do przeglądu przed dalszym kodowaniem. SDD nie oznacza zamrożenia całego
produktu ani napisania z góry tysięcy stron.

## Artefakty i statusy

- `specs/NNNN-nazwa/README.md`: problem, wymagania, kontrakty, scenariusze,
  ryzyka, plan realizacji i dowody. Opcjonalnie `contracts/`, `examples/`,
  `test-plan.md`, `evidence.md` wewnątrz tej specyfikacji.
- `adr/NNNN-nazwa.md`: kontekst, alternatywy, decyzja i skutki. ADR nie jest
  miejscem na listę zadań ani zastępstwem testów.
- Wdrożone kontrakty maszynowe mają jedno kanoniczne źródło; generowane SDK,
  OpenAPI lub schematy sprawdzamy pod kątem rozjazdu w CI.
- Testy i PR odnoszą się do `SPEC-NNNN` oraz `AC-NN`. Raport podaje commit,
  środowisko, polecenie, wynik i lokalizację dowodu, bez sekretów i danych firmy.

Status specyfikacji: Draft → In review → Accepted → Implementing → Verified
→ Released; możliwe Superseded lub Withdrawn. Accepted określa zamrożoną
rewizję, akceptującego, datę i zakres. Zmieniona wersja wymaga ponownego
przeglądu odpowiedniego zakresu; stare dowody zachowują powiązanie ze starą rewizją.

Status ADR: Proposed → Accepted → Superseded/Deprecated. Asystent może
przygotować propozycję i zebrać dowody, ale nie może sam ustanowić niezależnej
akceptacji własnej pracy. Akceptacja udzielona w rozmowie musi zostać zapisana
z datą i precyzyjnym zakresem, nie domyślona.

## Warunki rozpoczęcia implementacji — Definition of Ready

- Jest Accepted SPEC i jawny właściciel akceptacji.
- Zakres i kryteria AC są testowalne; każde wymaganie ma pokrycie.
- Uzgodniono kontrakty i inwarianty, zachowanie przy błędach, uprawnienia,
  współbieżność i zgodność wsteczną.
- Rozstrzygnięto decyzje blokujące dany przyrost; nie wymagamy rozstrzygnięcia
  niezależnych spraw z późniejszych etapów.
- Jest plan testów, migracji/rollback i obserwowalności adekwatny do ryzyka.
- Zależności oraz ryzyka mają właściciela i kryterium rozstrzygnięcia.

## Warunki ukończenia — Definition of Done

- Wszystkie AC mają dowód PASS albo jawny brak spełnienia; brak dowodu
  nie jest PASS. Niespełnione kryterium obowiązkowe blokuje ukończenie.
- Kod, specyfikacja, dokumentacja i kontrakty opisują to samo zachowanie.
- Testy jednostkowe, kontraktowe, integracyjne i negatywne dla zmiany przeszły;
  krytyczna ścieżka ma test E2E na prawdziwych usługach, nie wyłącznie mockach.
- Lint, typowanie, walidacja schematów i analiza zależności przeszły.
  Procent pokrycia nie zastępuje testowania inwariantów i ścieżek odmowy.
- Przegląd bezpieczeństwa ma skalę adekwatną do ryzyka; pozostałe ryzyka
  są jawne, z właścicielem, uzasadnieniem i terminem, bez ukrytego pomijania CI.
- Migrację i wycofanie sprawdzono na kopii reprezentatywnych danych, jeżeli
  zmiana dotyczy trwałego stanu. Backup bez próby restore nie wystarcza.
- Są logi/metryki, komunikaty błędów, instrukcja eksploatacji i dowody odbioru.
- Niezależny przegląd ludzki poprzedza merge/release według polityki projektu.
  Dopóki takiego procesu nie ustanowiono, nie nazywamy zmian zatwierdzonym
  wydaniem enterprise.

## Skala procesu

Zmiana dokumentacyjna bez wpływu na zachowanie wymaga przeglądu i kontroli
spójności, nie osobnej wielostronicowej SPEC. Poprawka błędu: istniejąca SPEC,
opis naruszonego AC, odtwarzający test i aktualizacja dowodów. Refaktoryzacja:
krótka specyfikacja niezmienników i plan regresji. Nowa funkcja/adapter/migracja:
pełna specyfikacja. Przerwanie awarii: minimalny zapis incydentu, ryzyka,
autoryzacji i planu cofnięcia **przed zmianą**, potem uzupełnienie dowodów.

Eksperyment techniczny ma osobny, zatwierdzony zakres, limit i kryterium
go/no-go. Nie dotyka rzeczywistych danych firmy ani produkcji. Nie jest furtką
do implementacji platformy bez specyfikacji.

## Planowane bramki CI i przeglądu

1. Spec/ADR i identyfikatory AC, linki, schematy i przykłady.
2. Formatowanie, lint, typowanie i testy jednostkowe.
3. PostgreSQL, magazyn S3, OIDC i adaptery: testy integracyjne/kontraktowe.
4. GUI/API/SDK: uprawnienia, konflikty edycji, E2E i dostępność interfejsu.
5. Sekrety, zależności, licencje, obrazy, SBOM i pochodzenie artefaktów.
6. Testy migracji, odzyskiwania i wydajności w odpowiednim profilu.

Required checks, ochrona gałęzi, uprawnienia botów i CODEOWNERS wymagają
rzeczywistej konfiguracji repozytorium i wskazania osób. Ten dokument ani
`AGENTS.md` nie włączają tych zabezpieczeń technicznie. CI wdrażamy jako
specyfikowaną zmianę przed pierwszym merge kodu produktu.

## Standardy odniesienia

Proces bezpieczeństwa oprzemy na praktykach
[NIST SSDF 1.1, SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final):
bezpieczeństwo jest częścią cyklu wytwarzania, a nie wyłącznie testem na końcu.
Wymagania aplikacyjne dobierzemy z wersjonowanego
[OWASP ASVS](https://github.com/OWASP/ASVS), a pochodzenie buildów opiszemy
w oparciu o [SLSA](https://slsa.dev/spec/v1.2/tracks).
Są to punkty odniesienia, nie twierdzenie, że Torii spełnia dziś ich poziomy.
Mapowanie konkretnych kontroli i dowodów należy do przeglądu bezpieczeństwa.

Szablony: [SPEC](../../specs/_templates/spec.md), [ADR](../../adr/_template.md).
