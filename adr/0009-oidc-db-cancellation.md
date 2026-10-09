# ADR-0009 — anulowanie OIDC a synchroniczne transakcje bazy

2026-10-10. Status: **Accepted (delegated)** po niezależnym review
`regulated_examples` przed kodem; autor `platform_state`.
Zakres: [SPEC-0001 B2a4c](../specs/0001-project-object-version/increment-b2a4c.md),
SP01-04b. Nie zmienia jeszcze IdentityStore, middleware ani tras HTTP.

## Kontekst

IdentityStore wykonuje synchroniczne transakcje SQLAlchemy/psycopg. Jego metody
zwracają wynik dopiero po commit; może jednak wystąpić utrata potwierdzenia już
zatwierdzonego zapisu. Baza ma pool/connect/lock/statement timeouts, bez wspólnego
deadline całej transakcji. Przeniesienie metody do wątku chroni event loop,
ale cancellation coroutine nie dowodzi przerwania SQL lub rollback.

Callback musi zużyć flow przed HTTP i może wydać credential wyłącznie po
potwierdzonym zapisie zweryfikowanej sesji. Zakończenie requestu z porzuconym
wątkiem pozwoliłoby na nieśledzony późny commit i wyścig z zamykaniem engine.

## Decyzja

Zachować istniejące API store i uruchamiać całe metody poza event loopem,
przez prywatny helper serwisu OIDC. Ograniczyć równoczesne futures do4,
kontrolować deadline/cancellation przed startem, a rozpoczęty worker zawsze
zsynchronizować przez async join. Nie przekazywać Connection między wątkami.

Cancellation blokuje dalsze zwykłe etapy i wydanie credential. Nie przerywa
oczekiwania na wynik już rozpoczętej transakcji. Powtórny cancel nie porzuca
workera; błąd cleanup nie zastępuje CancelledError. Ochrona dotyczy tylko join,
nie całego callback lub HTTP. Nie ma background retry ani detached revoke.

Jeśli po deadline/cancel uzyskano znany wynik create_session, jedna lokalna
próba revoke usuwa wyłącznie tę nową sesję. Nie odtwarzamy starej sesji usuniętej
w atomowej rotacji. Gdy wynik COMMIT jest nieznany i credential nie wróciło,
nie zgadujemy rekordu do usunięcia; możliwy niewydany rekord wygasa według
istniejącego idle/absolute TTL. Nie deklarujemy wtedy pewnego rollback.

Sieć zachowuje wspólny work deadline i1s rezerwy cleanup. DB join/kompensacja
mogą przekroczyć15s. To jawne ograniczenie komponentu, nie hard timeout.
Lifecycle drenuje operacje/workery przed zamknięciem klientów i przed dispose
engine przez jego właściciela. Awaria lokalnego logout nie jest sukcesem;
po potwierdzonym DELETE awaria remote revoke nie odtwarza sesji.

## Alternatywy i konsekwencje

- Porzucenie wątku po asyncio timeout: odrzucone, bo pozostawia nieśledzony
  skutek transakcji i nie gwarantuje rollback.
- Synchroniczne DB na event loop: odrzucone, bo blokuje inne operacje/cancellation.
- Zmiana store na async driver lub zewnętrzny transaction deadline: odłożona;
  wymaga oddzielnego kontraktu anulowania, commit-unknown i testów bazy.
  Sama zmiana drivera nie usuwa niepewności utraconego potwierdzenia COMMIT.
- Trwały rejestr operacji/kompensacji: poza zakresem małej kompozycji; zmieniłby
  model i migracje. Nie obiecujemy jego gwarancji bez implementacji.

Przed podłączeniem HTTP B2b musi rozstrzygnąć współpracę z istniejącym
EnvelopeMiddleware i jego `asyncio.timeout(15)`. Obecny wrapper nie dowodzi
twardego terminu zakończenia DB. Wymagane testy: real PG, bariery commit/cancel,
późny znany commit i jego kompensacja, fault injection commit-unknown,
responsywność event loop i lifecycle bez porzuconych workerów.

Dokładne API, kolejność i AC są w B2a4c. Akceptacja pozwala na implementację
tego wewnętrznego komponentu; nie uruchamia usług i nie nadaje statusu Verified
całemu auth/SP-01. Nie zastępuje ludzkiego audytu ani odbioru enterprise.
