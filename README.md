# altiplan/hosinfo personlig statistik
![](https://github.com/hehoe20/altiplan/blob/main/Screenshot.jpg?raw=true)
Eksemplet ovenfor er personlig statistik for en 10 dages periode.   

## alternativet til python
Vil du ikke download og installere python mm nedenfor, kan du downloade altiplan.exe fra mappen exe. Den kan køres direkte på en windows computer.   
Downloade evt også gui.exe fra mappen gui4exe og læg den i samme mappe som altiplan.exe   

## hvad skal du bruge:
Installer først python og derefter requirements med pip
```bash
pip install -r /path/to/requirements.txt
```

Kør for hjælp:
```bash
C:\>python altiplan.py -h
usage: altiplan.py [-h] [--inputfile INPUTFILE] [--savefile SAVEFILE] [--find FIND] [--months MONTHS] [--komb [KOMB]] [--afdeling AFDELING] [--brugernavn BRUGERNAVN] [--password PASSWORD] [--insecure]
                   [--expand-output] [--no-summary] [--no-filter] [--include-time] [--simple-parsing] [--startdate STARTDATE] [--enddate ENDDATE]

ALTIPLAN parser v1.0 til personlig statistik af Henrik Højgaard (c) 2026

optional arguments:
  -h, --help            show this help message and exit
  --inputfile INPUTFILE
                        Læs raw kalender rows fra JSON fil og spring login over
  --savefile SAVEFILE   Gem raw kalender rows som JSON til den angivne fil
  --find FIND           Søgeord til statistik (præcis match). Kan angives flere gange. Ex: --find "VITA dagtid"
  --months MONTHS       Antal måneder der skal hentes (int > 0). Bruges kun ved login. Default=1
  --komb [KOMB]         Tæl dage hvor ALLE 3-cifrede koder forekommer. Brug: --komb (default 100|290 sv.t døgnvagt) eller --komb 100|290|700
  --afdeling AFDELING   Afdelingskode (fx od207). Bruges kun ved login.
  --brugernavn BRUGERNAVN
                        Bruges kun ved login.
  --password PASSWORD   Bruges kun ved login.
  --insecure            Svar til curl -k: disable TLS cert verification (frarådes). Bruges kun ved login.
  --expand-output       Print expanded rows som JSON til stdout (kan være stor), brug evt dato selektering.
                        Tillader ikke summary og find.
  --no-summary          Slå summeret statistik fra (default er at den vises).
  --no-filter           Slå filtrering fra i summary (default filtrerer linjer fra som starter med matematiske operatorer eller er rene 3-cifrede tal).
  --include-time        Medtag også klokkeslæt-linjer i summary (default viser kun ikke-tidslinjer).
  --simple-parsing      Brug simpel offline parsing af ps (split kun på <br/> og linjeskift).
  --startdate STARTDATE
                        Startdato (inkl.), format YYYY-MM-DD. Filtrerer --summary/--find/--expand-output.
  --enddate ENDDATE     Slutdato (inkl.), format YYYY-MM-DD. Filtrerer --summary/--find/--expand-output.

Altiplan: scrape rå kalender data og/eller kør offline stats på gemt JSON.
```
Eksempel der henter de sidste 24 måneder og gemmer personlige kalenderdata til output.json (og for praktiske årsager og hastighed, da kan det anbefales at køre denne kommando én gang, med måske 48 mdr eller hvad man nu synes. Derfra kan man arbejde videre med data lokalt)
```bash
python altiplan.py --afdeling DEPT --brugernavn USERNAME --password PASSWORD --find "VITA dagtid" --months 24 --savefile altiplan.json
```
Eksempler der anvender de gemte json data
```bash
python altiplan.py --inputfile altiplan.json --startdate 2026-01-01 --enddate 2026-01-31 --simple-parsing
```
```bash
python altiplan.py --inputfile altiplan.json --startdate 2025-01-01 --enddate 2025-12-31 --simple-parsing --komb
```
```bash
python altiplan.py --inputfile altiplan.json --no-summary --startdate 2025-01-01 --enddate 2025-12-31 --find "VITA dagtid" --find "ITA dagtid"
```
```bash
python altiplan.py --inputfile altiplan.json --no-filter --include-time
```
Eksporter data som enkelt linjer json - kan importeres i fx. excel.   
formatet er [dato, tekst linje fra preparsing html, lørdag/søndag:true/false, helligdag:true/false, pre-parsing html]   
```bash
python altiplan.py --inputfile altiplan.json --startdate 2026-01-01 --enddate 2026-01-31 --expand-output > single_lines.json
```
