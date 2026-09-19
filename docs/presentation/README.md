# Prezentacja Torii

[Otwórz prezentację HTML](torii.html). Otwórz plik w przeglądarce po pobraniu
repozytorium. GitHub pokazuje kod HTML, nie uruchamia prezentacji.
Zachowaj folder `docs/brand/assets` z oryginalnym logo.

## Zakres dokumentacyjny

Użytkownik zlecił uporządkowanie README, instrukcje i prezentację sposobu
działania oraz zależności. To dokumentacja SPEC-0018 D07, bez zmiany API,
uruchomionych usług, danych, zależności aplikacji ani zakresu enterprise.

Prezentacja obejmuje osobne obiekty i wersje, przepływ demonstratora,
moduły Python/React, rzeczywisty MLflow, magazyny danych, zależności budowania,
podział Git/dane oraz granicę między demo, fundamentem enterprise i legacy.
Wartości przykładowych metryk pochodzą z zapisanego odbioru syntetycznego.

## Obsługa

- Przyciski Poprzedni/Następny lub klawisze strzałek zmieniają slajd.
- Home/End przechodzą do pierwszego/ostatniego slajdu.
- Spis slajdów pozwala wybrać temat. Adres `#slajd-5` otwiera dany slajd.
- „Wszystkie slajdy” pokazuje cały materiał do czytania. Druk przeglądarki
  obejmuje wszystkie slajdy, także w trybie prezentacji.
- Bez JavaScript treść pozostaje widoczna. Brak CDN, fontów z sieci,
  analityki i wywołań API. Link do aplikacji jest ręcznym przejściem na localhost.

## Plan kontroli

Spójność ze źródłami, sprawdzenie lokalnych linków i składni skryptu,
przegląd techniczny, odczyt i nawigacja w prawdziwej przeglądarce,
desktop oraz wąski ekran. Wyniki kontroli zapisujemy w dzienniku realizacji.
Nie ogłaszamy ponownego odbioru aplikacji na podstawie zmiany dokumentacji.

Automatyczna kontrola (korzysta z istniejącego `apps/web/node_modules`):

```powershell
node scripts/check-demo-docs.mjs
```

Polecenie wykonuj z katalogu repozytorium. Sprawdza lokalne odnośniki,
12 slajdów, identyfikatory, nawigację i fallback bez JavaScript. Kontrola
druku obejmuje wywołanie oraz regułę CSS dla wszystkich slajdów, nie render PDF.
