# altiplan_runner.ps1
# Runner til altiplan.exe med:
#  - Offline mode: brug eksisterende JSON + find + dato-filter
#  - Online mode: login + scrape + savefile
# Always includes: --simple-parsing

$ErrorActionPreference = "Stop"

function Prompt-RestartOrExit([int]$exitCode) {
    Write-Host ""
    Write-Host "Ønsker du at afslutte? Tryk A" -ForegroundColor Yellow
    Write-Host "Ønsker du at starte scriptet forfra? Tryk en vilkårlig anden tast" -ForegroundColor Yellow

    $k = [Console]::ReadKey($true)
    if ($k.KeyChar -eq 'A' -or $k.KeyChar -eq 'a') {
        exit $exitCode
    }
    # ellers: returner til caller som kan starte forfra
}

function Quote-Arg([string]$s) {
    if ($null -eq $s) { return '""' }
    # Escape " til \" og wrap i "
    $escaped = $s -replace '"', '\"'
    return '"' + $escaped + '"'
}

function Prompt-NonEmpty([string]$label) {
    while ($true) {
        $v = Read-Host $label
        if (-not [string]::IsNullOrWhiteSpace($v)) { return $v.Trim() }
        Write-Host "Feltet må ikke være tomt." -ForegroundColor Yellow
    }
}

function Prompt-YesNo([string]$label, [bool]$defaultYes) {
    $suffix = if ($defaultYes) { "[Y/n]" } else { "[y/N]" }
    while ($true) {
        $v = Read-Host "$label $suffix"
        if ([string]::IsNullOrWhiteSpace($v)) { return $defaultYes }
        $v = $v.Trim().ToLowerInvariant()
        if ($v -in @("y","yes","j","ja")) { return $true }
        if ($v -in @("n","no","nej")) { return $false }
        Write-Host "Svar venligst y/n." -ForegroundColor Yellow
    }
}

function Prompt-Months([int]$defaultMonths) {
    while ($true) {
        $v = Read-Host "Antal måneder (Enter for default: $defaultMonths)"
        if ([string]::IsNullOrWhiteSpace($v)) { return $defaultMonths }
        $v = $v.Trim()
        $n = 0
        if ([int]::TryParse($v, [ref]$n) -and $n -gt 0) { return $n }
        Write-Host "Ugyldigt tal. Skriv et helt tal > 0." -ForegroundColor Yellow
    }
}

function Prompt-Date([string]$label, [string]$defaultDate) {
    while ($true) {
        $v = Read-Host "$label (Enter for default: $defaultDate)"
        if ([string]::IsNullOrWhiteSpace($v)) { return $defaultDate }
        $v = $v.Trim()
        try {
            # Valider format YYYY-MM-DD
            [void][DateTime]::ParseExact($v, "yyyy-MM-dd", $null)
            return $v
        } catch {
            Write-Host "Ugyldig dato. Brug format YYYY-MM-DD." -ForegroundColor Yellow
        }
    }
}

function Prompt-FindTerms() {
    $v = Read-Host 'Søgeord til --find (flere adskilt af |). Enter for ingen'
    if ([string]::IsNullOrWhiteSpace($v)) { return @() }

    $terms = $v -split '\|' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    return ,$terms
}

function Run-Altiplan([string]$exePath, [string]$argString, [string]$argStringMasked) {
    Write-Host ""
    Write-Host "Kører altiplan.exe..." -ForegroundColor Gray
    Write-Host "$exePath $argStringMasked" -ForegroundColor DarkGray
    Write-Host ""

    $proc = Start-Process -FilePath $exePath -ArgumentList $argString -NoNewWindow -Wait -PassThru
    return $proc.ExitCode
}

# --- Defaults ---
$defaultSave   = Join-Path ([Environment]::GetFolderPath("Desktop")) "altiplan.json"
$defaultMonths = 24
$defaultStart  = "2025-01-01"
$defaultEnd    = "2025-12-31"

Write-Host "altiplan parser / personlig statistik" -ForegroundColor Cyan
Write-Host ""

# Find altiplan.exe (samme mappe som scriptet)
$exePath = Join-Path $PSScriptRoot "altiplan.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "Kunne ikke finde altiplan.exe her: $exePath" -ForegroundColor Red
    Write-Host "Læg altiplan.exe i samme mappe som dette script." -ForegroundColor Yellow
    Read-Host "Tryk Enter for at lukke"
    exit 1
}

while ($true) {

	$useExisting = $false
	if (Test-Path $defaultSave) {
		$useExisting = Prompt-YesNo "altiplan.json findes på standard-sti: $defaultSave`nØnsker du at arbejde med tidligere gemte json?" $true
	}

	if ($useExisting) {
		# --- OFFLINE MODE ---
		$terms = Prompt-FindTerms
		$startDate = Prompt-Date "Startdato" $defaultStart
		$endDate   = Prompt-Date "Slutdato" $defaultEnd

		# Byg arg string (quote alt, + always --simple-parsing)
		$argString = ""
		$argString += "--inputfile " + (Quote-Arg $defaultSave) + " "
		$argString += "--simple-parsing "
		$argString += "--komb "
		$argString += "--startdate " + (Quote-Arg $startDate) + " "
		$argString += "--enddate "   + (Quote-Arg $endDate)   + " "

		foreach ($t in $terms) {
			$argString += "--find " + (Quote-Arg $t) + " "
		}

		$argString = $argString.Trim()

		# Maskeret print (ingen password her, men behold mønster)
		$argStringMasked = $argString

		$exitCode = Run-Altiplan $exePath $argString $argStringMasked

		if ($exitCode -eq 0) {
			Write-Host "Færdig (offline). Input: $defaultSave" -ForegroundColor Green
		} else {
			Write-Host "Fejl (offline). Exit code: $exitCode" -ForegroundColor Red
		}

		Prompt-RestartOrExit $exitCode
		continue
	}

	# --- ONLINE MODE (LOGIN + SAVE) ---
	$dept = Prompt-NonEmpty "Afdeling (fx od207)"
	$user = Prompt-NonEmpty "Brugernavn"

	$secure = Read-Host "Kode (password)" -AsSecureString
	if ($secure.Length -eq 0) {
		Write-Host "Password må ikke være tomt." -ForegroundColor Red
		Read-Host "Tryk Enter for at lukke"
		exit 1
	}
	$passPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
		[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
	)

	$months = Prompt-Months $defaultMonths

	$save = Read-Host "Output fil (Enter for default: $defaultSave)"
	if ([string]::IsNullOrWhiteSpace($save)) { $save = $defaultSave }

	# Byg arg string (quote alt, + always --simple-parsing)
	$argString =
		"--afdeling "   + (Quote-Arg $dept)     + " " +
		"--brugernavn " + (Quote-Arg $user)     + " " +
		"--password "   + (Quote-Arg $passPlain)+ " " +
		"--months "     + (Quote-Arg "$months") + " " +
		"--savefile "   + (Quote-Arg $save)     + " " +
		"--simple-parsing"

	# Maskér password i det der printes
	$argStringMasked = $argString -replace '(--password\s+)"[^"]*"', '$1"******"'

	$exitCode = Run-Altiplan $exePath $argString $argStringMasked

	if ($exitCode -eq 0) {
		Write-Host "Færdig. Output gemt: $save" -ForegroundColor Green
	} else {
		Write-Host "Fejl. Exit code: $exitCode" -ForegroundColor Red
	}

    Prompt-RestartOrExit $exitCode
    continue
}

