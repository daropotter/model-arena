# Distributed returns — trudniejszy wariant end to end

Oddzielny benchmark po zbyt łatwym [Returns release v1](../returns-release/README.md).
**48 etapów, 11 grup testów, 9 scenariuszy użytkownika, ścieżka zależności 33.**
Suite: `model-arena-frontier-returns-distributed-v2`.
Wyników v1 nie nadpisujemy. [Kalibracja i kontrole](CALIBRATION.md).

**Pierwsza kalibracja:** DeepSeek v4.1 Flash uzyskał 48/48 w 740,176 s
(12 min 20 s), ze wszystkimi zależnościami i aktualnymi testami. To około
1,90× czasu v1, ale nadal pełne zaliczenie — nie mamy jeszcze potwierdzenia,
że ten wariant skutecznie rozróżnia czołówkę modeli.

## Co zwiększa trudność

| Właściwość | Returns release v1 | Distributed returns v2 |
|---|---|---|
| Wydawany produkt | jedna paczka Python | API, osobny worker, klient Node, kontrakt dostawcy |
| Rozliczenie | jedna transakcja SQLite | trwała kolejka i niezależna księga dostawcy |
| Awarie | restart, równoległe API | utrata odpowiedzi po zapłacie, SIGKILL, wygasanie lease, spóźniony worker, współbieżne wypłaty |
| Ponowienia | idempotentne HTTP | backoff, dead-letter, ręczne wznowienie bez zmiany kwoty i klucza |
| Klienci | stary i nowy Python | dodatkowy Node, pełna paginacja, kursor związany z tożsamością i migawką |
| Późna zmiana | poprawki według potrzeb | obowiązkowe ABI1→ABI2 przy już opłaconym i oczekującym zwrocie |
| Dowody | 8 grup dla finalnej paczki | 11 grup przed zmianą integracji i 11 po niej |
| Rollback | kod + zachowana baza | kod + zachowana baza i niezależna księga płatności |

Agent nadal dostaje wykonalne, jawne kontrakty; dane są małe. Trudność bierze
się z długości pracy i zależności między składnikami. Nie wymagamy 48 osobnych
edycji, narzuconej architektury ani określonej liczby wywołań modelu.
„Jedna sesja” dopuszcza narzędzia, notatki, retry i kompresję kontekstu,
bez ponagleń człowieka.

## Wydanie w dwóch fazach

Pierwsza paczka rzeczywiście działa z protokołem płatności 1, schematem 2
oraz ABI1 w API, workerze i Node. Po komplecie testów i wdrożeniu `handoff`
przeprowadza jeden zwrot, kolejny zostawia w kolejce i przełącza dostawcę.
Wydaje kontrakt ABI2 związany z pierwszą paczką. Oba formaty HTTP są opisane
od początku; nie karzemy za przygotowanie obu adapterów zawczasu.
Późniejsze aktywowanie ABI2 wymaga zmienionych źródeł i komponentów.

Agent buduje ABI2, przeprowadza wszystkie testy ponownie, migruje istniejącą
bazę do wersji 3 i rozlicza starą kolejkę przez nowy adapter. Jej kwoty i
klucze muszą pozostać takie same. Następnie checkpoint obu ksiąg, prawdziwy
rollback do pierwotnego programu zamówień, stary klient, ponowne wdrożenie
ABI2 i smoke na zachowanych danych. Operacje nie wykonują całego wydania
za agenta. Każdą z nich trzeba świadomie wywołać.

Pełne kontrakty: [SPEC](starter/SPEC.md), [DISTRIBUTED](starter/DISTRIBUTED.md),
[RELEASE](starter/RELEASE.md), [48 etapów](starter/STAGES.md), [prompt](prompt.md).

## Ocena działającego produktu

`build.py` dostarcza `orders.pyz`, `worker.pyz`, `refunds.mjs` oraz
`payment-contract.json`. Każdy z tych plików trafia do prywatnej paczki z
zachowanymi bajtami i skrótami. Procesy uruchamiane są z gotowych artefaktów
bez checkoutu. Ocena nie importuje kodu rozwiązania. Dostawca płatności to
osobny serwer HTTP kontrolowany przez grader, z własnym stanem; aplikacja
nie może potwierdzić wypłaty przez edycję raportu ani wyzerować jego księgi.

Zabicie workera następuje po rzeczywistym przyjęciu żądania przez dostawcę,
a przed odpowiedzią i lokalnym potwierdzeniem. Osobny scenariusz pozwala
nowszemu workerowi zakończyć pracę, a dopiero potem zwalnia odpowiedź dla
starego właściciela. Jego spóźniony zapis nie może powielić audytu ani zmienić
stanu. W trakcie zablokowanego HTTP niezależny zapis API musi się udać.

35 publicznych scenariuszy funkcjonalnych (34 etapy, dwa warianty S30),
40 końcowych scenariuszy po dodaniu wariantów danych. Każdy może wykonywać
wiele żądań i asercji. 14 pozostałych etapów mierzy historię wydania i raporty.
Weryfikacje są związane z całością `src/`, `client/`, `config/`, `build.py`
oraz bajtami wszystkich komponentów. Końcowy grader ponownie buduje checkout.
Zielony test sprzed ostatniej zmiany nie wystarcza.

`score = completed_stages / 48`; pełne zaliczenie wymaga 48/48. Dodatkowo:

- `longest_valid_chain / max_chain`: maksymalnie 33; wszystkie zależności
  węzła muszą przejść, także pozostałe gałęzie przy połączeniu.
- `dependency_complete`, `blocked`: etapy ze wszystkimi zależnościami i
  etapy działające osobno, ale z niespełnionym poprzednikiem.
- `user_scenarios`: 9 wyników obejmujących klienta, częściowe zwroty,
  odrzucenie/anulowanie, współbieżność, uprawnienia, klientów/księgowość,
  odzyskiwanie po awarii dostawcy, późną integrację i trwałe wydanie.
- `final_artifact_verified`: odbudowana finalna paczka z pełnym aktualnym
  kompletem potwierdzeń ABI2.

Wysoki procent przy przerwanej ścieżce nie oznacza wydanego produktu.
Wyniki są w `grade.json` i `record.json.task_metrics`. Graf: [requirements.json](requirements.json).

## Uruchomienie

Linux, Docker, `/dev/fuse`, obraz `model-arena-observed` z Node 22 i Pythonem.
Kontrole działają bez sieci. Próba modelowa potrzebuje tylko jego API.

```bash
python3 runner/frontier.py --task returns-distributed --verify --timeout 600
python3 runner/frontier.py --task returns-distributed --verify-all --timeout 600
python3 runner/frontier.py --task returns-distributed \
  --model opencode-go/deepseek-v4.1-flash --timeout 7200
python3 runner/frontier.py --regrade results-frontier/RUN
```

13 negatywnych kontroli: noop, no-worker, duplicate-charge, ignore-lease,
lost-pending, old-wire, stale-client, stale-checks, skip-handoff, no-rollback,
wrong-cursor, fake-manifest, unfenced-worker. Każda ma wskazane etapy, które
musi oblać. Kontrola equivalent zachowuje kontrakt przy innym formatowaniu
podpisywanego JSON i dodatkowym polu diagnostycznym klienta; powinna mieć 100%.
Kontrole prowadzą cały przebieg przez te same operacje co model.

Ten benchmark mierzy implementację i doprowadzenie lokalnego wydania do końca.
Mały Python/SQLite i jawna lista kontrolna nadal upraszczają zadanie względem
prawdziwego monorepo. Numer schematu i deklaracje ABI są celowymi punktami
aktywacji wydania; nie zastępują testów zachowania. Nie jest to pełny audyt
bezpieczeństwa złośliwego kodu ani produkcyjny system płatniczy. Jedna próba
modelowa nie wyznacza rankingu, wariancji ani pass rate.
