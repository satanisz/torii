# SPEC-0018 — ręcznie testowalny demonstrator Torii

2026-09-19. Status: Accepted (delegated), po niezależnym review contract_review
przed kodem, z czterema doprecyzowaniami poniżej. Nie odbiór enterprise.
Nowa dyspozycja użytkownika: działająca aplikacja do prezentacji konceptu,
nie pełny enterprise jako warunek demonstracji. Nie zalicza SP-01–15.

## Zakres i świadome uproszczenia

Osobny jawny entrypoint FastAPI `apps/demo`, React w `apps/web/demo.html`.
Nie zmieniamy ani nie obchodzimy zabezpieczeń `torii_api.app`. Lokalny operator,
bez kont/SSO/udostępniania firmowego. UI stale oznacza DEMO / lokalne / bez SSO.
Nowy katalog ignorowany `apps/demo/.local`, SQLite metadanych i osobny SQLite
MLflow/artifacts. Nie używamy legacy usług/wolumenów/root.env lub danych firmy.
Uruchomienie na127.0.0.1:18440, jeden proces. Host dokładnie127.0.0.1:18440 lub
localhost:18440; modyfikacje wymagają `X-Torii-Demo: 1` i jeśli obecny Origin
to dokładny własny origin. Brak CORS, no-store, request body max8MiB.
To ochrona przed drive-by stroną, nie uwierzytelnienie innych lokalnych procesów.
Nie wystawiać przez LAN/proxy/Internet. Startup jawnie --local-demo.

## Obiekty, wykonania, dane

SQLite: projects(id,name,created_at); objects(id,project_id,kind,name,created_at);
versions(id,object_id,number,definition JSON,payload JSON,sha256,created_at);
runs(id,project_id,model_version_id,dataset_version_id,status,result JSON,
error,created_at). Nie nadpisujemy versions; transakcja numeruje kolejne wersje.
Kind dataset/transformation/model/analysis. ID losowy UUID. Nazwy1..100.
Definicje deklaratywne, żadnego eval/exec/import kodu użytkownika ani pickle upload.
Payload tabeli jest snapshotem listy rekordów JSON; dane nie trafiają do Git.
Hash kanonicznego JSON identyfikuje zawartość; nie jest podpisem.
Lineage zawiera konkretne input_version_id, model_version_id, run_id.

Import CSV UTF-8 base64: max8MiB request,5000rows,50columns,
250000cells, unique nonempty column names<=100, wartości scalar JSON finite,
string<=2000. Brak arbitrary URL/path/SQL. Parquet odłożone.
Syntetyczny przykładowy dataset regresji dostępny bez sieci. Profil: typ,missing,unique,
min/max/mean dla numeric, preview20. Zero danych firmowych w testach.
Transformacja jako obiekt: drop_missing, drop_duplicates, select_columns,
filter_numeric(column,operator gte/lte,value). Execute tworzy nowy dataset
z lineage; nie zmienia input. Nie ma dowolnego Pythona w API.

Modele jako definicje: task regression, algorithm linear (Ridge,alpha0..100),
dummy (stała średnia train jako prosty benchmark nieuczący relacji).
Target,features listnumeric,seed42,test_size0.25. Modelregułowy później;
dummy nie przedstawiamy jako pełny edytor modeli nie-ML.
Train/test split przed preprocessing; median imputer fit tylko train; reproducible
random state. Bez tuningu/AutoGluon/GPU.
Minimum20rows; split deterministic.
Missing target odrzucamy, brak numericfeatures/all-empty trainfeature odrzucamy.
Regression R2/MAE/RMSE. Analiza: actual/predicted20rows oraz współczynniki Ridge
(po standardyzacji cech), jawnie nie przyczynowość, nie pełne XAI.
Zapis własnego modelu joblib, metryk i środowiska tylko we własnym run directory.
Prawdziwy MLflow3.14.0 lokalny tracking: params/metrics/artifacts, ID w wyniku.
Awaria tracking oznacza failedrun, nie udajemy successfulMLflow.

Wykonania w osobnym subprocess z tym samym zamrożonym Pythonem, timeout120s,
jeden aktywny run; API zwraca202 i UI polluje. Nie sandbox dowolnego kodu.
Status queued/running/succeeded/failed, restart oznacza osierocone jako failed.
Timeout/nonzero ma bezpieczny komunikat, nie rawtraceback wUI. Artefakty tylko
allowlist model.joblib/result.json/environment.json; żadnych pathargumentów.
Eksport JSON definicji+hashy+wyników bez payloadów danych/modeli do Git; nie jest
pełnym replaybundle. Osobno pobranie własnego modelu i danych CSV do testów.
Oznaczenie modelu jako candidate jest demonstracją build/experiment, nie production.
Brak przycisku udającego real deployment. Jupyter/SQL/Gitpush/współdzielenie później.

## Kontrakt HTTP /demo-api (osobny od enterprise OpenAPI)

JSON błędu {detail:string}, krótkie bezpieczne teksty. Pydantic extra=forbid.
- GET /state -> {projects:[],objects:[],runs:[],mode:"local-demo"}; object zawiera
  id,project_id,kind,name,versions:[{id,number,definition,sha256,created_at,summary}].
  summary dataset:{columns:string[],row_count,profile:[],preview:[]}; dla innych {}.
  Run:{id,project_id,model_version_id,dataset_version_id,status,result,error,created_at}.
- POST /projects {name} -> project201.
- POST /projects/{id}/sample -> dataset object201 (synthetic regression).
- POST /projects/{id}/datasets {name,format:"csv",content_base64,object_id?:uuid}
  -> object201; object_id tworzy wersję tylko własnego datasetu w tym projekcie.
- POST /projects/{id}/transformations {name,input_version_id,operation,columns?:[],
  column?:str,operator?:"gte"|"lte",value?:number} -> transformation object201.
- POST /transformations/{version_id}/execute {} -> output dataset object201.
- POST /projects/{id}/models {name,task:"regression",algorithm:"linear"|"dummy",target,features:string[],alpha?:number}
  -> model object201. Definicja obejmuje seed42 i test_size0.25 po stronie serwera.
- POST /projects/{id}/runs {model_version_id,dataset_version_id} -> run202;
  źródła w tym samym projekcie,409 gdy aktywne wykonanie.
- GET /runs/{id}/artifacts/{name} -> own file allowlist;404 gdy nie istnieje.
- GET /datasets/{version_id}/csv -> CSV snapshot (spreadsheet formula neutralized).
- GET /projects/{id}/export -> JSON definitions/hashes/results,bez danych/sekretów.

## AC / testy przed odbiorem demonstratora

D01: nowy projekt,synthetic/CSV import, błędy, preview/profile i immutable
wersje przetrwają restart; projektA nie może referować obiektówB.
D02: transformacja jako byt, wykonanie tworzy dataset,lineagewidoczny,oryginał bez zmian.
D03: model Ridge i baselineśredniej,real subprocess/run/MLflow ID/metryki/podziałtest; wyniki różnych
runów porównywalne w jednym UI, brak udawanych metryk; niepoprawnytargetczytelnyfailed.
D04: analiza/współczynniki i artifactdownload,export bez danych; trwałość po restarcie.
D05: GUI logo, projects/catalog/flow/experiments/result; forms,loading/error/empty,
responsywność,brak surowych HTML, stale demo warning i disabled enterprise claims.
D06: loopback/host/origin/header/body limits,brak dowolnego kodu/path,walidacja
negativeinputs,independentreview,regresja existingfoundation,realHTTP+browser smoke.
D07: launcher zapisuje zweryfikowany PID listenera także przy błędzie/timeout
readiness, niezależnie od odpowiedzi /state; Stop nadal weryfikuje własność.
Regresja: listener będący dzieckiem redirectora zostaje zapisany bez HTTP success;
obcy listener nie może zastąpić rekordu. Review: contract_review przed poprawką.
Jedno polecenie startu i instrukcja manualtest5–10min; zostawić działający
URL użytkownikowi. SDD/testy wymagane,enterpriseDR/securityqualification deferred.

Plan: spec+ADR/review -> engine/store/API/frontend równolegle -> integracja
realMLflow/subprocess -> browser/manualsmoke -> lokalnycommit i instrukcja.
Rollback: zatrzymanie własnego PID bez kasowania danych; enterpriseentrypoint
i legacy bez zmian. Zależności w osobnym uv.lock, frontend reuse existingdeps.

## Zawężenie przez użytkownika

Użytkownik pozwolił ograniczyć pracę. Pierwszy demo wyłącznie CSV/synthetic,
regresja Ridge i średnia, proste transformacje, porównanie metryk, współczynniki.
Parquet/SQL/Jupyter/multiuser/nonMLcustom/XAI/production odłożone jawnie.
Nie trzeba dokańczać pełnego enterpriseSSO żeby pokazać osobny lokalny koncept.

## Doprecyzowania niezależnego review przed implementacją

- Features niepuste, unikalne, istniejące; target nigdy wfeatures. Imputer median
  i StandardScaler fit wyłącznie train, później transform holdout.
- CSV comma UTF-8 (BOM dozwolony), empty→None; finite float→number, pozostały
  text zachowany. NaN/Inf/-Inf jako wartości liczbowe odrzucane, nie JSONNaN.
- TrackingURI generuje backend do własnego SQLite; artifactroot/runroot tylko
  we własnym katalogu, nigdy requestfield ani odziedziczony MLFLOW_TRACKING_URI.
- Eksport doGit OMIT predictions,preview,payload,coefficients/modelartifact;
  tylko definicje+hashy+metryki/environment/runID. Nie pełny replaybundle.
- Po sukcesie automatycznie tworzy się analysis object/version wskazujący run,
  model i dataset. Porównanie pokazuje datasetversion/target/split, ostrzega
  przy różnych danych; nie udaje rankingu metryk z różnych zbiorów.
- Błędy Pydantic krótkie bez odbijania content_base64; CSV export neutralizuje
  formuły także w nagłówkach i tekstach, bez zmiany poprawnych liczb.

## Zamrożone shape wewnętrzne i UI

Data = {columns:string[],rows:record[],row_count:number,profile:Profile[]}.
Profile = {name,dtype:"number"|"string"|"boolean"|"mixed"|"empty",missing,unique,
min:number|null,max:number|null,mean:number|null}. Summary dodaje preview pierwsze20.
Dataset definition={source:"csv"|"synthetic"|"transformation",input_version_id?:str,
transformation_version_id?:str}; transformation definition to pola request bezname.
Model definition to pola request bezname +seed42,test_size0.25,alpha default1.
Run result={metrics:{mae,rmse,r2},importance:[{feature,value}],
predictions:[{actual,predicted}],train_rows,test_rows,mlflow_run_id,algorithm,
environment:record}; importance to współczynniki Ridge, baseline empty[].
Przed sukcesem result=null (queued/running/failed); nie pusty obiekt udający wynik.
Run zwraca dodatkowo target,seed,test_size z definicji dla porównywania.
Worker job={data:Data,definition:ModelDefinition,run_dir:absolute internalpath,
tracking_uri:internal SQLite URI}; CLI python -m torii_demo.worker job.json,
zapisuje result.json/model.joblib/environment.json, nonzero przyfailure.
