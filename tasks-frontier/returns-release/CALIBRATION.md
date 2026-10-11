# Kalibracja Returns release v1 — 2026-10-05

**DeepSeek ukończył pełne wydanie: 36/36 etapów, 26/26 długości ścieżki
z kompletem zależności, 7/7 scenariuszy użytkownika.** Test ocenia rzeczywisty
produkt, ale ta pierwsza wersja nadal nie rozróżniła badanego mocnego modelu
od wzorca. Jedna próba nie jest oszacowaniem pass rate ani rankingiem.

Model: `opencode-go/deepseek-v4.1-flash`. Jedna autonomiczna sesja, bez
ponagleń ani dodatkowych instrukcji od człowieka w trakcie. Limit wynosił
7200 s; model zakończył sam po 390,586 s (6 min 31 s), wraz z końcową oceną.

| Metryka | Wynik |
|---|---:|
| Ukończone etapy | 36/36 |
| Score ukończenia | 100% |
| Etapy z kompletem zależności | 36/36 |
| Najdłuższa poprawna ścieżka / maksymalna | 26/26 |
| Scenariusze użytkownika | 7/7 |
| Końcowe scenariusze produktu | 29/29 |
| Grupy sprawdzone na finalnym artefakcie | 8/8 |
| Finalny artefakt zgodny ze źródłami i testami | tak |

77 wywołań narzędzi w 62 krokach; 3 raportowane błędy narzędzi. Dostawca
zaraportował 64 296 tokenów wejściowych, 19 568 wyjściowych oraz 22 185
reasoning. Nie przeliczamy tych liczb na koszt bez danych rozliczeniowych.

## Co faktycznie wykonał model

Model zmienił używane źródła, dodał własny zestaw testów end to end w
`tests_extra/test_returns.py` i uruchamiał go na zbudowanej paczce. Własny
test wykrył problem z parsowaniem argumentów klienta CLI; model poprawił go
przed pierwszym kandydatem do wydania. Potem wszystkie osiem grup
akceptacyjnych przeszło bez dodatkowych zmian źródła.

Audyt zawiera 208 zdarzeń i 19 operacji `arena-ops`:

| Receipts | Czynność |
|---|---|
| r0001–r0002 | baseline starej aplikacji i backup |
| r0003 | deterministyczny build kandydata |
| r0004–r0011 | osiem grup weryfikacji tej paczki |
| r0012–r0014 | deploy, rzeczywisty zwrot, checkpoint po rozliczeniu |
| r0015–r0016 | uruchomienie starego kodu, sprawdzenie starego klienta |
| r0017–r0018 | ponowny deploy oraz smoke zachowanych danych |
| r0019 | dodatkowy build o identycznych bajtach i źródłach |

Aktywny pozostał kandydat r0003. Ostatni r0019 nie zmienił kodu ani
aktywnego wydania; jego identyczny hash potwierdza powtarzalność.

Finalny artefakt SHA-256:

```
21e6da5e042a723113b235a374572f8fe53dca838bcfb091d7dc09e63a981193
```

Logiczny hash bazy po zwrocie, przed i po rollbacku, przed i po ponownym
deploy oraz na końcu sesji był identyczny. Grader dodatkowo potwierdził
zwrot `refunded`, kwotę 333 grosze, pojedynczy wpis księgi, stan magazynu 11,
bezskutkowe ponowienie tego samego klucza i działanie starego klienta.
Procesy HTTP naprawdę zostały uruchomione z paczek, zatrzymane i wznowione.

## Zachowane dowody i odtwarzanie

Wynik lokalny, ignorowany przez Git:

```
results-frontier/20261005-182803-3c4725__returns-release__opencode-go_deepseek-v4.1-flash/
```

`grade.json` zawiera etapy, graf, grupy i scenariusze; `record.json` także
`task_metrics`, czas i zużycie. `evidence/audit.json` zachowuje zdarzenia
oraz bajty zbudowanych aplikacji. `protocol/` zawiera zamrożone wejścia,
runner i grader, a `submission/` końcową pracę modelu.

Pierwotny wynik wynosił 100%. Nie zmieniano gradera po obejrzeniu wyniku
modelu ani nie stosowano korekty jego punktacji. Ponowna ocena oryginalnym
graderem odtwarza ten sam wynik w `grade.rechecked.json`.

Podczas przygotowywania harnessu, przed oceną modelu, pierwszy wzorzec
ujawnił brak CAP_KILL dla supervisora zatrzymującego proces innego UID.
Kontrola regrade ujawniła brak CAP_FOWNER przy przygotowywaniu katalogów
należących do UID aplikacji. Uprawnienia kontenerów wyrównano; problemy te
nie są liczone jako porażki modelu. Aplikacja i agent pozostają bez tych
capabilities. Socket operacji dodatkowo sprawdza UID rozmówcy, aby kod
aplikacji nie mógł produkować własnych potwierdzeń wykonania.

## Kontrole negatywne i pozytywne

Wszystkie 10 końcowych kontroli dało oczekiwane wyniki:

| Wariant | Etapy | Ścieżka | Wykryte |
|---|---:|---:|---|
| reference | 36/36 | 26/26 | cały działający workflow |
| noop | 0/36 | 0/26 | brak pracy |
| dead-code | 5/36 | 2/26 | poprawiony wyłącznie niepakowany prototyp |
| stale-build | 26/36 | 16/26 | źródło zmienione po zbudowaniu i testach |
| stale-check | 34/36 | 17/26 | nowa paczka bez odnowienia testów |
| no-rollback | 31/36 | 21/26 | pominięty rzeczywisty rollback |
| fake-report | 35/36 | 25/26 | nieistniejący smoke receipt |
| broken-client | 33/36 | 14/26 | serwer działa, klient w paczce nie |
| duplicate-refund | 33/36 | 9/26 | retry ponownie zmienia księgę |
| lost-state | 31/36 | 15/26 | migracja usuwa zwroty przy powtórzeniu |

Ślad: `results-frontier/returns-validation/summary.json`. Wzorzec:
`results-frontier/returns-validation/20261005-182802-630432__returns-release__reference`.
Jego zamrożony regrade jest identyczny. Przeszły cztery testy jednostkowe
grafu/izolacji socketu i osiem istniejących testów obserwacji. Referencyjny
Dispatch również zachował pełne zaliczenie po zmianach wspólnego runnera.

## Ograniczenie trudności

36 to liczba logicznych etapów odbioru; nie jest to dowód 36 oddzielnych,
trudnych prac implementacyjnych. Model może napisać kilka warstw jednym
ciągiem. Całość mieści się w małym projekcie Python+SQLite. Brak własnego
UI przeglądarkowego, niezależnego workera i osobnego systemu płatności
ogranicza liczbę problemów integracyjnych.

Model naprawił klienta przed pierwszym formalnym buildem. Poprawnie obsłużył
całe wydanie, ale ta próba nie wymusiła późnej poprawki unieważniającej
wcześniejsze potwierdzenia; tę właściwość miernika potwierdziły kontrole
stale-build/stale-check, a nie zachowanie modelu w tej próbie.

W kolejnej osobnej wersji warto sprawdzić rozbudowę o niezależny worker
outbox, klienta o innym cyklu budowania i obowiązkowe odnowienie dowodów po
późnej zmianie integracyjnej. To hipotezy zwiększenia trudności, jeszcze
niezaimplementowane. Nie dopisujemy reguł do zakończonej próby i nie
przedstawiamy pełnego zaliczenia jako porażki modelu.
