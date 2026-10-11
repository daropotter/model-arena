# Dossier — rekonstrukcja obowiązujących ustaleń

Zadanie 3 działa osobno w `tasks-frontier/`, pod identyfikatorem
`model-arena-frontier-dossier-v1`. Prompt, korpus i wynik są po angielsku.
Agent oddaje **tabelę Markdown** w `answer/obligations.md`.

## Korpus i trudność

Generator tworzy co najmniej **50 000 000 bajtów tekstu źródłowego**. Kończy
ostatnią sprawę, więc przekroczenie celu o rozmiar jednej sprawy jest
zamierzone. Indeks, słownik i rejestr pytań nie wliczają się do tych 50 MB.
Domyślny seed daje 50 131 534 bajty, 226 spraw, 5424 zobowiązania i 59 276
dokumentów rozłożonych w 512 tomach. Każda sprawa obejmuje cztery produkty
i sześć tematów wybranych z dwunastu. Każdy dokument należy do historii
co najmniej jednego ocenianego zobowiązania; nie ma sekcji dopisanej wyłącznie
dla zwiększenia rozmiaru.

24 rodziny znaczeniowe obejmują m.in. częściową akceptację, umocowanie autora,
wygaśnięcie, warunek łączny, odwołaną delegację, novację, pierwszeństwo
szczegółowego aneksu, brakujący zakres, kontrpropozycję, przetrwanie reguły
po wypowiedzeniu i pierwszeństwo wersji językowej. Każda ma dwie wersje
o innych skutkach prawnych, z podobnymi słowami i tymi samymi opcjami reguły.

Niezależne warstwy utrudniają rozpoznawanie pojedynczych formułek:

- Sprzeczne kopie zapisują obie wersje kluczowej wypowiedzi. Osobne
  potwierdzenie pochodzenia wskazuje wiarygodną kopię przez wykluczenie,
  zakres produktu lub rozdzielenie rekomendacji od uprawnionego poświadczenia.
- Aneks zmieniający tylko wyjątek ma osobno uzgodniony zakres. Nie wybiera
  reguły, nie usuwa rzeczywistej niepewności i nie resetuje daty jej obowiązywania.
- Nazwa handlowa zmienia się bez zmiany podmiotu, podobny podmiot pozostaje
  odrębny, a novacja może przenieść tylko konkretne zobowiązanie.
- Późne propozycje i konfiguracje operacyjne używają wiarygodnych alternatywnych
  reguł, choć same nie wykonują aneksu. Fizyczna kolejność plików i losowe
  identyfikatory nie wskazują poprawnej odpowiedzi.

Rejestr pytań usuwa zgadywanie, ile wierszy trzeba oddać. Nie zawiera odpowiedzi.
Publiczny słownik daje kody normalizacyjne zamiast polegania na modelu-sędzim
oceniającym swobodny tekst. Skrypty, wyszukiwanie, notatki i kompresja kontekstu
są dozwolone. Profil `reconstruction` nie nakazuje kodowania ani czytania SPEC.md.
Treść korpusu jest dostępna na żądanie w plikach, bez wstrzyknięcia do promptu.

## Wzorzec i ocena

Generator jednocześnie zapisuje prywatny wzorzec, przyczyny rozstrzygnięć,
grupy niezbędnych dowodów i dopuszczalne zamienniki, np. poświadczony odpis.
Wzorzec i kod generatora pozostają w niedostępnym dla agenta katalogu `/private`.
Do workspace kopiowane są wyłącznie `starter/` i `assets/workspace/`.
Rozwiązanie referencyjne trafia do procesu testowego tylko w trybie `--verify`.

Ocena częściowa jest średnią po **wszystkich** wymaganych wierszach:

| Składnik wiersza | Waga |
|---|---:|
| Obecność jednoznacznego wiersza | 5% |
| Podmiot prawny | 10% |
| Stan: bound / unresolved | 10% |
| Aktualna reguła | 25% |
| Wyjątek | 10% |
| Data obowiązywania | 10% |
| Podstawa rozstrzygnięcia | 10% |
| Pełny, precyzyjny łańcuch dowodów | 20% |

Ogólne kody `baseline-controls` i `executed-change` są dopuszczalne również
wtedy, gdy wzorzec stosuje bardziej szczegółowy kod, o ile odpowiadają
rzeczywistemu rozstrzygnięciu. Wybór autorskiej etykiety nie zastępuje oceny
prawdziwości wniosku.
Analogicznie rozstrzygnięte pierwszeństwo może mieć kod `specific-prevails`,
a potwierdzony zakres z włączonego załącznika — `incorporated-term`.
Dowód podmiotu może pochodzić z umowy lub wykonanego instrumentu novacji;
oddzielny cytat z rejestru nazw nie jest obowiązkowy. Jeden akapit może
udowadniać kilka elementów łańcucha.

Za dowody uznaje się cytowania wspierające poprawne rozstrzygnięcie. Ich wynik
łączy pokrycie wymaganych ról i precyzję cytowań. Maksymalnie 12 źródeł na
wiersz zapobiega wrzuceniu całego archiwum do każdej komórki. Nieaktualne
reguły, pomylone podmioty, bezpodstawne twierdzenia i nadmiarowe „unresolved”
mają osobne metryki. Brakujące lub zduplikowane zakresy nie dostają punktów
za wiersz; dodatkowe wymyślone zakresy i duplikaty powodują karę. Uszkodzenie
korpusu zeruje wynik. Pełne zaliczenie wymaga wszystkich kryteriów C01–C09.

`score` jest wynikiem częściowym, nie odsetkiem całkowicie udokumentowanych
wierszy. Ten ostatni należy odczytywać jako `exact_rows / total_rows`.
Dlatego poprawne wartości ze zmyślonymi cytowaniami mogą uzyskać punkty za
wartości, ale mają 0 wierszy w pełni uzasadnionych i nie zaliczają zadania.
Obok score runner zapisuje m.in. `resolution_accuracy`, `evidence_accuracy`,
`entity_error_rate`, `stale_rule_rate`, `unsupported_claim_rate` oraz wyniki
dla poszczególnych rodzin historii.

Publiczne `validate.py` sprawdza tylko strukturę, pokrycie i słownik. Nie
wywołuje ukrytego gradera, nie udostępnia oracle ani informacji, czy dany
wniosek jest poprawny. Ocena końcowa korzysta z zaufanego parsera i zamrożonych
danych, bez uruchamiania kodu kandydata.

Do katalogu roboczego gradera kopiowana jest tylko końcowa tabela. Pełny
workspace z indeksami i notatkami pozostaje w artefaktach przebiegu; jego
rozmiar nie zużywa małego tmpfs przeznaczonego na ocenę. Selekcja pliku
odrzuca dowiązania symboliczne, także w katalogach nadrzędnych.

## Generowanie i uruchomienie

```bash
# Przygotowanie opcjonalne: runner zrobi to sam, jeżeli brakuje cache.
python3 tasks-frontier/dossier/build_corpus.py

# Pełny wzorzec, następnie dwa poprawne i dwanaście błędnych wariantów.
python3 runner/frontier.py --task dossier --verify --timeout 300
python3 runner/frontier.py --task dossier --verify-all --timeout 300

# Jedna autonomiczna sesja modelowa.
python3 runner/frontier.py --task dossier \
  --model opencode-go/deepseek-v4.1-flash --timeout 7200

# Odtworzenie oceny z zamrożonym wzorcem i audytem.
python3 runner/frontier.py --regrade results-frontier/RUN
```

`assets/`, pliki robocze generatora i blokada są gitignored. Cache powstaje
atomowo pod blokadą; kolejne uruchomienie sprawdza hashe i nie generuje go
ponownie. Zmiana kodu generatora/parametrów przebudowuje cache. Uszkodzony
cache o tym samym fingerprint jest zgłaszany jako błąd, nie po cichu używany.
Nie są potrzebne sieć, API ani dodatkowe biblioteki do generowania danych.

Przebieg zamraża korpus, prywatny wzorzec, grader i harness wraz z hashami.
Nowy seed tworzy inną instancję danych i nie powinien być mieszany w jednym
rankingu bez jawnego oznaczenia. Tryb `--current-grader` odrzuci rewizję,
która zmienia źródła pokazane modelowi.

## Kontrole i ograniczenia

Kontrole obejmują: brak odpowiedzi, „nie wiadomo” wszędzie, stare reguły,
pomylenie podmiotu, fikcyjne źródła, nadmiar cytowań, brakujące/wymyślone/
powtórzone wiersze oraz trzy proste rozwiązania korzystające wyłącznie
z publicznych danych: częstotliwość fraz, najnowszy dokument i regexy
szukające podpisania/akceptacji. Drugi poprawny wariant zmienia kolejność
wierszy i cytuje dopuszczalne odpisy za pomocą linków Markdown.

To korpus syntetyczny z komponowanej biblioteki znaczeń, a nie 50 MB
niezależnie napisanej korespondencji. Przejście tych trzech słabych kontroli
nie dowodzi odporności na każdy parser wyuczony na stylu generatora. Także
5424 poprawne kody nie dowodzą dowolnie szerokiego rozumienia prawa; mierzymy
konkretne rozstrzygnięcia i ich udokumentowanie. Przed włączeniem do rankingu
czołówki trzeba sprawdzić skuteczność mocnych modeli i silniejszego parsera
na kolejnych seedach. Nie przedstawiamy samego rozmiaru jako dowodu trudności.

[Przegląd wzorca i semantyki](REVIEW.md) · [Wyniki walidacji](CALIBRATION.md)
