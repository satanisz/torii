# SP-00 — kontrakty przyszłych prób technicznych

Status kontraktów pełnych prób: Draft. Aktualizacja 2026-10-10: odrębna
[SPEC-0020 / EXP-03a](../../specs/0020-model-workbench-trial/README.md)
została przyjęta i wykonana; [wyniki](../../specs/0020-model-workbench-trial/evidence.md)
nie zaliczają całego EXP-03. EXP-01/02 nadal niewykonane. Każdy kolejny zakres
przed kodem i uruchomieniem wymaga własnego review. Dane syntetyczne, nowa
instalacja testowa, brak dostępu do firmy i historycznych wolumenów demonstracji.
Owner wyniku: platform/architekt; reviewer i konkretny wykonawca do wskazania.

## EXP-01 / D-06 — runner

Pytanie: czy Dagster albo prosty runner zapewnia kontrakt Torii bez przejęcia
domeny obiektów, ACL i wydań? Limit proponowany: jedna sesja do 4 h na kandydata,
maksymalnie dwóch kandydatów. Przekroczenie wymaga replanu.

Scenariusze: dwa projekty, transformacja Python, snapshot/wejście/wyjście,
restart dispatchera/workera, duplicate dispatch, timeout, cancel i stary lease.
Sprawdzić limity zasobów, brak host mounts/sekretów API, brak publikacji przez
starego workera, jeden wynik i pełny ślad prób. Zmierzyć narzut startu/utrzymania.

Go: inwarianty spełnione lub wykonalne w jawnym, oszacowanym adapterze.
No-go: brak izolacji, gubienie stanu po awarii lub obchodzenie ACL.
Rezultat: raport i ADR, nie automatyczne włączenie prototypu do produktu.
Bramka: przed Accepted SPEC-0004.

## EXP-02 / D-07 — snapshoty

Pytanie: czy publikacja jest spójna mimo awarii magazynu/bazy i konkurencji?
Limit proponowany: 4 h na nowym lokalnym magazynie S3.
Scenariusze: zmiana tego samego logicznego źródła, staging/upload/digest,
awaria między upload a commit, retry, nadpisanie/usunięcie chronionego obiektu,
sprzątanie orphan i brak wycieku globalnego istnienia hash przez dedup.

Go: v1 dostępna, tylko kompletne wyniki publikowane, cleanup nie usuwa aktywnych
referencji. No-go: nazwa z hashem to jedyna ochrona lub brak reconciliation.
Rezultat: raport/digesty, polityka retencji i ADR finalizacji.
Bramka: przed Accepted SPEC-0003; spójność SQL rozszerzyć przed SPEC-0005.

## EXP-03 / D-08 — MLflow i prawa

Pytanie: jak zachować tracking/model SDK bez dostępu projektu A do zasobów B?
Limit proponowany: 4 h na nowej instancji MLflow; nie rozwijamy bez końca proxy.
Scenariusze: list/search/read/download/upload/model registration/alias, znane
ID/URI innego projektu, cofnięcie grantu i retry. Oddzielnie model regułowy bez
fit. Ładowanie modelu tylko w izolacji, bez root keys magazynu w notebooku.

Go: każda dostępna metoda i artifact endpoint mają egzekwowaną politykę/audyt;
lista wspieranych metod SDK jawna. No-go: wymagany wspólny token do wszystkiego.
Rezultat: macierz API/SDK, ograniczenia, ADR i wpływ na zakres produktu.
Bramka: przed zobowiązaniem do SP-10 / Accepted SPEC-0010.

Wynik negatywny jest poprawnym zakończeniem badania. Może zmienić wybór
technologii, ale nie obniża wymagań bezpieczeństwa. Nie zaliczamy opisania
próby jako dowodu jej przeprowadzenia.
