# Kalibracja Distributed returns v2

Nowy wariant jest oceniany oddzielnie od Returns release v1, na którym
DeepSeek v4.1 Flash uzyskał 36/36 w 390,586 s. Nie zmieniamy tamtej próby.

Wzorzec dla obecnych 48 etapów i 40 końcowych scenariuszy: 48/48,
ścieżka 33/33, 9/9 scenariuszy użytkownika. Zgodny wariant z innym
formatowaniem podpisywanego JSON i dodatkowym polem klienta: również 48/48.
Kontrole używają prawdziwych procesów, HTTP i dwóch zachowywanych ksiąg.

## DeepSeek v4.1 Flash — jedna autonomiczna sesja

Model: `opencode-go/deepseek-v4.1-flash`. **48/48 etapów, 33/33 ścieżki,
9/9 scenariuszy użytkownika, 40/40 końcowych scenariuszy produktu.**
`final_artifact_verified=true`, `valid_for_quality=true`, zakończenie normalne,
bez ponaglenia człowieka. Limit 7200 s, rzeczywisty czas runnera **740,176 s**
(12 min 20 s; tak samo jak w v1 pomiar obejmuje końcową ocenę).

| Pomiar | Returns release v1 | Distributed returns v2 |
|---|---:|---:|
| Etapy | 36/36 | 48/48 |
| Ścieżka ze wszystkimi zależnościami | 26/26 | 33/33 |
| Scenariusze użytkownika | 7/7 | 9/9 |
| Czas runnera | 390,586 s | 740,176 s |
| Wywołania narzędzi | 77 | 98 |
| Kroki modelu | 62 | 75 |
| Tokeny wejściowe raportowane przez runner | 64 296 | 115 813 |
| Tokeny wyjściowe | 19 568 | 29 751 |
| Tokeny reasoning raportowane przez provider | 22 185 | 53 050 |

Pierwszy kandydat `r0003` oblał S07 (walidacja) i S19 (izolacja dostępu).
Model poprawił implementację, zbudował `r0015` i ponowił komplet 11 grup.
Dopiero potem wykonał handoff (`r0028`), zmienił źródła i kontrakt na ABI2,
zbudował `r0029`, ponowił 11 grup i dokończył wydanie. Łącznie 47 formalnych
operacji: 3 buildy, 33 weryfikacje, 3 wdrożenia oraz pozostałe kroki cyklu.
Pierwsze zielone testy nie zostały uznane za dowód dla końcowych bajtów.
Model dodał też `tests_extra/test_e2e.py` i `tests_extra/test_proto2.py`.

Pełne wyniki: `results-frontier/20261005-192910-928fa2__returns-distributed__opencode-go_deepseek-v4.1-flash/`.
Ważne pliki: `record.json`, `grade.json`, `evidence/audit.json`, `provenance.json`,
`submission/` i zamrożone `protocol/`. Nie zmieniano promptu ani gradera
w odpowiedzi na wynik modelu; nie poprawiano jego rozwiązania. Jeden przebieg,
bez wybierania najlepszego z wielu. **Zamrożony regrade dał identyczny wynik**,
bez zmiany gradera (`revised_grader=false`).

## Co wynika z tej próby

Zakres jest większy, a zmierzony czas około **1,90×** dłuższy. Model musiał
przejść realną poprawkę i ponownie odnowić testy, następnie obsłużyć zmianę
integracji z zachowaną kolejką. To nie dowodzi, że sam czas mierzy trudność:
pomiar obejmuje różną liczbę testów, a jedna próba nie estymuje wariancji.

**Wynik jakościowy nadal osiągnął 100%. Ten wariant nie oddzielił jeszcze
tego mocnego modelu od idealnego wyniku.** Nie należy na tej podstawie
ogłaszać skutecznego rozróżniania czołówki ani rankingu modeli. Dalsze
zwiększanie trudności powinno dostać osobny wariant, zachowując ten pomiar.
Przykładowy następny kierunek to szersze zależności produktowe i rzeczywiste
zmiany reprezentacji danych; nie samo dopisywanie punktów checklisty.


## Kontrole oceny

Wszystkie 13 negatywnych kontroli oblało wskazane etapy, przy poprawnym
zakończeniu procesu wzorcowego. Dwa pozytywne warianty dostały 48/48.
Wynik procentowy sam nie wystarcza do zaliczenia: np. fałszywy manifest
pozostawia 47/48 działających etapów, ale przerywa odbiór wydania.

| Kontrola | Ukończone etapy | Oczekiwane odrzucone etapy |
|---|---:|---|
| reference | 48/48 | pełne zaliczenie |
| noop | 0/48 | S27, S38 |
| no-worker | 23/48 | S14, S27 |
| duplicate-charge | 44/48 | S29 |
| ignore-lease | 45/48 | S30 |
| lost-pending | 39/48 | S41, S42 |
| old-wire | 24/48 | S36, S42 |
| stale-client | 44/48 | S35 |
| stale-checks | 46/48 | S40 |
| skip-handoff | 22/48 | S38, S39 |
| no-rollback | 43/48 | S44, S45 |
| wrong-cursor | 45/48 | S34 |
| fake-manifest | 47/48 | S48 |
| unfenced-worker | 45/48 | S30 |
| equivalent | 48/48 | pełne zaliczenie |

Źródło: `results-frontier/returns-distributed-validation/summary.json`
(zawiera katalog, skrót wersji zadania i rzeczywiste odrzucone etapy).
Pierwsze cztery kontrole finansowe/aktualności powstały przed dodaniem
dodatkowego scenariusza spóźnionego potwierdzenia workera; ich właściwe
warunki oceny nie zmieniły się. Wzorzec, kontrola equivalent i unfenced-worker
obejmują już oba warianty S30.

Wzorzec: `20261005-192515-b31aef__returns-distributed__reference`;
zamrożony regrade: identyczny wynik. Kontrola equivalent:
`20261005-192515-b42174__returns-distributed__reference-equivalent`.
Regresja v1: `20261005-192816-531fc2__returns-release__reference`, 36/36.
Testy jednostkowe: 7 dla obu wariantów returns i 8 dla protokołu obserwacji.
