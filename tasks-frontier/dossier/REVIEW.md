# Przegląd semantyki i wzorca

Przegląd autorski obejmuje 48 rozgałęzień znaczeniowych i niezależne operatory
pochodzenia źródła oraz zakresu wyjątku. Nie jest zewnętrzną ekspertyzą prawną
ani niezależnym przeglądem człowieka. Korpus ustanawia własne jawne konwencje
kontraktowe; zadaniem jest odtworzenie ich skutków, a nie dopowiedzenie prawa
konkretnej jurysdykcji.

Poniżej A to oryginalna reguła, B to propozycja, C to konkurencyjna reguła.
W każdym zakresie rzeczywiste treści A/B/C są losowo przypisywane do trzech
różnych opcji tematu. Kolumny nie są publicznym oznaczeniem wariantów.

| Rodzina | Wersja negatywna | Wersja pozytywna | Rozstrzygający szczegół |
|---|---|---|---|
| execution | A | B | Podpis obejmuje protokół negocjacji albo zmianę zobowiązania |
| authority | A | B | Autor „Approved” ma uprawnienia operacyjne albo kontraktowe |
| condition | A | B | Potwierdzony brak albo spełnienie warunku wejścia w życie |
| sunset | A od wygaśnięcia | B | Upłynął albo nie upłynął okres tymczasowej zmiany |
| scope | A | B | Wyłączono właściwy albo drugi produkt |
| priority | C | B | Późny dokument usuwa albo zachowuje wcześniejszy szczegółowy |
| conflict | unresolved | B | Brak albo obecność wiążącego rozstrzygnięcia pierwszeństwa |
| missing-schedule | unresolved | B | Brakuje załącznika określającego zakres albo zakres jest poświadczony |
| partial-assent | A | B | Przyjęto zmianę kontaktu albo zmianę reguły |
| correction | A | B | Skaner albo obie strony zatwierdziły materialną korektę |
| novation | B, stary podmiot | B, nowy podmiot | Oddzielna zgoda na przejęcie całej pozycji kontraktowej |
| rescission | A od uchylenia | B | Przyjęto albo odrzucono uchylenie aneksu |
| silence | A | B | Brak albo obecność zawartej procedury milczącej akceptacji |
| receipt | A | B | „Accepted” oznacza przyjęcie do archiwum albo również zawarcie zmiany |
| trial | A | B | Definicja obejmuje próby albo produkcję |
| conjunction | unresolved | B | Brak dowodu drugiego warunku albo oba warunki spełnione |
| incorporation | C | B | Wskazano drugą albo pierwszą alternatywę załącznika |
| future | A | B | Data obowiązywania przypada po albo przed datą przeglądu |
| renewal | A od odnowienia | B | Odnowienie zastępuje albo zachowuje pominięte aneksy |
| nested-exception | A | B | Klasyfikacja produktu w wyłączeniu i wyłączeniu z wyłączenia |
| delegation | A | B | Pełnomocnictwo odwołane przed albo po akceptacji |
| counteroffer | A | B | Zastrzeżenie pozostaje albo zostało skutecznie wycofane |
| survival | A od wypowiedzenia | B | Przetrwanie zobowiązania w środowisku przejściowym |
| translation | C | B | Pierwszeństwo równoległej albo angielskiej wersji |

Ustalono również:

- Wygaśnięcie i uchylenie przywracają A z datą przywrócenia, a nie datą
  pierwotnej umowy. Nazwa handlowa i ponowne potwierdzenie nie resetują daty.
- Niepotwierdzony warunek daje „unresolved” tylko przy jawnie niekompletnym
  kanale dowodowym. Udokumentowane niespełnienie warunku pozostawia A.
- B co do zasady niesie wyjątek z propozycji, C i A go nie dziedziczą.
  Niezależny aneks dotyczący wyjątków może to zmienić dla wskazanego produktu.
- Aneks dotyczący samego wyjątku nie rozwiązuje niepewności reguły. Przy
  „unresolved” pozostają `?` w kolumnach reguły, wyjątku i daty.
- Prawdziwa kopia dokumentu jest wybierana przez uprawnione potwierdzenie
  pochodzenia; oba cytowane warianty same nie tworzą dwóch zobowiązań.
- Odpis zastępuje tylko odtworzony fragment, nie cały łańcuch. Opcjonalne
  dokumenty mogą wspierać odrzucenie fałszywego tropu, ale nie zastępują
  dowodu tożsamości, akceptacji ani zakresu.

W `tests/unit/test_dossier.py` ręcznie zapisano oczekiwane skutki 48 gałęzi,
nie korzystając z wygenerowanego oracle do wyznaczenia tych oczekiwań.
Testy sprawdzają też, czy każdy dopuszczalny cytat istnieje, każdy dokument
należy do ocenianej historii, alternatywne cytowania przechodzą, a pominięcie
warstw pochodzenia lub wyjątku nie daje pełnego uzasadnienia.

To walidacja programu i przegląd biblioteki, nie ręczna lektura wszystkich
59 tysięcy wygenerowanych dokumentów. Błąd znaczeniowy odnaleziony później
wymaga jawnej rewizji i ponownego ocenienia zamrożonych odpowiedzi; nie wolno
cicho podmieniać danych w rozpoczętym przebiegu.

Dodatkowo odczytano komplet wymaganych źródeł trzech złożonych przykładów
domyślnego seeda: `M-E4A1C30887F2 / Vault / Canada / availability`
(konkurencyjna reguła, pierwszeństwo, wybór kopii i zmiana wyjątku),
`M-4C1E24682844 / Orbit / EEA / exit` (brak dowodu drugiego warunku,
którego późniejszy aneks o wyjątkach nie usuwa),
`M-454EC7ED2021 / Archive / UK / disclosure` (selektywna novacja i rider
dotyczący innego produktu). W każdym z tych przypadków teksty potwierdzają
rozstrzygnięcie, zakres, podmiot i datę zapisane we wzorcu.

Przegląd kodów Basis ujawnił, że publiczne definicje ogólne nakładają się na
szczegółowe. Grader akceptuje prawdziwe `baseline-controls` dla aktualnej
reguły oryginalnej oraz `executed-change` dla obowiązującej reguły zmienionej.
Pozostałe pola i dowody muszą nadal być poprawne. Osobny test odrzuca
odwrotne przypisanie tych kodów. Korektę wykonano podczas pierwszej sesji
modelowej; jej zamrożony grader i ewentualna rewizja oceny pozostają rozdzielone.

Po sesji potwierdzono jeszcze dwa dopuszczalne szczegółowe uzasadnienia:
`specific-prevails` przy wykonanym porozumieniu o pierwszeństwie oraz
`incorporated-term` przy potwierdzonym zakresie z włączonego załącznika.
Umowa jest jednocześnie dowodem zobowiązania i wskazanego w niej podmiotu;
wykonany instrument novacji może dowodzić tożsamości następcy. Nie wymagamy
drugiego cytatu z rejestru, jeśli te same fakty wynikają z cytowanych dokumentów.
Nowe testy i wariant equivalent weryfikują te równoważne uzasadnienia.
