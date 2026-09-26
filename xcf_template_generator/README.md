# XCF template generator (eksperyment)

Ten plugin testuje wariant, w ktorym XCF jest glownym template'em, a CSV/XLSX zawiera tylko dane.

Nie korzysta z `BaseGeneratorPlugin`, analizatora XCF ani generatora JSON.

## Nazwy warstw

Warstwy, ktore maja byc wypelniane, powinny miec nazwy:

- `nazwa_warstwy:text:nazwa_db` - ustawia tekst z kolumny `nazwa_db_text`.
- `nazwa_warstwy:img:nazwa_db` - wczytuje plik z kolumny `nazwa_db_img`.
- `nazwa_warstwy:shape:nazwa_db` - zarezerwowane do obslugi ksztaltow.

Przyklad:

```text
tytul:text:nazwa_karty
opis:text:opis_karty
portret:img:portret
```

Plugin dla tekstu szuka kolejno `nazwa_db_text` i `nazwa_db`. Dla obrazu
szuka kolejno `nazwa_db_img`, `plik_nazwa_db` i `nazwa_db`. Stare aliasy
`txt:kolumna` i `img:kolumna` pozostaja obslugiwane.

Pozostale warstwy pozostaja bez zmian.

## Uruchomienie

1. Przygotuj XCF i nazwij warstwy wedlug konwencji.
2. Przygotuj CSV lub XLSX z naglowkami odpowiadajacymi kluczom po dwukropku.
3. W GIMP wybierz `Filtry > GeneratorKart > Generator z template XCF...`.
4. Wybierz template, dane, folder zapisu i zakres wierszy.

Plugin zapisuje `<nazwa>.xcf` oraz `<nazwa>.png`.

## Ograniczenia pierwszej wersji

- obrazy zastepuja placeholder i usuwaja stara warstwe z wynikowego XCF;
- brakujace dane nie przerywaja renderowania, ale sa wypisywane w logu;
- brak bezposredniego mapowania stylu z arkusza.
