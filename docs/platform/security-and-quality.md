# Bezpieczeństwo, niezawodność i dowody jakości

Status: Draft. Kontrole poniżej są wymaganiami do zaprojektowania i sprawdzenia,
nie opisem aktualnego Compose. Dane firmowe pozostają poza demonstracją.

## Wymagania niefunkcjonalne

| ID | Wymaganie i miara | Bramka |
|---|---|---|
| NFR-01 | Deny-by-default; pełna macierz ról dla API/SDK, list, wyszukiwania, lineage, preview, eksportu, logów i artefaktów; żaden test nieuprawnionego dostępu nie może przejść jako dozwolony | S1 i każdy nowy endpoint |
| NFR-02 | Kod użytkownika poza API; zadanie nie czyta cudzych plików, sekretów hosta ani innych projektów; timeout, pamięć/CPU, cancel, kontrola sieci | S2; weryfikacja produkcyjna S6 |
| NFR-03 | Każdy gotowy wynik ma kompletny manifest i zweryfikowany digest; brak zależności uniemożliwia deklarację dostępnego replay | S2–S5 |
| NFR-04 | Trwałość stanu po awarii, przetestowany restore, RPO/RTO i plan przerw zatwierdzone przed rzeczywistym użyciem | S1/S2; odbiór operacyjny S6 |
| NFR-05 | Mierzalny profil obciążenia i budżety opóźnień; brak blokowania API przez trening lub preview dużych plików | pomiary od S1; docelowy profil S6 |
| NFR-06 | Przypięte zależności/obrazy, SBOM, analiza sekretów/licencji/podatności, weryfikowalne pochodzenie i integralność wydania | CI od S1; release gate S5/S6 |
| NFR-07 | Wersjonowane API/manifesty, jawne migracje i test zgodności GUI/SDK/CLI; brak cichej zmiany semantyki | od S1 |
| NFR-08 | Correlation ID: żądanie → Run → próba → artefakt → integracja; metryki awarii, kolejek i opóźnienia projekcji; alert ma właściciela/runbook | od S1/S2 |
| NFR-09 | Klasyfikacja, minimalizacja, szyfrowanie, retencja i kontrola eksportu obejmują dane, metadane, logi, notebook outputs, modele i raporty | od S1; polityka firmy przed S6 |
| NFR-10 | Klawiatura, czytelne komunikaty, stany odmowy/awarii; krytyczne ścieżki możliwe bez drag-and-drop i bez samego rozróżnienia kolorem | od pierwszego UI |

## Proponowane cele pilotażu — nie SLA

Do zatwierdzenia z firmą po ustaleniu skali i krytyczności. Te wartości są
budżetem do testów, nie dowodem wydajności ani właściwym SLA dla każdego procesu.

- Profil P1: 25 aktywnych użytkowników, 5 równoległych zadań, 10 000 wersji
  obiektów, 100 000 rekordów wykonań, pliki wejściowe do 1 GiB.
- API metadanych: p95 do 500 ms przy 20 żądaniach/s, mniej niż 1% odpowiedzi
  5xx przez 30 minut. Test określa miks operacji, paginację, cache i topologię;
  nie zalicza czasu transferu danych ani treningu do tego samego budżetu.
- UI: podstawowy ekran katalogu używalny do 2 s na ustalonej sieci testowej.
- Propozycja usługowa: dostępność 99,5% miesięcznie, RPO do 15 min, RTO do 4 h.
  Liczenie dostępności, okna obsługowe i budżet błędów muszą być jawne.
  Krytyczne procesy mogą wymagać znacznie ostrzejszych wartości.
- Limity pamięci, czasu, magazynu i budżetu projektu konfigurowalne; zadanie
  przekraczające limit kończy się kontrolowanym błędem i nie zatrzymuje API.

Profil D1 lokalny służy funkcjonalnym testom wielu tożsamości i awarii.
Wyniki D1 nie potwierdzają P1. Przed benchmarkiem zapisujemy CPU/RAM/dysk/sieć,
wersje usług, stan cache i zużycie zasobów. Czas treningu zależy od modelu i
danych, nie otrzymuje fikcyjnej gwarancji uniwersalnej.

## Wstępny model zagrożeń

| Zagrożenie | Wymagana kontrola | Dowód negatywny |
|---|---|---|
| Podmiana project/object ID, odczyt cudzych metadanych | Autoryzacja obiektu i filtrowanie zapytań przed paginacją/agregacją | Użytkownik obcego projektu nie widzi nazwy, liczników, wersji ani lineage |
| Ominięcie Torii przez MLflow/S3/DataHub | Prawa usług spójne z Torii, prywatne endpointy, krótkie tokeny/URL scoped do obiektu | Token projektu A i URL artefaktu nie dają odczytu projektu B |
| Utrzymanie dostępu po odebraniu roli | Bieżąca autoryzacja, ograniczony czas delegacji, jawna polityka anulowania zadań | Odebrany grant blokuje nowe odczyty/uruchomienia; mierzymy okno ważności istniejących URL/tokenów |
| Złośliwy model/pickle/notebook/Python | Brak deserializacji w API; izolacja wykonania, read-only filesystem, non-root, brak Docker socket i host mounts | Payload nie wykonuje kodu w API i nie czyta pliku innego zadania |
| SSRF i SQL na niedozwolonym celu | Polityka sieci, kontrola połączeń/DNS/redirects, rozdział admina konektora, read-only konto DB i parametry | Próba dostępu do hosta/metadanych infrastruktury i zapis SQL są odrzucane |
| Przejęcie sesji/tokena | OIDC, bezpieczne sesje, CSRF/CORS, rotacja, scope/audience, TLS; MFA egzekwowane przez firmowy IdP | Token o złym issuer/audience lub wygasły jest odrzucany; przeglądarka nie przechowuje długiego sekretu w projekcie |
| Wyciek przez preview, log, raport HTML lub notebook output | Redakcja, limity próbkowania, ACL, sanitizacja/izolacja HTML i kontrola eksportu | Testowy sekret i skrypt nie pojawiają się/nie wykonują w UI lub raportach |
| Przejęta zależność albo obraz | Locki, digesty, zaufane registry, skany, SBOM i podpisy/attestations | Zmieniony artefakt lub niedozwolony obraz nie przechodzi promocji |
| Nadpisanie danych, zatwierdzenia lub wyniku | Finalizacja wersji, integralność, approvals dla digestu, fencing przy retry | Modyfikacja po akceptacji unieważnia możliwość wdrożenia; stary worker nie publikuje |
| Manipulacja audytem | Oddzielne prawa, append-only dla aplikacji, eksport do chronionego magazynu, weryfikacja integralności | Rola aplikacji nie edytuje historii; awaria eksportu uruchamia alert |
| Nieograniczony koszt/DoS | Quotas, limity upload/preview, rate limits, timeout i limity zadań | Wielki plik/rozpakowanie i nadmiar zadań nie wyczerpują całego hosta |
| Utrata bazy lub magazynu | Spójny plan backupu metadanych i artefaktów, test restore i reconciliation | Odtworzenie sprawdza nie tylko start usług, ale referencje, digesty i replay |

To wstępny rejestr, nie kompletny pentest. Specyfikacje dodają zagrożenia
charakterystyczne dla konektora, formatu, tożsamości i sposobu wykonania.

## Audyt, prywatność i retencja

Audyt operacji zmieniającej stan jest zapisywany atomowo z metadanymi albo
operacja nie jest uznana za wykonaną. Audyt odczytów wrażliwych i odmów ma
ustaloną trwałość, wydajność i politykę zachowania przy awarii. Zapisujemy
actor, delegację, action, object/version, environment, decision, correlation ID
i czas UTC; bez tokenów, haseł i pełnych rekordów danych.

Nie nazywamy tabeli append-only niezmienną wobec administratora bazy.
Wymagany poziom odporności na manipulację, przechowywanie poza zasięgiem roli
aplikacji, WORM/podpisy i monitoring dostępu ustalamy z bezpieczeństwem firmy.

Polityka obejmuje także modele mogące ujawniać informacje z treningu i raporty
XAI. Usuwanie i legal hold wymagają właściciela procesu; tombstone musi sam
respektować minimalizację danych. Replikacja, backup oraz eksport mają tę samą
klasyfikację co źródło. Nie kopiujemy produkcyjnych danych do laptopa domyślnie.

## Wydanie i utrzymanie

Przed realnym pilotażem wymagamy: zatwierdzonego threat modelu, przejścia
uzgodnionych kontroli ASVS, przeglądu licencji, analizy obrazu, SBOM, testu
izolacji, testu upgrade/restore i wskazanego operatora z runbookami.
Brak otwartych krytycznych podatności jest warunkiem wydania. Pozostałe ryzyko
wymaga udokumentowanej decyzji uprawnionego właściciela, nie asystenta.

Plan reagowania musi obejmować: kradzież poświadczeń, zatrzymanie zadań,
unieważnienie modelu/release, podatną zależność, odzyskanie danych i komunikację.
Okna patchowania, okres wsparcia wersji i częstotliwość restore drill wymagają
właścicieli. Nie rozszerzamy w ciemno obecnej macierzy starszych Pythonów
na wspierany produkt enterprise; baseline runtime podlega osobnemu przeglądowi.

Wersjonowane mapowanie wymagań aplikacji opracujemy na podstawie
[OWASP ASVS](https://github.com/OWASP/ASVS); wymagania pochodzenia buildów
na podstawie [SLSA](https://slsa.dev/spec/v1.2/tracks).
Pełna lista kontroli, poziom i wyjątki muszą być przyjęte dla konkretnego wdrożenia.
