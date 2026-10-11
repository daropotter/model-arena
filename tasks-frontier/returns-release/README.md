# Returns release — długie zadanie end to end

Drugi kierunek testów frontier: pełne lokalne wydanie zwrotów w istniejącym
systemie zamówień. **36 etapów odbioru**, 8 grup weryfikacji i 7 scenariuszy
użytkownika. Jedna autonomiczna sesja od promptu do końca; wywołania modelu,
notatki, ponowienia i kompresja kontekstu należą do tej samej sesji.
Suite ID: `model-arena-frontier-returns-release-v1`.

**Kalibracja:** DeepSeek v4.1 Flash ukończył 36/36 etapów, ścieżkę 26/26
i 7/7 scenariuszy w 390,586 s. Wariant nadal okazał się łatwy dla tego
modelu. [Wynik, dowody i ograniczenia](CALIBRATION.md).

Trudniejszy, odrębny wariant: [Distributed returns v2](../returns-distributed/README.md)
(48 etapów, osobny worker, klient Node i obowiązkowa późna zmiana integracji).

Nie wymagamy 36 osobnych edycji ani konkretnej liczby wywołań narzędzi.
To mierzalne etapy dostarczenia produktu. Agent może realizować je w swoim
porządku, grupować pracę i wracać do poprawek. Graf zależności opisuje
kompletność wydania, nie nakazaną kolejność pisania kodu.

## Produkt i zakres

Starter to działający serwis zamówień w Pythonie z SQLite i starym
konsumentem API. Budowanie pakuje `src/` do deterministycznego ZIP executable
`dist/orders.pyz`. Wszystko działa offline na standardowej bibliotece.

Nowa funkcja wymaga migracji v1→v2, częściowych zwrotów, rezerwacji ilości,
idempotencji, obsługi równoległości, przejść stanów, uprawnień i izolacji
tenantów, aktualizacji magazynu, dokładnego rozliczania groszy, księgi
zwrotów, audytu, CSV, flagi funkcji i klienta HTTP w tej samej paczce.
Stary klient oraz odpowiedź `/v1/orders/ID` mają pozostać zgodne.

Ostatnia część zadania to zbudowanie końcowego wydania, osiem kompletnych
weryfikacji, uruchomienie usługi, rzeczywisty zwrot klient→support→magazyn→
finanse, checkpoint danych, rollback kodu do oryginalnej aplikacji,
sprawdzenie starego klienta, ponowne wdrożenie i odczyt zachowanych danych.
Rollback nie może usuwać rozliczonych zwrotów ani cofać magazynu.

Pełny [prompt](prompt.md), [kontrakt funkcji](starter/SPEC.md),
[procedura wydania](starter/RELEASE.md) i [36 etapów](starter/STAGES.md)
są dostępne przed rozpoczęciem pracy. Dane są małe; to nie test dużego
korpusu ani zapamiętywania ukrytych obowiązków z poprzedniego wariantu.

## Co naprawdę sprawdza grader

`arena-ops build` kopiuje bieżące wejścia do prywatnej migawki i uruchamia
projektowe `build.py` jako UID 1001. Serwer i CLI startują wyłącznie z gotowej
paczki w osobnym katalogu, bez checkoutu i bez PYTHONPATH. Grader wysyła
HTTP i odczytuje skutki w SQLite; nie importuje kodu rozwiązania.
W repozytorium jest jawnie oznaczony niepakowany `prototypes/returns.py`.
Naprawienie tylko jego nie daje zaliczenia nowej funkcji.

Każde potwierdzenie weryfikacji zawiera identyfikator kandydata, SHA-256
artefaktu oraz skrót całego `src/` i `build.py`. Końcowa ocena ponownie
buduje submission i porównuje rzeczywiste bajty z wdrożonym produktem.
Zmiana po testach wymaga nowej paczki i nowych potwierdzeń. Dokładna kopia
artefaktu jest zachowana w prywatnym audycie, więc regrade nie odtwarza
historii z deklaracji ani z końcowych źródeł.

`deploy`, `rollback` i ponowny `deploy` naprawdę zatrzymują i uruchamiają
proces HTTP na tej samej bazie. Operacje oraz końcowy odczyt stanu zapisuje
zaufany supervisor. Po zakończeniu sesji procesy są sprzątane. Lokalna
usługa nie jest publikowana w sieci. Model działa jako UID 1000, aplikacja
jako UID 1001; socket operacji odrzuca żądania aplikacji. Supervisor ma
CAP_KILL do zatrzymywania procesów innego UID; aplikacja nie dostaje tej
capability. FUSE, ograniczenia kontenera i wyłączenie indeksatora OpenCode
są wspólne z [Dispatch](../dispatch-migration/README.md).

Publiczne grupy obejmują 24 etapy funkcjonalne. Końcowa ocena używa 29
scenariuszy, w tym wariantów kwot i dodatkowego zamówienia/SKU/waluty;
pojedynczy scenariusz wykonuje zwykle wiele żądań i asercji. Pozostałe
12 etapów dotyczy faktycznej historii wydania i końcowych raportów.
Zestaw nie jest dowodem odporności na wszystkie błędy domenowe lub
celowo złośliwą aplikację; to kontrolowany benchmark dostarczenia funkcji.

## Punktacja

Główny `score = completed_stages / 36`. Publikujemy także:

- `longest_valid_chain / max_chain`: długość najdłuższej ukończonej ścieżki
  w grafie, maksymalnie 26. Węzeł jest uznany za ukończony w tym pomiarze
  tylko wtedy, gdy sam przeszedł i WSZYSCY jego poprzednicy również przeszli.
  Nie można ominąć niedziałającej gałęzi przy połączeniu zależności.
- `dependency_complete`: liczba etapów z kompletem zależności; `blocked`
  wskazuje działające osobno etapy z brakującym poprzednikiem.
- `user_scenarios`: 7 wyników — pełny zwrot, częściowe zwroty, anulowanie/
  odrzucenie, równoległe ponowienia, uprawnienia, klient/księgowość,
  trwałe wydanie z rollbackiem.
- `final_artifact_verified`: finalny build odpowiada źródłom i ma komplet
  aktualnych potwierdzeń; to odrębne od wyniku ukrytych scenariuszy produktu.

`passed` wymaga wszystkich 36 etapów. Sam wysoki procent nie oznacza
ukończonego wydania: np. brak rollbacku zostawia wiele działających funkcji,
ale przerywa ścieżkę wydania. Metryki są w `grade.json` i
`record.json.task_metrics`. Graf jest jawny w [requirements.json](requirements.json).

## Uruchomienie i kontrole

Wymagania: Linux, Docker, `/dev/fuse`, obraz `model-arena-observed`.
Z głównego katalogu repozytorium:

```bash
python3 runner/frontier.py --task returns-release --verify --timeout 300
python3 runner/frontier.py --task returns-release --verify-all --timeout 300
python3 runner/frontier.py --task returns-release \
  --model opencode-go/deepseek-v4.1-flash --timeout 7200
python3 runner/frontier.py --regrade results-frontier/RUN
```

Wzorzec wykonuje całą procedurę przez prawdziwy serwis. Negatywne kontrole:
`noop`, `dead-code`, `stale-build`, `stale-check`, `no-rollback`,
`fake-report`, `broken-client`, `duplicate-refund`, `lost-state`.
Każda musi odpaść na określonych etapach, nie tylko uzyskać wynik poniżej 100%.
Test jednostkowy grafu sprawdza blokowanie węzła przez brak jednej z gałęzi,
a test socketu — odrzucanie operacji zgłoszonych przez UID aplikacji.

Próby modelowe korzystają z zamrożonego startera, promptu, runnera i gradera.
Wyniki tej serii są niezależne od zwykłego sweepu i od Dispatch/Minefield.
