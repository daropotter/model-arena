# Kalibracja zadania 4

Kalibracja z 2026-10-05: `opencode-go/deepseek-v4.1-flash` rozwiązał zadanie
w jednej autonomicznej sesji trwającej **205,183 s (około 3 min 25 s)**.
Po korekcie błędu gradera wynik to **19/19 kryteriów**, a testy napisane
przez model wykryły **7/7 mutacji odpowiedzi**. Model poprawił właściwą
instancję, zachował zachowanie pozostałych i wdrożył przetestowaną paczkę.

To jedna próba jednego modelu, bez ponagleń człowieka ani ponownego
uruchomienia modelu po korekcie oceny. Nie określa rankingu ani pass rate.
Pełne rozwiązanie w tym czasie oznacza, że ta kalibracja **nie potwierdza
jeszcze zdolności zadania do rozróżniania czołówki modeli**.

## Przebieg modelowy i korekta oceny

Artefakty:
[`20261005-223511-6c7928__export-forensics__opencode-go_deepseek-v4.1-flash`](../../results-frontier/20261005-223511-6c7928__export-forensics__opencode-go_deepseek-v4.1-flash/).

| Ocena tego samego rozwiązania | Wynik | Znaczenie |
|---|---:|---|
| Pierwotny `grade.json` | 18/19 | D05 odrzucił listę cytowanych plików |
| Zamrożony grader, `grade.rechecked.json` | 18/19 | Odtworzenie pierwotnej oceny |
| Poprawiony grader, `grade.current.json` | 19/19 | Usunięty nieudokumentowany wymóg cytowania |

Pierwotny D05 wymagał dokładnego zestawu sześciu kanonicznych ścieżek
w `evidence_files`, chociaż dokumentacja nie narzucała takiej listy.
Model poprawnie wskazał pola łańcucha, źródło i mechanizm błędu oraz
przeprowadził eksperyment, lecz zacytował inny zestaw istniejących dokumentów.
Był to błąd autora gradera, nie brak naprawy ani błędna diagnoza modelu.

D05 sprawdza teraz istnienie cytowanych plików, właściwe źródło przyczyny,
opis mechanizmu oraz poprawność D01–D04. Przy przeglądzie usunięto też z D06
wymóg dosłownego wystąpienia identyfikatorów zgłoszenia i odbiorcy w opisie
przekazania; nadal wymagane są rzeczywisty review, opis przekazania i
poprawne zachowanie partnera. W tym przebiegu D06 już wcześniej przechodził.

Prompt, starter, wymagania, rozwiązanie modelu i audyt pozostały bez zmian.
Pierwotne `grade.json` i `record.json` są zachowane. `record.regraded.json`
zawiera osobne `grading_revision` z hashami starego i nowego gradera oraz
tego samego audytu. Ponowna ocena zamrożonym graderem odtworzyła 18/19;
19/19 pochodzi z jawnej rewizji gradera.

Sesja obejmowała 40 kroków modelu, 72 wywołania narzędzi i 2 błędy narzędzi.
Audyt konsoli zawiera 4 buildy, 3 review, 4 operacje testowania, 1 deploy,
4 zapytania do eksportu i 2 odczyty statusu. Jedną próbę testowania
odrzucono z powodu nieaktualnych źródeł/testów. Inny test kończył się kodem 0,
ale nie wykonał żadnego zapytania — także nie został zaliczony. Model
przywrócił rzeczywiste testy, zbudował i sprawdził końcowego kandydata.

## Kontrole gradera

Po korekcie wykonano ponownie wszystkie **12 kontroli integracyjnych**:
dwa poprawne warianty oraz dziesięć celowo błędnych. `--verify-all`
zakończyło się kodem 0 i `verification_failures: []`.

| Wariant | Kryteria zaliczone | Oczekiwany rezultat kontroli |
|---|---:|---|
| reference | 19/19 | Pełne zaliczenie, 7/7 mutacji |
| equivalent | 19/19 | Pełne zaliczenie, 7/7 mutacji |
| noop | 4/19 | Brak naprawy, diagnozy i testów |
| wrong-host | 9/19 | Naprawiona niewłaściwa instancja |
| dead-copy | 11/19 | Zmiana nieużywanej kopii |
| generated-only | 11/19 | Zmiana wyłącznie pliku wygenerowanego |
| global-fix | 12/19 | Regresja kontraktu partnera |
| no-tests | 14/19 | Brak testów agenta |
| shallow-tests | 18/19 | Testy HTTP 200 wykrywają 0/7 mutacji |
| stale-tests | 17/19 | Brak aktualnych dowodów testowania |
| fake-report | 17/19 | Raport cytuje nieprawdziwe potwierdzenia |
| skip-review | 16/19 | Pominięty przegląd zgodności |

`equivalent` naprawia aktywny entrypoint zamiast wspólnego pakietu,
dodatkowo edytuje nieużywany plik, cytuje tylko dwa poprawne dokumenty
i używa polskiego opisu przekazania bez wymaganych wcześniej słów.
Pełny wynik potwierdza, że miejsce równoważnej poprawki, liczba zmian
i dosłowna forma raportu nie decydują o sukcesie.

Aktualne wyniki z przebiegów `20261005-224041`–`20261005-224130`:
[`summary.json`](../../results-frontier/export-forensics-validation/summary.json).
Pierwsze kontrole sprzed korekty zachowano w
[`summary.initial.json`](../../results-frontier/export-forensics-validation/summary.initial.json).

## Sprawdzenia integracji

Przeszło 6 testów autorstwa zadania: profil instrukcji, dwuwyrazowy prompt,
łańcuch zamiaru, odrzucanie niejednoznacznych danych i znaczenie mutacji.
Przeszło też 7 testów wcześniejszych zadań returns oraz 8 testów protokołu
obserwacji, kontrola składni shella i kompilacja Pythona.

Wzorzec wcześniejszego `returns-release` zachował **36/36** w rzeczywistym
przebiegu kontenerowym
[`20261005-223621-f090b8__returns-release__reference`](../../results-frontier/20261005-223621-f090b8__returns-release__reference/).
Wyników wcześniejszych benchmarków nie zmieniono.
