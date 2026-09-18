# ADR-0002: repozytoria i autorytatywne źródła danych

Status: Proposed. Data: 2026-09-19. Akceptujący: nie wskazano.

## Kontekst i alternatywy

Git, PostgreSQL, MLflow, magazyn artefaktów i DataHub zapisują różne aspekty
tego samego procesu. Bez podziału odpowiedzialności użytkownik widziałby
sprzeczne wersje definicji i historii.

Rozważono jedno repo wszystkich projektów, repo na każdy węzeł oraz repo na
niezależny projekt. Pierwsze utrudnia odrębne prawa i cykle wydania, drugie
komplikuje atomową zmianę Flow. Preferowany jest trzeci wariant.

## Proponowana decyzja

| Rodzaj informacji | Autorytatywne miejsce |
|---|---|
| Kod Torii i specyfikacje | Repozytorium platformy |
| Kod/deklaracje projektu | Commit repozytorium projektu; draft w jawnej working copy, nie w ukrytym drugim masterze |
| Zarejestrowane wersje | Baza Torii: niezmienny snapshot/import definicji powiązany z commitem lub utrwalonym draftem |
| Grants, stan wykonania, approvals/deployments | Baza Torii i jej audyt; nie pliki z Git akceptowane bez autoryzacji |
| Parametry/metryki eksperymentu i identyfikatory modeli MLflow | MLflow, z jednoznacznym mapowaniem do Torii |
| Bajty danych, modeli, raportów i paczek kodu | Wersjonowany magazyn artefaktów, identyfikowany manifestem i digestem |
| Sekrety | Zatwierdzony secret manager, tylko referencje w deklaracjach |
| Katalog organizacyjny | DataHub jako projekcja Torii; zewnętrzne pola według jawnego mapowania własności |

Wspólny kod wielu projektów staje się pakietem o własnej wersji; osobne repo
uzasadnia niezależne utrzymanie, nie samo istnienie modułu Python.

Import Git nie zmienia praw, właściciela ani sekretów na podstawie pliku.
Przeniesienie deklaracji do innego projektu wymaga jawnej operacji import/copy,
nowych uprawnień i zasad mapowania ID. Nie kopiuje danych przez przypadek.

## Konsekwencje i weryfikacja

Potrzebne są semantyczny diff, konflikty, mapowanie ID i protokół publikacji
przy częściowej awarii. Nie ma jednej transakcji obejmującej Git i bazę.
Outbox/reconciliation zapewniają wykrycie rozbieżności, nie magiczne exactly-once.

Dowód S3: zmiana GUI → commit → clone/import zachowuje znaczenie oraz ID;
zmiana z Git trafia do wersji dopiero po autoryzowanej walidacji.
Dowód integracji: awaria DataHub nie gubi Runu; replay zdarzeń nie duplikuje
obiektów ani nie nadpisuje pól zarządzanych przez innego właściciela.
