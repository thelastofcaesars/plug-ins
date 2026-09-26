Wymagania:
Gimp 3.2+

Python 3.10+


Ogólne


kolor królestwa - albo z kartą- wsm z kartą generowane - czyli z bazy danych kart wzięty kolor na podstawke
generacja gralli 0p
wsm kolor chyba powinien być propagowany dalej na inne bazy - jeśli by miała nastąpić zmiana kolorów w królestwach - tak raczej by łatwiej było
ewentualnie kolor zostaje na planszy w kolejności, a reszta leci dalej, idk
nazywać tak lub w bazie danych, co by łatwo się generowała cała plansza

architektura:
template_gimp_xcf:

nazwa_warstwy:typ_warstwy:nazwa_db

typ_warstwy:

- img - w zasadzie redundantne bo gimp xcf to wie - w db {nazwa}_img
- text - w db {nazwa}_text
- shape - do zastanowienia
- dodajemy jeśli są w db, jeśli nie to nie, patrzymy się najpierw po typie warstwy w xcf - ergo- szukamy kolumny _text jeśli warstwa to text w gimpie

w db dodatkowo mogą znajdowac się inne informacje, w tym np nr karty, typ karty,

to jak baza danych radzi sobie z wyciaganiem danych - zostawiamy bazie danych, my chcemy tylko request o zasoby

fajnie jakby ostatecznie to byl nowy plik xcf na podstawie starego bez starych warstw - czyli podmieniamy tylko zawartośc tych warstw co są

todo: wyrównywanie tekstu na środek - jeśli 4-5linijek itd, no dostosywanie
