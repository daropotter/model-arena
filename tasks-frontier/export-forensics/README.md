# Napraw eksport — zadanie 4

Prompt modelu to dokładnie **„Napraw eksport”**. Osobny profil instrukcji
`forensics` nie wskazuje SPEC.md, zgłoszeń, domen, manifestów ani kodu do edycji.
Instrukcje utrzymania są zwykłymi plikami repozytorium; model musi je odnaleźć.
Suite: `model-arena-frontier-export-forensics-v1`.

## Zamiar i dowody

Bieżąca kolejka wskazuje jedno otwarte zgłoszenie. Jego dokładna domena prowadzi
przez konfigurację wirtualnych hostów do instancji, manifestu budowania,
entrypointu i wybranej wersji wspólnego pakietu. To łańcuch:

```text
.desk/current.json → kolejka → INC-482 → raporty.novara.test
→ wk-a73 → builds/settlement-r7.json → services/settlement-http/app.py
→ shared/tabular/r4/records/project.py
```

W repozytorium są też stare README, podobna domena `raporty-novara.test`,
zamknięte zgłoszenia, wcześniejsza wersja pakietu, snapshot, plik wygenerowany
oraz oczywisty błąd w nieużywanym eksporterze. Bieżąca konfiguracja i marker
kolejki rozstrzygają te sprzeczności. Zmiana starej kopii nie naprawia produktu.

Właściwy problem: wspólna projekcja odrzuca wartości falsy przed zapisaniem
wiersza CSV. Puste pola znikają, a kolejne kolumny przesuwają się; giną również
0 i false. UTF-8 i BOM są poprawne. Wiarygodna hipoteza ze zgłoszenia wskazuje
kodowanie znane z wcześniejszego incydentu, lecz surowa odpowiedź ją podważa.

Trzy lokalne instancje to realne procesy HTTP uruchomione z oddzielnych ZIP
executables, bez checkoutu serwera. Przed sesją działa pierwotna wersja.
Konsola i bramka HTTP zapisują rzeczywiste eksperymenty. Model może użyć
konsoli lub POST /dispatch pod adresem z .runtime/environment.json.

## Późny wyjątek

Przegląd zgodności kandydata ujawnia umowę odbiorcy `importer-r12`: jego sparse
feed celowo pomija wartości falsy. Globalne „naprawienie” wspólnego pakietu
psuje ten kontrakt. Poprawka, testy i raport muszą uwzględnić wyjątek.
Przegląd jest przypięty do kandydata i zapisywany w zaufanym audycie.

Agent, który wcześniej przewidział kompatybilność, nie musi wykonywać
sztucznej dodatkowej edycji. Musi jednak po przeglądzie ponowić testy finalnej
paczki. Nie karzemy za dobrą architekturę ani wczesne zebranie dowodów.

## Ocena

19 kryteriów: 8 produktu, 6 diagnozy, 5 weryfikacji. `score` to ich odsetek;
pełne zaliczenie wymaga wszystkich. Liczba edytowanych plików nie ma znaczenia.
Grader ponownie buduje końcowy checkout i sprawdza bajty aktywnego wydania.
Weryfikuje również, czy pliki wskazane przez manifest faktycznie weszły do
paczki. 14 scenariuszy HTTP obejmuje właściwy eksport, granice kontraktu
oraz obie pozostałe instancje.

Raport diagnozy wiąże zgłoszenie, domenę, instancję, manifest, rzeczywiste
źródła i dokumenty. Odrzucenie hipotezy kodowania musi mieć zapis eksperymentu
na pierwotnej usłudze: wadliwy układ pól przy zachowanym Unicode i BOM.
Nie oceniamy ukrytego toku rozumowania ani kolejności otwierania plików.

Testy napisane przez agenta (`tests_extra/run.py`) działają tylko przez HTTP.
Po czystym przebiegu uruchamiamy je z siedmioma niezależnymi mutacjami
odpowiedzi: usuniętym pustym polem, zgubionym zerem, zgubionym false,
uszkodzonym cytowaniem, Unicode, kolejnością pól i kompatybilnością partnera.
To **mutacje odpowiedzi usługi**, niezależne od struktury kodu rozwiązania;
nie są mutacjami AST. Nie dostarczamy testom identyfikatora aktywnej mutacji.

Mutacja liczy się jako wykryta tylko gdy czysty przebieg przeszedł, test
otrzymał faktycznie zmienioną odpowiedź, a następnie zakończył się błędem.
Brak właściwego przypadku wejściowego, timeout i sygnał zabijający proces
nie są wykryciem. Osobno raportujemy `mutation_detection` (0–7),
`correct_instance`, `evidence_chain` i `final_artifact_verified`.

Raport strukturalny musi cytować rzeczywiście wykonane testy na końcowych
źródłach i paczce, po review, oraz testy wszystkich trzech hostów. Grader
sprawdza te konkretne deklaracje; nie jest ogólnym semantycznym sędzią każdej
frazy w swobodnym tekście odpowiedzi modelu. Wnioski tekstowe są zachowane
w artefaktach do przeglądu.

## Uczciwość i ograniczenia

Kanoniczny marker wskazuje jedną aktywną sprawę; pozostałe zgłoszenia są
zamknięte lub kolejki archiwalne. Test autorstwa sprawdza jednoznaczność
łańcucha i brak wskazówek w profilu harnessu. Wykryta niejednoznaczność
markera jest błędem danych zadania wymagającym wyjaśnienia, nie porażką
modelu. Neutralny profil pozwala pytać, jeśli dowody naprawdę dopuszczają
różne interpretacje. Ten wariant nie zawiera osobnej interaktywnej rundy
oceniającej treść pytania w celowo niejednoznacznym środowisku.

Rozwiązanie funkcjonalne może być małe — trudność dotyczy ustalenia miejsca,
zakresu i weryfikacji poprawki. Checklistę zamknięcia incydentu można znaleźć
w dokumentacji firmy, lecz nie dostaje się jej w promptcie. Benchmark nie
jest audytem przeciw dowolnemu celowo złośliwemu kodowi.

## Uruchomienie

```bash
python3 runner/frontier.py --task export-forensics --verify --timeout 300
python3 runner/frontier.py --task export-forensics --verify-all --timeout 300
python3 runner/frontier.py --task export-forensics \
  --model opencode-go/deepseek-v4.1-flash --timeout 7200
python3 runner/frontier.py --regrade results-frontier/RUN
```

Domyślny profil pozostałych zadań pozostaje `spec`. Wybór profilu trafia do
`provenance.json`, a prompt, kod harnessu, grader, źródła i audyt są zamrażane.
12 kontroli integracyjnych: dwa poprawne warianty oraz 10 błędnych
(noop, wrong-host, dead-copy, generated-only, global-fix, no-tests,
shallow-tests, stale-tests, fake-report, skip-review).

[Wyniki kalibracji i kontroli](CALIBRATION.md).
