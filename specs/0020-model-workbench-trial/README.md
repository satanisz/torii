# SPEC-0020 — warsztat modeli, próba EXP-03a

Rewizja 0.2, 2026-10-10. Status: **Verified — lokalna próba techniczna**.
Wynik kwalifikacji bezpośredniej integracji enterprise: **NO-GO** (audyt niezakwalifikowany).
Dowody: [raport i macierz](evidence.md). To nie jest Verified całego EXP-03/SP-10.
Niezależny review ingress: `regulated_examples`, 2026-10-10, przed kodem.
Rewizja 0.1 Accepted (delegated), implementowana i testowana.
Owner: integrator Torii. Niezależny review przed kodem: agent
`regulated_examples`, 2026-10-10, bez blokerów. Akceptacja tylko lokalnego EXP-03a;
nie oznacza audytu człowieka ani kwalifikacji adaptera do produktu.
Mandat: użytkownik włączył Docker i zlecił skupienie na architekturze narzędzi
do tworzenia modeli. Techniczny review przed kodem wymagany zgodnie z AGENTS.md.
Powiązania: FR-01/06/08 z [wymagań](../../docs/platform/requirements.md)
oraz NFR-01/02/03/06 z [zasad jakości](../../docs/platform/security-and-quality.md)
w ograniczonym zakresie próby, nie pełny odbiór tych wymagań;
[EXP-03](../../docs/platform/sp-00-technical-trials.md),
[ADR-0007](../../adr/0007-model-workbench-trial.md).

## Pytanie i granice

Czy MLflow 3.14.0 może być adapterem warsztatu modeli: zapisać i odtworzyć
eksperyment oraz egzekwować dostęp do jego metadanych, modeli i artefaktów?
Limit: jedna sesja implementacji i prób do 4 godzin. Wynik negatywny dla ACL
jest dopuszczalnym wynikiem badania, ale blokuje kwalifikację adaptera do Torii.
Nie budujemy nowego UI ani nie zaliczamy całego EXP-03, SP-01 lub SP-10.

Zakres: osobna instalacja Docker Compose, PostgreSQL, MLflow z basic-auth,
magazyn S3 SeaweedFS, mały Caddy ingress oraz jednorazowe kontenery treningu
i testów kontraktowych. Ingress potrzebny, ponieważ Docker Desktop nie publikuje
portu serwisu należącego wyłącznie do sieci internal (sprawdzone w runtime).
MLflow experiments A/B reprezentują zasoby dwóch zespołów w teście; nie są
implementacją Torii Project ani dowodem zgodności jego ACL. Natywne konta
MLflow są tożsamościami technicznymi wyłącznie tej próby, nie docelowym SSO.
Domyślna polityka nowych zasobów ma być NO_PERMISSIONS dla pozostałych kont.

Model: syntetyczna miesięczna seria finansowa, cel prognozy jawnie zdefiniowany
w przykładzie, chronologiczny podział trening/test, porównanie prostej regresji
z baseline. To ćwiczenie kontraktu ML, nie model NII ani rekomendacja finansowa.
Model regułowy bez fit testowany jako wersjonowany artefakt JSON.

## Kontrakt infrastruktury i danych

- Nowy Compose project `torii-exp03-<12 znaków hex>`, własne wolumeny/sieci
  z etykietą `io.torii.scope=exp03`. Jawne compose file, env file i project directory.
- Nie czytać root `.env`, nie zmieniać istniejących usług, obrazów ani wolumenów.
  Brak komend globalnego cleanup; stop tylko bieżącej własnej instancji, bez delete.
- Caddy wystawia MLflow na sprawdzonym porcie loopback (domyślnie 18500).
  PostgreSQL/S3/MLflow bez publikowanych portów. Worker tylko sieć API;
  backend storage na osobnej sieci. Tylko zaufany Caddy łączy sieć ingress
  z siecią API; nie ma sekretów, magazynu danych ani kodu użytkownika.
- Maksymalnie 4 CPU i 4 GiB łącznie w jednocześnie działających nowych usługach
  (trening i testy uruchamiane sekwencyjnie). Brak Docker socket i host workspace
  w kontenerach. Kod w obrazie; worker/MLflow/DB/S3 bez Internetu.
  Ingress ma routowalną sieć Docker potrzebną do publikacji loopback, bez
  otwartego proxy i bez odbioru dowolnego celu od klienta.
- Sekrety losowe w ignorowanym katalogu instancji z ograniczonym ACL Windows,
  osobne pliki admin/A/B/S3/DB. Brak sekretów w argv, raportach i repozytorium.
  Worker otrzymuje tylko konto A; test harness konta A/B/admin, nigdy klucze S3/DB.
- Tracking i auth mają trwały PostgreSQL; artefakty przechodzą przez MLflow proxy
  do S3. Klient treningowy nie otrzymuje klucza ani bezpośredniego adresu S3.
- Obrazy bazowe przypięte digestem, biblioteki lockiem; raport zapisuje image ID
  z uruchomionej instancji, wersje pakietów i SHA-256 wejść/kodu/artefaktów.
- Manifest pochodzenia wiąże dataset bytes → transform code → split → run →
  parametry/metryki → model/predykcje. To dostarczone wejścia i zapis wykonania,
  nie dowód pełnej obserwacji odczytów ani niezmienności snapshotu (EXP-02 osobno).
- Ponowne wykonanie ma nowy run ID; porównuje hash danych/predykcji i metryki
  w tym samym przypiętym obrazie. Nie deklaruje bitowej zgodności serializacji modelu.

## Kryteria odbioru

| AC | Obserwowalny wynik i dowód |
|---|---|
| AC-01 | Provision/check/up/status/stop używają tylko nowych zasobów; brak host portów DB/S3/MLflow, socketów, starych wolumenów oraz sekretów DB/S3/admin w workerze. Tylko Caddy publikuje loopback; odpowiedź API bez tożsamości odrzucona. Inspekcja konfiguracji/runtime. |
| AC-02 | Rzeczywisty trening baseline i regresji zapisuje params, metrics, dataset digest, kod, model, predykcje i manifest w MLflow/S3. Pobranie przez SDK weryfikuje digest. |
| AC-03 | Drugie wykonanie w tym samym obrazie odtwarza predykcje i metryki; zmiana danych daje inny digest. Restart MLflow/DB/S3 zachowuje wcześniejsze runy i artefakty. |
| AC-04 | Macierz A/B obejmuje własne i obce list/search/get/mutation runów, upload/download/list artefaktów (SDK i znany URI), model registration/version/alias, anonimowy dostęp, grant READ i jego cofnięcie z ponowieniem. Każdy wynik PASS/FAIL/UNSUPPORTED/NOT TESTED; brak dowodu nigdy nie oznacza PASS. |
| AC-05 | Test modelu bez fit oraz jawna lista wspieranych metod i ograniczeń. Ocena audytu natywnego MLflow; brak audytu oznacza NO-GO dla bezpośredniej integracji enterprise. |
| AC-06 | Zapisane komendy, czasy/wersje/ID obrazów, wyniki, instrukcja powtórzenia i mapa następnych sprintów. Niezależny przegląd zmian. |

Ustalenia review: search/list sprawdzają treść; READ wyklucza zapis; revoke
obejmuje faktyczny download. JSON bez fit testuje artefakt, nie ogólny runtime.

AC-04/05 wymagają wykonania i rzetelnego sklasyfikowania prób, nie arbitralnego
uzyskania samych pozytywnych odpowiedzi. Każdy nieautoryzowany sukces lub luka
w pokryciu ogranicza decyzję go/no-go; nie poprawiamy testu, aby zalegalizować błąd.

## Plan, awarie i wycofanie

1. Przegląd specyfikacji i ADR; sprawdzenie dokładnych wersji i API dostawców.
2. Izolowany Compose, provision/runner, lock zależności, entrypoint usług.
3. Harness dostępu i przykładowy trening z manifestem, bez integracji z UI Torii.
4. Uruchomienie na syntetycznych danych, próba odtworzenia i restartu, review.
5. Raport decyzji i aktualizacja dziennika/roadmapy.

Awaria startu przerywa próbę; nie wyłącza cudzych usług i nie resetuje baz.
Po częściowym uruchomieniu status pokazuje własne kontenery; stop zachowuje dane.
Provision odmawia nadpisania istniejącej instancji. Ponowne testy tworzą nowe nazwy
zasobów w tej samej instancji. Nie jest to migracja danych produktu ani kwalifikacja DR.

Ograniczenia: lokalny HTTP na loopback/prywatnych sieciach, konta basic-auth,
wspólny serwis artefaktów, pojedyncze węzły. Brak SSO Torii, niezależnego audytu,
HA, WORM, zatwierdzeń modeli, integracji katalogu/grafu i kwalifikacji bankowej.
Ryzyka te blokują użycie poza tą syntetyczną próbą, nie jej wykonanie.
