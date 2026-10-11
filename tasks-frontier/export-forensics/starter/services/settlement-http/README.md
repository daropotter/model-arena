# Settlement transport

Ta usługa nie ma zależności od katalogu apps/reporting. Pakiet records
wybiera manifest budowania; uruchomienie ze zmienionym PYTHONPATH może
korzystać z innej wersji niż wdrożenie. Konfigurację consumer przekazujemy
do warstwy projekcji. Build zawiera app.py jako moduł application.
