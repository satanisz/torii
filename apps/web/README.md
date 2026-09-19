# Torii web — dwa punkty wejścia

Wspólny projekt React / TypeScript / Vite buduje dwa **odrębne interfejsy**.
Demo nie jest trybem omijającym zabezpieczenia aplikacji enterprise.

| Punkt wejścia | Kod | Backend | Stan |
|---|---|---|---|
| `demo.html` → `dist/demo.html` | `src/demo/` | Własne `/demo-api/*` w `apps/demo` | Działający lokalny demonstrator: dane, transformacje, modele, eksperymenty i wyniki. |
| `index.html` → `dist/index.html` | `src/main.tsx`, `src/App.tsx` | Docelowo `/api/v1/*` oraz `/auth/*` w `apps/api` | Fundament SP-01 oznaczony DEV. Pełne logowanie i integracja produktowa nie są jeszcze ukończone. |

## Uruchomienie rzeczywistego demo

Na Windows, z **katalogu głównego repozytorium**, uruchom:

```powershell
.\scripts\demo.ps1
```

Otwórz [http://127.0.0.1:18440](http://127.0.0.1:18440).
FastAPI serwuje zbudowany `demo.html`, zasoby i własne API z tego samego origin.
Wymagane są Python 3.12, uv, Node.js ≥24.15.0 i <25 oraz npm 11. Docker nie jest
potrzebny. [Instrukcja demo](../demo/README.md) oraz
[obsługa lokalna](../../docs/demo-operations.md) opisują start, stop i dane.

Demo jest stale oznaczone „lokalnie / bez SSO”. Używaj wyłącznie danych
syntetycznych lub niesensytywnych; nie udostępniaj portu przez LAN ani Internet.
Zapisy używają nagłówka `X-Torii-Demo: 1`. To lokalny warunek żądania,
**nie uwierzytelnienie ani kontrola dostępu użytkowników**.

Komponenty wyświetlają prawdziwe dane z API. Fixtures występują wyłącznie
w testach. CSV, wersje, wykonania i artefakty nie są wersjonowane w Git.
Kontrakt i kryteria demo: [SPEC-0018](../../specs/0018-concept-demo/README.md).

## Walidacja i budowanie

Polecenia poniżej wykonuj z `apps/web`, używając Node 24.15.0 (sprawdzona
wersja) oraz npm 11. Dokładne ograniczenia określa [package.json](package.json).

```powershell
npm ci --ignore-scripts
npm run api:check
npm run typecheck
npm run lint
npm test
npm run build
npm audit --audit-level=low
```

`npm run build` sprawdza kontrakt enterprise i typy, a następnie buduje oba
punkty wejścia do `dist/`. Testy komponentowe nie dowodzą integracji API ani
gotowości logowania; rzeczywisty browser smoke ma osobny zakres odbioru.

`npm run api:generate` odtwarza typy enterprise z kanonicznego
[OpenAPI](../../specs/0001-project-object-version/contracts/openapi.json).
Zmiany pliku generowanego wymagają przejrzanej zmiany źródłowego kontraktu;
`api:check` wykrywa rozbieżność. Kontrakt demo jest osobny.

`npm run dev` i `npm run preview` nasłuchują tylko na loopback. **Nie dostarczają
API ani usługi tożsamości.** Otwarcie samego Vite nie uruchamia pełnego demo;
do ręcznego testu całego procesu używaj skryptu `demo.ps1`.

## Granica interfejsu enterprise

Zakres fundamentu SPEC-0001 / SPEC-0002 / SPEC-0017 i jego dowody opisuje
[IMPLEMENTATION.md](IMPLEMENTATION.md). Bieżący stan integracji:
[dziennik realizacji](../../docs/platform/delivery-progress.md).

Dystrybucję enterprise należy podawać przez
[odizolowany gateway platformy](../../deploy/platform/README.md), z HTTPS,
same-origin `/api/v1/*`, `/auth/*` i fallbackiem SPA dla tras klienta.
Sam poprawny build lub ekran logowania nie oznacza działającego OIDC.
Nie wyłączaj kontroli TLS/issuer i nie wstawiaj tokenu do kodu dla demonstracji.

Trasy fundamentu: `/login`, `/projects`, `/projects/:id`,
`/projects/:id/access`, `/projects/:id/audit`. Nie ma przycisków udających
niezaimplementowane moduły. Mutacje używają bieżącego CSRF sesji,
warunkowych ETag i kluczy idempotencji operacji. Backend musi każdorazowo
sprawdzać prawa; widoczność przycisku nie jest autoryzacją.

Build nie wstrzykuje adresów API, credentials, tokenów Bearer, endpointów
telemetrii, fontów zewnętrznych ani mock API. Nie jest proxy do legacy AutoML.
Dockerowy build używa ograniczonego kontekstu `apps/web` oraz publicznego
kontraktu potrzebnego do `api:check`; nie może kopiować głównego `.env`.

## Logo

`public/torii-logo.jpg` to niezmieniona, identyczna bajtowo kopia oryginału
użytkownika, używana przez oba interfejsy. Nie jest nowym projektem ani
deklaracją licencji. [Pochodzenie i status wariantów](../../docs/brand/README.md).
