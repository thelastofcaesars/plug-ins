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

    $kandydaci = @(
        "$env:ProgramFiles\GIMP 3\bin\python3.exe",
        "${env:ProgramFiles(x86)}\GIMP 3\bin\python3.exe",
        "$env:LocalAppData\Programs\GIMP 3\bin\python3.exe"
    )
    foreach ($sciezka in $kandydaci) {
        if ($sciezka -and (Test-Path $sciezka)) {
            return $sciezka
        }
    }

    # Ostatnia deska ratunku: przeszukaj foldery "GIMP*" na wszystkich dyskach lokalnych.
    $dyski = Get-PSDrive -PSProvider FileSystem | Where-Object { Test-Path $_.Root }
    foreach ($dysk in $dyski) {
        $znaleziony = Get-ChildItem -Path $dysk.Root -Filter "GIMP*" -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "bin\python3.exe" } |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1
        if ($znaleziony) {
            return $znaleziony
        }
    }

    return $null
}

function Wlacz-SitePackages {
    <#
        GIMP 3 na Windows dodaje obok python3.exe plik "python3*._pth", ktory
        domyslnie ma zakomentowana linie "import site". Bez niej katalog
        site-packages nie jest w ogole dolaczany do sys.path, wiec nawet po
        "pip install" biblioteki (np. openpyxl) i tak nie zaimportuja sie w
        pluginach GIMP-a. Trzeba odkomentowac te linie raz - robimy to tutaj.
    #>
    param([string]$PythonExe)

    $katalogBin = Split-Path -Parent $PythonExe
    $plikPth = Get-ChildItem -Path $katalogBin -Filter "python3*._pth" -ErrorAction SilentlyContinue |
    Select-Object -First 1
    if (-not $plikPth) {
        Write-Host "Nie znaleziono pliku python3._pth - pomijam ten krok."
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

if (-not $SkipSystem) {
    Write-Host "== Instalacja requirements.txt (Python systemowy) ==" -ForegroundColor Cyan
    $pythonSystemowy = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonSystemowy) {
        Write-Warning "Nie znaleziono 'python' w PATH - pomijam instalację systemową."
    }
    else {
        & python -m pip install -r (Join-Path $KatalogSkryptu "requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "Instalacja requirements.txt nie powiodła się (kod $LASTEXITCODE)."
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
        & $gimpPython -m ensurepip --upgrade
        & $gimpPython -m pip install -r (Join-Path $KatalogSkryptu "requirements-gimp.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "Instalacja requirements-gimp.txt nie powiodła się (kod $LASTEXITCODE)."
        }
    }
}

Write-Host ""
Write-Host "Gotowe." -ForegroundColor Green
