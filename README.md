Install python og requirements   
```bash
pip install -r /path/to/requirements.txt
```

Execute for help
```bash
C:\>python altiplan.py -h
usage: altiplan.py [-h] --afdeling AFDELING --brugernavn BRUGERNAVN --password PASSWORD [--savefile SAVEFILE]
                   [--find FIND] [--insecure] [--months MONTHS]

Altiplan login via WP admin-ajax + ekstra ajax-kald

optional arguments:
  -h, --help            show this help message and exit
  --afdeling AFDELING   Afd (fx od207)
  --brugernavn BRUGERNAVN
  --password PASSWORD
  --savefile SAVEFILE   Gem all_rows som JSON til denne fil (fx rows.json)
  --find FIND           Søgetekst til statistik. Kan angives flere gange. Ex: --find "VITA dagtid"
  --insecure            Svar til curl -k: disable TLS cert verification (frarådes)
  --months MONTHS       Antal måneder der skal hentes (int > 0). Default=1
```
Example getting 12 months
```bash
python altiplan.py --afdeling DEPT --brugernavn USERNAME --password PASSWORD --find "VITA dagtid" --months 12 --savefile output.json
```
