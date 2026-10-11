# Kalibracja dossier

Walidacja z 2026-10-05. Korpus ma 50 131 534 bajty źródeł, 226 spraw,
5424 zobowiązania i 59 276 dokumentów. 356 zobowiązań jest rzeczywiście
nierozstrzygalnych; 3830 historii ma konkurencyjne kopie źródeł, a 3202
niezależny aneks dotyczący wyjątku. Każda z 48 gałęzi znaczeniowych występuje
co najmniej 93 razy. Potrzebny łańcuch zawiera najwyżej 9 cytowanych akapitów.

## Kontrole

Wszystkie **14 kontroli** dało oczekiwany rezultat: dwa poprawne warianty
uzyskały pełne zaliczenie, dwanaście celowo błędnych zostało odrzuconych.
`--verify-all` zakończyło się kodem 0 i `verification_failures: []`.

| Kontrola | Punkty częściowe | Wiersze w pełni udokumentowane |
|---|---:|---:|
| reference | 100% | 5424 |
| equivalent — inne cytowania i kolejność | 100% | 5424 |
| noop | 0% | 0 |
| all-unknown | 19,28% | 121 |
| stale | 46,91% | 1118 |
| wrong-entity | 70% | 0 |
| fabricated-citations | 80% | 0 |
| shotgun-citations | 80% | 0 |
| missing-rows | 50% | 2712 |
| invented-rows | 99,9908% | 5424, plus jeden fikcyjny |
| duplicate-rows | 99,9723% | 5423 |
| keyword | 41,30% | 0 |
| latest | 35,42% | 0 |
| regex | 35,42% | 0 |

Kontrole z fikcyjnymi cytowaniami otrzymują punkty za poprawne wartości
przepisane ze wzorca, lecz nie za dowody, i nie zaliczają zadania. Niewielka
kara za pojedynczy dodatkowy wiersz jest proporcjonalna do liczby 5424 pytań;
nadal uniemożliwia pełne zaliczenie. Rozwiązania keyword/latest/regex mają
dostęp tylko do publicznych plików; nie odczytują wzorca. Keyword poprawnie
rozstrzyga 11,28% wierszy, a latest i regex 0%. Żadne nie odtwarza pełnego
łańcucha dowodów.

Artefakty ostatniej pełnej serii: `20261005-233623`–`20261005-233721`,
zestawienie w
[`summary.json`](../../results-frontier/dossier-validation/summary.json).
Wcześniejsza seria z bardziej rygorystycznym kodem Basis pozostaje w
[`summary.strict-basis.json`](../../results-frontier/dossier-validation/summary.strict-basis.json).
Seria po pierwszej korekcie kodów, ale przed korektą dowodu tożsamości, jest w
[`summary.basis-revision.json`](../../results-frontier/dossier-validation/summary.basis-revision.json).

## Testy techniczne

Przeszło **36 unikalnych testów jednostkowych**: 15 nowych testu 3 oraz 21 wcześniejszych
testu 4, zadań returns i protokołu obserwacji. Pokrywają m.in. 48 ręcznie
określonych skutków semantycznych, kompletność odwołań, alternatywne dowody,
nieuprawnione cytowania, dopuszczalne ogólne uzasadnienia, powtarzalność
generatora, ponowne użycie cache, wykrycie jego uszkodzenia i izolację plików.
Przeszły kontrola składni shella oraz kompilacja zmienionych modułów Pythona.
Publiczny walidator zaakceptował tabelę wzorcową: 5424 wiersze, 0 błędów
strukturalnych. Nie otrzymał dostępu do ukrytej oceny.

Odtworzenie zamrożonego wzorca dało identyczny wynik 100%. Po dodaniu
kopiowania samej tabeli do gradera wzorzec ponownie uzyskał 100%:
[`20261005-232607-5a5b1b__dossier__reference`](../../results-frontier/20261005-232607-5a5b1b__dossier__reference/).
Duże indeksy robocze pozostają w archiwizowanym workspace, ale nie zużywają
tmpfs przeznaczonego na ocenianie. Pierwsza sesja modelowa rozpoczęła się
jeszcze z wcześniejszym, zamrożonym kopiowaniem całego workspace.

Kontenerowy wzorzec zadania 4 zachował **19/19**:
[`20261005-232023-08bbb6__export-forensics__reference`](../../results-frontier/20261005-232023-08bbb6__export-forensics__reference/).
Po ostatniej zmianie wspólnego kopiowania plików wzorzec `returns-release`
zachował **36/36**:
[`20261005-232935-93c440__returns-release__reference`](../../results-frontier/20261005-232935-93c440__returns-release__reference/).

## Sesja modelowa

Jedna autonomiczna sesja `opencode-go/deepseek-v4.1-flash`, z limitem
7200 s, zakończyła się po **948,46 s (15 min 48 s)**:
[`20261005-231801-9a0427__dossier__opencode-go_deepseek-v4.1-flash`](../../results-frontier/20261005-231801-9a0427__dossier__opencode-go_deepseek-v4.1-flash/).
Model wykonał 77 kroków i 88 wywołań narzędzi, bez błędów narzędzi.
Po korektach gradera niezmieniona odpowiedź ma **99,2948% punktów częściowych**
i **5339/5424 (98,43%) wierszy w pełni poprawnych i udokumentowanych**.
Pełnego zaliczenia nie uzyskała.

Wszystkie zakresy są obecne dokładnie raz. Podmioty, wyjątki, daty i wszystkie
356 przypadków nierozstrzygalnych rozpoznano poprawnie. Wszystkie cytaty
wskazują prawdziwe, właściwe źródła. W 85 wierszach model zachował pierwotną
regułę zamiast wiążącej reguły z nadrzędnej wersji językowej. Wszystkie te
błędy należą do rodziny `translation`: 141/226 poprawnych wierszy; pozostałe
23 rodziny mają komplet poprawnych wierszy.

W czasie sesji, przed jej zakończeniem, przegląd autora usunął z gradera
arbitralne wymaganie szczegółowego kodu Basis tam, gdzie publiczny kod ogólny
jest również prawdziwy. Nie zmieniono promptu, korpusu, słownika ani
wymaganego formatu. Sesja miała zamrożony pierwotny grader. Po zakończeniu
analiza dowodów ujawniła dodatkowo, że umowa sama podaje prawidłowy podmiot
prawny, a novacja podaje następcę. Wymóg dodatkowego cytatu z rejestru był
nadmiarowy. Dopuszczono też prawdziwe szczegółowe kody Basis dla rozstrzygniętego
pierwszeństwa i zakresu z włączonego załącznika. Usunięto kary za te równoważne
sposoby uzasadnienia, zachowując wymagania dotyczące faktów i pozostałych ról
dowodowych.

| Grader | Wynik częściowy | Pełne wiersze | Artefakt |
|---|---:|---:|---|
| Pierwotny | 94,8201% | 0 | `grade.json`, `record.json` |
| Zamrożone odtworzenie pierwotnego | 94,8201% | 0 | `grade.rechecked.json`, identyczny wynik |
| Pierwsza korekta Basis | 95,3955% | 0 | `grade.basis-revision.json`, `record.basis-revision.json` |
| Końcowa korekta dowodów i uzasadnień | 99,2948% | 5339 | `grade.current.json`, `record.regraded.json` |

Pierwotne zero pełnych wierszy było artefaktem wymagania osobnego cytatu
tożsamości w każdej odpowiedzi. **Nie jest dowodem, że model nie udokumentował
żadnego wniosku.** Rewizje zachowują hashe, zamrożony audyt i niezmienioną
odpowiedź. Nie wykonano drugiej sesji modelu ani nie poprawiano jego tabeli.

## Wniosek o trudności

Ta wersja jest technicznie zweryfikowana, ale jedna próba nie ustala rankingu
ani pass rate czołówki. Model jawnie rozpoznał 24 powtarzające się rodziny
i napisał parser wraz z regułami rozstrzygającymi. Skutecznie wykorzystał
regularność syntetycznego generatora, mimo że trzy proste kontrole zawiodły.
Oznacza to, że wynik mierzy także rozpoznawanie struktury i budowę takiego
parsera; nie dowodzi przetworzenia 50 MB niezależnie napisanych znaczeń.
Przed traktowaniem zadania jako docelowego, bardzo trudnego testu czołówki
potrzebna jest większa różnorodność narracji oraz kalibracja innych mocnych
modeli i seedów. Wysokiego wyniku DeepSeek nie należy ukrywać za pierwotnymi
błędami gradera.
