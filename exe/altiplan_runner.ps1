# altiplan_runner.ps1
# Spørger efter afdeling/brugernavn/password/fil + antal måneder (default 24) og kalder altiplan.exe

$ErrorActionPreference = "Stop"

function Prompt-NonEmpty([string]$label) {
    while ($true) {
        $v = Read-Host $label
        if (-not [string]::IsNullOrWhiteSpace($v)) { return $v.Trim() }
        Write-Host "Feltet må ikke være tomt." -ForegroundColor Yellow
    }
}

function Prompt-Months([int]$defaultMonths) {
    while ($true) {
        $v = Read-Host "Antal måneder (Enter for default: $defaultMonths)"
        if ([string]::IsNullOrWhiteSpace($v)) { return $defaultMonths }

        $v = $v.Trim()
        $n = 0
        if ([int]::TryParse($v, [ref]$n) -and $n -gt 0) {
            return $n
        }
        Write-Host "Ugyldigt tal. Skriv et helt tal > 0." -ForegroundColor Yellow
    }
}

# Default savefile: Desktop\altiplan.json
$defaultSave = Join-Path ([Environment]::GetFolderPath("Desktop")) "altiplan.json"
$defaultMonths = 24

Write-Host "Altiplan - simpel runner" -ForegroundColor Cyan
Write-Host ""

$dept = Prompt-NonEmpty "Afdeling (fx od207)"
$user = Prompt-NonEmpty "Brugernavn"

# Password (skjult input)
$secure = Read-Host "Kode (password)" -AsSecureString
if ($secure.Length -eq 0) {
    Write-Host "Password må ikke være tomt." -ForegroundColor Red
    exit 1
}
$passPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
)

# Months (default 24)
$months = Prompt-Months $defaultMonths

# Filnavn (default desktop)
$save = Read-Host "Output fil (Enter for default: $defaultSave)"
if ([string]::IsNullOrWhiteSpace($save)) { $save = $defaultSave }

# Find altiplan.exe (samme mappe som scriptet)
$exePath = Join-Path $PSScriptRoot "altiplan.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "Kunne ikke finde altiplan.exe her: $exePath" -ForegroundColor Red
    Write-Host "Læg altiplan.exe i samme mappe som dette script, eller ret \$exePath." -ForegroundColor Yellow
    exit 1
}

function Quote-Arg([string]$s) {
    if ($null -eq $s) { return '""' }
    # escape " til \" og wrap i "
    $escaped = $s -replace '"', '\"'
    return '"' + $escaped + '"'
}

# byg en korrekt argument-streng (ALT quoter vi)
$argString =
    "--afdeling "   + (Quote-Arg $dept)     + " " +
    "--brugernavn " + (Quote-Arg $user)     + " " +
    "--password "   + (Quote-Arg $passPlain)+ " " +
    "--months "     + (Quote-Arg "$months") + " " +
    "--savefile "   + (Quote-Arg $save) + " " +
    "--simple-parsing"

# print en maskeret version (så password ikke vises)
$argStringMasked = $argString -replace '(--password\s+)"[^"]*"', '$1"******"'

Write-Host ""
Write-Host "Kører altiplan.exe..." -ForegroundColor Gray
Write-Host "$exePath $argStringMasked" -ForegroundColor DarkGray
Write-Host ""

$proc = Start-Process -FilePath $exePath -ArgumentList $argString -NoNewWindow -Wait -PassThru
$exitCode = $proc.ExitCode

if ($exitCode -eq 0) {
    Write-Host "Færdig. Output gemt: $save" -ForegroundColor Green
} else {
    Write-Host "Fejl. Exit code: $exitCode" -ForegroundColor Red
}

# Pause før luk
Read-Host "Tryk Enter for at lukke"

exit $exitCode



