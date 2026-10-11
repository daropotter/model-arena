# CSV w aplikacjach interaktywnych

POST pod ścieżkę skonfigurowaną dla hosta, JSON:
{"columns":[{"key":"id","label":"ID"},{"key":"amount","label":"Kwota"}],
 "rows":[{"id":"x","amount":0}]}

Kolejność kolumn pochodzi z columns, nie z kolejności kluczy w rekordach.
Nagłówek to label. Każdy wiersz zachowuje każdą pozycję: brak, null i pusty
string dają puste pole, 0 daje "0", false daje "false", true daje "true".
Tekst zachowuje Unicode, znaki separatora, cudzysłowy i nowe linie — CSV
musi prawidłowo cytować. Końce rekordów CRLF. UTF-8; BOM i separator według
konfiguracji instancji. Content-Type text/csv; charset=utf-8. Wejście puste
rows nadal daje nagłówek. Puste columns, brak rows lub zły typ daje 400.
Bez zmiany danych, stanu ani formatu innych klientów.

Katalog (consumer=catalog) używa tych samych reguł pozycji, lecz swojego
separatora i bez BOM. Odbiorcy maszynowi mogą mieć utrwalone wyjątki;
przegląd zgodności release podaje obowiązujące ustalenia tych klientów.
