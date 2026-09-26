<#
.SYNOPSIS
    Instaluje zależności Pythona dla tego projektu - zarówno do systemowego
    Pythona (requirements.txt), jak i do Pythona wbudowanego w GIMP-a
    (requirements-gimp.txt), którego pluginy w tym repo faktycznie używają
    w trakcie działania (np. wspolne/db_reader.py -> openpyxl).

    Po drodze odblokowuje też site-packages w Pythonie GIMP-a (plik
    python3._pth ma domyślnie zakomentowaną linię "import site", bez czego
    zainstalowane biblioteki i tak nie dałoby się zaimportować w pluginach).

.PARAMETER GimpPythonPath
    Ścieżka do python3.exe wbudowanego w GIMP-a. Jeśli pominięta, skrypt
    spróbuje go znaleźć automatycznie w typowych lokalizacjach.

.PARAMETER SkipSystem
    Pomija instalację requirements.txt systemowym Pythonem.

.PARAMETER SkipGimp
    Pomija instalację requirements-gimp.txt Pythonem GIMP-a.

.EXAMPLE
    .\install_requirements.ps1

.EXAMPLE
    .\install_requirements.ps1 -GimpPythonPath "A:\GIMP 3\bin\python3.exe"

.EXAMPLE
    # Jeśli polityka wykonywania (np. wymuszona przez GPO) i tak blokuje ten
    # plik, uruchom go jawnie z Bypass:
    powershell -ExecutionPolicy Bypass -File .\install_requirements.ps1

.EXAMPLE
    # Jeśli konsola PowerShell jest już otwarta (bez odpalania nowego procesu),
    # ustaw Bypass tylko dla bieżącej sesji i uruchom skrypt normalnie:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    .\install_requirements.ps1
#>

param(
    [string]$GimpPythonPath,
    [switch]$SkipSystem,
    [switch]$SkipGimp
)

$ErrorActionPreference = "Stop"
$KatalogSkryptu = Split-Path -Parent $MyInvocation.MyCommand.Path

# Domyślna polityka wykonywania (Restricted/AllSigned) blokuje uruchamianie
# .ps1. Ustawiamy Bypass tylko dla tego procesu (nie wymaga uprawnień admina
# i nie zmienia ustawień systemowych na stałe).
try {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
}
catch {
    Write-Warning "Nie udało się ustawić polityki wykonywania dla tego procesu: $_"
}

# Plik pobrany z internetu bywa oznaczony jako zablokowany (Mark of the Web),
# co też uniemożliwia jego uruchomienie.
try {
    Unblock-File -Path $MyInvocation.MyCommand.Path -ErrorAction SilentlyContinue
}
catch {
    # ignorujemy - to tylko wygoda, nie krytyczny krok
}

function Znajdz-GimpPython {
    if ($GimpPythonPath) {
        if (Test-Path $GimpPythonPath) {
            return $GimpPythonPath
        }
        Write-Warning "Podana ścieżka -GimpPythonPath nie istnieje: $GimpPythonPath"
    }

    # W zależności od builda GIMP-a plik nazywa się python3.exe albo python.exe.
    $nazwyExe = @("python3.exe", "python.exe")
    $foldeyBin = @(
        "$env:ProgramFiles\GIMP 3\bin",
        "${env:ProgramFiles(x86)}\GIMP 3\bin",
        "$env:LocalAppData\Programs\GIMP 3\bin"
    )
    foreach ($folder in $foldeyBin) {
        foreach ($nazwa in $nazwyExe) {
            $sciezka = Join-Path $folder $nazwa
            if (Test-Path $sciezka) {
                return $sciezka
            }
        }
    }

    # Ostatnia deska ratunku: przeszukaj foldery "GIMP*" na wszystkich dyskach lokalnych.
    $dyski = Get-PSDrive -PSProvider FileSystem | Where-Object { Test-Path $_.Root }
    foreach ($dysk in $dyski) {
        foreach ($nazwa in $nazwyExe) {
            $znaleziony = Get-ChildItem -Path $dysk.Root -Filter "GIMP*" -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName "bin\$nazwa" } |
            Where-Object { Test-Path $_ } |
            Select-Object -First 1
            if ($znaleziony) {
                return $znaleziony
            }
        }
    }

    return $null
}

function Wlacz-SitePackages {
    <#
        GIMP 3 na Windows dodaje obok python3.exe/python.exe plik
        "python*._pth", ktory domyslnie ma zakomentowana linie "import site".
        Bez niej katalog site-packages nie jest w ogole dolaczany do sys.path,
        wiec nawet po "pip install" biblioteki (np. openpyxl) i tak nie
        zaimportuja sie w pluginach GIMP-a. Trzeba odkomentowac te linie raz -
        robimy to tutaj.
    #>
    param([string]$PythonExe)

    $katalogBin = Split-Path -Parent $PythonExe
    $plikPth = Get-ChildItem -Path $katalogBin -Filter "python*._pth" -ErrorAction SilentlyContinue |
    Select-Object -First 1
    if (-not $plikPth) {
        Write-Host "Nie znaleziono pliku python._pth - pomijam ten krok."
        return
    }

    $tresc = Get-Content -Path $plikPth.FullName
    if ($tresc -match "^\s*import site\s*$") {
        Write-Host "Plik $($plikPth.Name) juz ma wlaczone 'import site'."
        return
    }

    $nowaTresc = $tresc | ForEach-Object {
        if ($_ -match "^\s*#\s*import site\s*$") { "import site" } else { $_ }
    }
    if (-not ($nowaTresc -match "^\s*import site\s*$")) {
        $nowaTresc += "import site"
    }

    Set-Content -Path $plikPth.FullName -Value $nowaTresc
    Write-Host "Odblokowano site-packages w $($plikPth.Name) (odkomentowano 'import site')."
}

function Wylacz-ExternallyManaged {
    <#
        Buildy Pythona oparte na MSYS2 (jak w GIMP-ie) czasem maja plik
        "EXTERNALLY-MANAGED", ktory pip odczytuje jako zakaz instalacji poza
        wirtualnym srodowiskiem (blad "externally-managed-environment").
        Flaga --break-system-packages to obchodzi, ale dziala tylko w pip
        >= 23.0.1 - starsze pip zwraca "no such option". Jedyne wyjscie w
        takim wypadku to tymczasowe przemianowanie tego pliku.
    #>
    param([string]$PythonExe)

    $prefiks = Split-Path -Parent (Split-Path -Parent $PythonExe)
    $plikExternally = Get-ChildItem -Path $prefiks -Filter "EXTERNALLY-MANAGED" -Recurse -File -ErrorAction SilentlyContinue |
    Select-Object -First 1
    if (-not $plikExternally) {
        return
    }

    $nowaNazwa = "$($plikExternally.Name).bak"
    if (Test-Path (Join-Path $plikExternally.DirectoryName $nowaNazwa)) {
        return  # juz wczesniej wylaczone
    }

    Rename-Item -Path $plikExternally.FullName -NewName $nowaNazwa
    Write-Host "Tymczasowo wylaczono $($plikExternally.Name) (zmieniono nazwe na $nowaNazwa), zeby odblokowac pip install."
}

function Wlacz-ExternallyManaged {
    <#
        Przywraca plik EXTERNALLY-MANAGED wylaczony wczesniej przez
        Wylacz-ExternallyManaged (odwrotnosc tamtej operacji).
    #>
    param([string]$PythonExe)

    $prefiks = Split-Path -Parent (Split-Path -Parent $PythonExe)
    $plikBak = Get-ChildItem -Path $prefiks -Filter "EXTERNALLY-MANAGED.bak" -Recurse -File -ErrorAction SilentlyContinue |
    Select-Object -First 1
    if (-not $plikBak) {
        return
    }

    Rename-Item -Path $plikBak.FullName -NewName "EXTERNALLY-MANAGED"
    Write-Host "Przywrocono plik EXTERNALLY-MANAGED."
}

function Aktualizuj-Pip {
    <#
        Aktualizuje samo pip przed instalacja wymagan - starsze pip częsciej
        nie obsługuje --break-system-packages albo ma inne problemy z
        rozwiazywaniem zaleznosci.
    #>
    param([string]$PythonExe)

    & $PythonExe -m pip install --upgrade pip --break-system-packages
    if ($LASTEXITCODE -ne 0) {
        & $PythonExe -m pip install --upgrade pip
    }
}

function Zainstaluj-Wymagania {
    <#
        Nowsze pip (PEP 668) odmawia instalacji do "externally managed"
        środowiska (typowe dla Pythona GIMP-a/systemowego spoza virtualenv),
        chyba że doda się --break-system-packages. Starsze pip tej flagi nie
        zna, więc w razie błędu próbujemy jeszcze raz bez niej.
    #>
    param(
        [string]$PythonExe,
        [string]$SciezkaRequirements
    )

    & $PythonExe -m pip install --break-system-packages -r $SciezkaRequirements
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Instalacja z --break-system-packages nie powiodla sie - probuje bez tej flagi (starsze pip)."
        & $PythonExe -m pip install -r $SciezkaRequirements
    }
    return $LASTEXITCODE
}

if (-not $SkipSystem) {
    Write-Host "== Instalacja requirements.txt (Python systemowy) ==" -ForegroundColor Cyan
    $pythonSystemowy = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonSystemowy) {
        Write-Warning "Nie znaleziono 'python' w PATH - pomijam instalację systemową."
    }
    else {
        $kodWyjscia = Zainstaluj-Wymagania -PythonExe "python" -SciezkaRequirements (Join-Path $KatalogSkryptu "requirements.txt")
        if ($kodWyjscia -ne 0) {
            throw "Instalacja requirements.txt nie powiodła się (kod $kodWyjscia)."
        }
    }
    Write-Host ""
}

if (-not $SkipGimp) {
    Write-Host "== Instalacja requirements-gimp.txt (Python z GIMP-a) ==" -ForegroundColor Cyan
    $gimpPython = Znajdz-GimpPython
    if (-not $gimpPython) {
        Write-Warning (
            "Nie znaleziono python3.exe z GIMP-a. Uruchom skrypt ponownie z " +
            "-GimpPythonPath ""<ścieżka>\GIMP 3\bin\python3.exe""."
        )
    }
    else {
        Write-Host "Znaleziono: $gimpPython"
        Wlacz-SitePackages -PythonExe $gimpPython
        Wylacz-ExternallyManaged -PythonExe $gimpPython
        & $gimpPython -m ensurepip --upgrade
        Aktualizuj-Pip -PythonExe $gimpPython
        $kodWyjscia = Zainstaluj-Wymagania -PythonExe $gimpPython -SciezkaRequirements (Join-Path $KatalogSkryptu "requirements-gimp.txt")
        if ($kodWyjscia -ne 0) {
            throw "Instalacja requirements-gimp.txt nie powiodła się (kod $kodWyjscia)."
        }
        Wlacz-ExternallyManaged -PythonExe $gimpPython
    }
}

Write-Host ""
Write-Host "Gotowe." -ForegroundColor Green
