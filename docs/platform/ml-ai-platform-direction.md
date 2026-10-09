# Kierunek rozwoju FrameML i Torii jako platformy ML i AI

Data: 2026-10-09. Status: propozycja kierunku do dalszego planowania.
Punkt odniesienia: Torii `a2b1cc2`.

Aktualizacja po doprecyzowaniu potrzeb: użytkownik wskazał finanse banku
(księga, portfele, NII, prognozy i anomalie). Pierwszy proces oraz konkretny
dobór architektury opisuje [warsztat finansów banku](banking-finance-research.md).
Przykład dostaw poniżej pozostaje historyczną ilustracją ogólnego cyklu ML.

**Rekomendacja: rozwijać Torii jako platformę, która prowadzi zespoły od pracy
na danych i eksperymentu do kontrolowanego wdrożenia oraz utrzymania ML i AI.**
Ogłoszenie Billennium na stanowisko ML Platform Engineer wzmacnia ten kierunek.
Najważniejsza korekta to większy nacisk na pełny cykl eksploatacji: wdrażanie,
monitorowanie, diagnozowanie awarii i wycofywanie zmian.

FrameML jest tu kontekstem dotychczasowych środowisk i demonstracji;
repozytorium `torii` pozostaje miejscem rozwoju produktu. Zachowujemy istniejący
rdzeń danych, transformacji, modeli, analiz, wersji i wykonań. Obsługa modeli
regułowych oraz pracy analitycznej nadal ma miejsce w tym zakresie.

## Co zmienia perspektywa z ogłoszenia

Przekazana oferta opisuje wspólny obszar AI/ML Engineering i MLOps/Platform
Engineering, po 50% obowiązków. Zespół buduje rozwiązania biznesowe oraz
środowisko, w którym można je bezpiecznie rozwijać i utrzymywać. Wymieniono
przetwarzanie batch i online, Kubernetes, CI/CD, obserwowalność, governance
oraz rozwój w stronę agentów. Kubeflow Pipelines jest pozycją „nice to have”.

Dla Torii wynika z tego propozycja mierzenia postępu **sprawnością całej ścieżki
użytkownika i operatora**. Sam trening, katalog modeli czy atrakcyjny interfejs
pokazują tylko część wartości. Drugą częścią jest odpowiedź na pytania:
co działa w danym środowisku, kto dopuścił tę wersję, dlaczego wykonanie
zawiodło, jak je bezpiecznie ponowić i jak przywrócić poprzednie wydanie.

Cel „zastąpić uzgodnioną część zastosowań Databricks” warto przełożyć na
konkretne procesy zespołu. Pierwszy z nich może obejmować prognozę opóźnień
dostaw. Sukcesem będzie samodzielne przejście tego procesu przez autora,
recenzenta i operatora, z dowodami jakości i pochodzenia wyników.

Ogłoszenie jest inspiracją produktową, a nie specyfikacją Torii. Wskazane
„setki modeli” opisują skalę tamtego środowiska; nie ustanawiają naszego celu
MVP. Podział 50/50 nie wyznacza proporcji kodu ani czasu naszych sprintów.
Źródłem opisu roli jest tekst przekazany przez użytkownika 2026-10-09.

## Punkt wyjścia w projekcie

| Obszar | Co istnieje | Co pozostaje do osiągnięcia |
|---|---|---|
| [Demonstrator](../../apps/demo/README.md) | Lokalny przepływ CSV/synthetic → transformacja → Ridge/baseline → MLflow → analiza; wersje i powiązania wyników | Wielu użytkowników, SSO, kontrolowane wydania i obsługa produkcyjna. Eksport manifestu nie jest pełnym pakietem odtworzenia. |
| [Fundament enterprise](../../apps/api/README.md) | Komponenty projektów, transakcji, polityk dostępu i OIDC; osobny frontend oraz [infrastruktura dev/test](../../deploy/platform/README.md) | Pełne logowanie i połączenie API z UI. W [fabryce API](../../apps/api/src/torii_api/app.py) podłączone są tylko trasy health; SP-01 pozostaje nieukończony. |
| [Legacy](../legacy-workspaces.md) | Obrazy workspace, scaffold, AutoML i wcześniejsze integracje MLflow/MinIO/DataHub | Przydatność tych elementów dla nowej platformy wymaga integracji i weryfikacji jej granic. |
| Dostarczanie i operacje | [Workflow CI fundamentu](../../.github/workflows/platform-foundation.yml), lokalne skrypty kontroli i zapisane dowody testów | Kompletny proces wydawania, obserwowalność usług i modeli, odzyskiwanie oraz odbiór na docelowej infrastrukturze. |

Bieżący status określa [dziennik realizacji](delivery-progress.md). Historyczne
fragmenty wymagań i roadmapy opisują wcześniejszy stan. Zapisane wyniki testów
demo nie oznaczają ukończenia sprintów enterprise ani aktualnie działającej
instalacji produkcyjnej.

## Zakres docelowej platformy

| Zdolność | Wartość dla użytkownika | Miejsce w rozwoju |
|---|---|---|
| Samoobsługowa praca zespołu | Projekt, uprawnienia, wersje danych/kodu i spójna praca przez GUI, Python oraz Git | Istniejący plan S1–S3 |
| Powtarzalne wykonania | Izolowany trening i batch inference, limity zasobów, trwały stan prób, retry/cancel i pochodzenie wyniku | Istniejący plan S2–S4 |
| Kontrolowane dostarczanie | Ocena jakości, niezmienny pakiet wydania, niezależna zgoda, promocja między środowiskami i rollback | Istniejący plan S4–S5 |
| Codzienna eksploatacja | Logi i metryki powiązane z wykonaniem/wydaniem, alerty, instrukcje awaryjne, backup/restore, zużycie zasobów | W każdym przyroście; kwalifikacja środowiska w S6 |
| Predykcja online przez API | Wersjonowany kontrakt wejścia/wyjścia, autoryzacja, pomiary opóźnień i błędów, kontrola obciążenia | Rozszerzenie po sprawdzeniu ścieżki batch; osobna SPEC |
| Aplikacje LLM i agenci | Kontrolowane RAG, wywołania narzędzi, ewaluacja, śledzenie przebiegu i koszty | Osobny etap na wspólnym rdzeniu platformy |

Monitoring powinien rozróżniać zdrowie infrastruktury, poprawność wykonania
oraz jakość rozwiązania ML/AI. Sprawny endpoint nie dowodzi dobrej jakości
predykcji; ocenę jakości trzeba powiązać z dostępnymi wynikami rzeczywistymi
i uzgodnionym zbiorem oceny.

Data Scientist odpowiada za sens modelu i ocenę wyników. ML/AI Engineer
przygotowuje pipeline lub usługę. Platform Engineer zapewnia wspólne mechanizmy
uruchamiania, dostarczania i obserwacji. Recenzent oraz operator mają odrębne
uprawnienia do zatwierdzenia i wdrożenia konkretnego wydania. Mały zespół może
łączyć role, zachowując rozdział obowiązków wymagany dla danego procesu.

## Architektura i dobór technologii

Zachowujemy [proponowaną architekturę](architecture.md): modularny backend
sterowania, wspólny interfejs i osobne środowiska wykonawcze. Torii rozwija
własne kontrakty, wersjonowanie, uprawnienia, historię oraz doświadczenie
użytkownika; integruje gotowe mechanizmy przechowywania, tożsamości, trackingu
i obliczeń. Takie podejście odpowiada opisowi platformy jako produktu dla
wewnętrznych użytkowników w [CNCF Platforms White Paper](https://tag-app-delivery.cncf.io/whitepapers/platforms/).

Kubernetes jest mocnym kandydatem na docelowe środowisko wykonywania zadań
i usług, szczególnie przy firmowym klastrze oraz potrzebie wielu użytkowników
i limitów zasobów. Jego wybór powinien wynikać z topologii i możliwości
utrzymania. Dostarcza mechanizmy uruchamiania i skalowania kontenerów;
pozostawia dobór CI/CD, monitoringu i usług aplikacyjnych integratorowi.
[Dokumentacja Kubernetes](https://kubernetes.io/docs/concepts/overview/#what-kubernetes-is-not).

Lokalne demo nadal służy zbieraniu feedbacku. Próbę Kubernetes planujemy przy
kontrakcie adaptera wykonawczego i wyborze środowiska, zanim podejmiemy
zobowiązanie do konkretnego wdrożenia. Obecna decyzja D-06 o runnerze pozostaje
otwarta. [Kubeflow Pipelines](https://www.kubeflow.org/docs/components/pipelines/overview/)
może być ocenione jako narzędzie do kontenerowych pipeline'ów ML; wzmianka
w ofercie nie rozstrzyga jego przyjęcia. Nie wybieramy teraz dostawcy chmury.

## Pierwszy przekrój potwierdzający wartość

Proponowany scenariusz: **kontrolowane prognozowanie opóźnień dostaw na danych
syntetycznych**. Jest zgodny z przykładem w obecnej [roadmapie](roadmap.md).

1. Autor utrwala wersję danych, transformacji, kodu i środowiska, a następnie
   trenuje model oraz porównuje go z prostą regułą na wspólnym zbiorze oceny.
2. Recenzent otrzymuje wyniki i pochodzenie artefaktów, po czym zatwierdza
   konkretny, niezmienny pakiet. Autor nie zatwierdza własnego wydania.
3. Operator uruchamia zatwierdzony model wsadowo dla nowej, zapisanej wersji
   danych w odrębnym środowisku testowym. Widzi użyte wydanie i stan wykonania.
4. Kontrolowana awaria pozostawia czytelny błąd. Ponowienie nie publikuje
   podwójnego wyniku. Operator może przywrócić poprzednie wydanie.
5. Z dowolnego wyniku można wskazać rzeczywiste wejścia, kod, model, runtime,
   aktora i decyzję o wydaniu. Sprawdzamy odtworzenie oraz odmowę dostępu
   użytkownikowi innego projektu.

To cel obejmujący zależności S1–S5, a nie zakres jednego sprintu. Najbliższy
krok pozostaje mały: ręczny odbiór SPEC-0018 i zapis braków względem tego
scenariusza. Następnie planujemy domknięcie fundamentu S1 oraz najmniejszą
ścieżkę batch przez wymagane etapy. Ewentualne przesunięcie rozbudowanego Flow,
Jupyter czy dodatkowych konektorów wymaga jawnej aktualizacji planu i SPEC.

Odbiór powinien mierzyć czas od rozpoczęcia pracy do pierwszego poprawnego
runu, czas od kandydata do wdrożenia, kompletność pochodzenia wyników,
skuteczność odzyskania po awarii i zużycie zasobów. Progi ustalamy dla
konkretnego pilotażu. Liczba ekranów, bibliotek i modeli nie zastępuje tych
dowodów.

## Miejsce aplikacji LLM i agentów

Agenci powinni korzystać z tych samych projektów, uprawnień, wydań i historii,
z dodatkowymi kontraktami właściwymi dla AI. Wydanie musi identyfikować model
lub wersję usługi dostawcy, prompt, narzędzia, konfigurację retrieval oraz
dopuszczone źródła. Ewaluacja wymaga ustalonego zestawu przypadków, kryteriów
jakości i śladu wykonania z kontrolą dostępu oraz retencją.

Pierwszym kandydatem jest asystent wyjaśniający wyniki i nieudane wykonania
na podstawie dostępnych użytkownikowi metadanych. Dostęp do narzędzi nadaje
backend, a odczytane dokumenty nie rozszerzają tych uprawnień. Operacje
zmieniające stan wymagają jawnej polityki zgody, limitów czasu/kosztu i liczby
kroków. Zapis przebiegu pozwala wyjaśnić działanie; nie gwarantuje identycznej
odpowiedzi LLM przy powtórzeniu. Wybór frameworka nastąpi po tym kontrakcie.

## Granice tej propozycji

Nie deklarujemy dziś obsługi setek modeli, produkcyjnego SLA ani gotowości
regulacyjnej. Przed pilotażem trzeba wskazać proces biznesowy i jego właściciela,
wymagania danych, skalę, budżet, docelową infrastrukturę oraz odpowiedzialność
operacyjną. Pierwszy zakres pozostaje batch; online, GPU i agentic workflows
wymagają własnych kryteriów odbioru.

Notatka uzupełnia kierunek, bez nadawania statusu Accepted nowym rozszerzeniom.
Nie zmienia statusów SPEC, kolejności zatwierdzonych prac ani wstrzymanej
automatyzacji. Dalsza implementacja podlega [procesowi SDD](spec-driven-development.md).
