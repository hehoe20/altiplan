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

# Argumenter (ingen manuel quoting nødvendig)
$args = @(
    "--afdeling",   $dept
    "--brugernavn", $user
    "--password",   $passPlain
    "--months",     "$months"
    "--savefile",   $save
)

Write-Host ""
Write-Host "Kører altiplan.exe..." -ForegroundColor Gray

# Maskér password i det der printes
$argsMasked = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "--password" -and ($i + 1) -lt $args.Count) {
        $argsMasked += "--password"
        $argsMasked += "******"
        $i++  # skip selve password-værdien
        continue
    }
    $argsMasked += $args[$i]
}

Write-Host "$exePath $($argsMasked -join ' ')" -ForegroundColor DarkGray
Write-Host ""

# Kør og vent (viser konsol-output fra exe)
$proc = Start-Process -FilePath $exePath -ArgumentList $args -NoNewWindow -Wait -PassThru
$exitCode = $proc.ExitCode

if ($exitCode -eq 0) {
    Write-Host "Færdig. Output gemt: $save" -ForegroundColor Green
} else {
    Write-Host "Fejl. Exit code: $exitCode" -ForegroundColor Red
}

# Pause før luk
Read-Host "Tryk Enter for at lukke"

exit $exitCode




