# Kalibracja Dispatch v1 — 2026-10-05

**Wniosek: protokół jest wykonywalny i sprawdzony, ale ten wariant nie
okazał się wystarczająco trudny dla badanego modelu.**

`opencode-go/deepseek-v4.1-flash` zaliczył wszystkie 64 kryteria w jednym
autonomicznym przebiegu, bez pomocy w trakcie. To jeden poprawnie obserwowany
przebieg jednego modelu, nie ranking ani oszacowanie pass rate.

| Grupa | Wynik |
|---|---:|
| Funkcjonalność | 24/24 |
| Przebieg i kolejność | 12/12 |
| Artefakty | 10/10 |
| Narzędzia i skille | 6/6 |
| Zakazy otwarcia | 8/8 |
| Regresje | 4/4 |
| Łączny score | 1.000000 |

Czas całego przebiegu z oceną: 324,842 s. Zapisano 72 wywołania narzędzi
w 44 krokach; zakończenie zwykłe, bez timeoutu. Raportowane zużycie: 69 934
tokenów wejściowych, 13 380 wyjściowych i 19 602 reasoning. Nie przeliczamy
ich na koszt bez danych rozliczeniowych dostawcy.

## Ślad i korekta oceny

Wyniki są lokalne, celowo ignorowane przez Git:

```
results-frontier/20261005-152737-0e14d4__dispatch-migration__opencode-go_deepseek-v4.1-flash/
```

- `grade.current.json` — poprawiona ocena 100%, wszystkie 64 kryteria.
- `record.regraded.json` — wynik z hashami starego i nowego gradera.
- `grade.json` — zachowana pierwotna ocena 98,75%, jedyny fail: P08.
- `grade.rechecked.json` — odtworzenie pierwotnej oceny, identyczne z oryginałem.
- `evidence/audit.json`, `events.jsonl`, `submission/` — oryginalne dowody.
- `protocol/` — niezmienne wejścia przebiegu; `regrade-protocol-*` zachowuje korektę gradera.

Pierwotny grader przypisał nieudane `arena-ops check` bez argumentu SCOPE
do modułu config. Model poprawnie opisał tę pomyłkę składni w dzienniku CLI
przed pierwszą zmianą źródła. To błąd gradera, a nie modelu. Korekta przypisuje
błędy składni bez scope do CLI. Osobna kontrola zalicza poprawną diagnozę,
a kontrola pominiętej diagnozy rzeczywistego testu nadal oblewa P08.
Regrade użył tego samego audytu i submission; nie wykonano kolejnego
wywołania modelu ani nie obniżono wymagań promptu.

## Wykluczona próba i automatyczne indeksowanie

Wcześniejsza próba:

```
results-frontier/20261005-134004-d3dd2a__dispatch-migration__opencode-go_deepseek-v4.1-flash/
```

Ma `valid_for_quality=false`, `run_outcome=harness_contamination`.
OpenCode odczytał wszystkie zakazane pliki przed pierwszym narzędziem modelu.
Nie zaliczamy tego jako porażki modelu. Lokalny sztuczny dostawca, który
odpowiada tylko READY, odtworzył te otwarcia; procesem był `fff-scan`.
Wyłączenie samych snapshotów nie pomogło. `OPENCODE_DISABLE_FFF=true`
usunęło otwarcia w kontroli bez narzędzi. Dopiero potem ponowiono model.

## Kontrole protokołu

21 testów jednostkowych obserwacji przeszło. Końcowa seria integracyjna
ma 16 poprawnie rozpoznanych scenariuszy. Pełny wzorzec i rzeczywisty rollback
osiągają 100%; pusty przebieg 23,2143%. Grader wykrywa bezpośredni odczyt,
alias, spóźniony baseline/backup/notatkę, nieaktualne testy, fałszywe receipt,
zmianę chronionych danych cofniętą przed końcem i pominięte sprawdzenie
konsumentów. Kontrola harnessu potwierdza automatyczne odczyty przy domyślnej
konfiguracji oraz ich brak przy konfiguracji benchmarku.

Zbiorczy ślad: `results-frontier/validation-final/summary.json`.

## Co zaostrzyć w następnej wersji

Nie zmieniamy reguł tej wersji po obejrzeniu wyniku. Nowy wariant powinien
mieć osobny identyfikator i własną kalibrację. Hipotezy do sprawdzenia:

1. Więcej warunkowych obowiązków zależnych od faktycznie wykonywanej zmiany.
   Obecne pięć modułów pozwala przygotować komplet notatek na samym początku.
   Potrzebne są warunki aktywujące się również przy późniejszych poprawkach,
   zmieniające wymagany dowód zależnie od zakresu zmiany.
2. Więcej różniących się wyjątków tenantów i konsumentów. Samo powielenie
   liczby identycznych raportów nie dodaje istotnej trudności. Reguły powinny
   obejmować odmienne kontrakty, zależności i dozwolone działania.
3. Obowiązki powracające po naprawie: po zmienieniu konkretnego kontraktu
   trzeba zaktualizować tylko właściwe dowody, odbiorców i raporty.
   Nadal bez przypomnień serwisu, jaka czynność należy się teraz.
4. Oceniać osobno poprawność produktu oraz odsetek zastosowanych obowiązków.
   Obecny skalar mocno waży funkcjonalność, więc nawet wiele pominięć procesu
   może pozostawić wysoki wynik. To kwestia interpretacji i projektowania
   przyszłej skali, nie powód do zmiany uzyskanego wyniku.

Większy korpus danych i przeciążanie początkowego kontekstu nie są potrzebne
do tego wariantu; należą do odrębnego testu pamięciowego z pomysłu Daro.
