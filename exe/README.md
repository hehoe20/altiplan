# how to use (on windows med powershell)
download **altiplan.exe** og **altiplan_runner.ps1** til samme mappe   
![](https://raw.githubusercontent.com/hehoe20/altiplan/refs/heads/main/exe/Screenshot3.jpg)
{kør ***altiplan_runner.ps1*** med powershell (evt via hø. klik og vælg kør med powershell, se ovenfor)   
Følg prompts, første gang, indtast credentials og generer json filen (hvis du vil arbejde videre med den, da må du ikke ændre sti/filnavn, skal være default)   
![](https://raw.githubusercontent.com/hehoe20/altiplan/refs/heads/main/exe/Screenshot1.jpg)
![](https://raw.githubusercontent.com/hehoe20/altiplan/refs/heads/main/exe/Screenshot2.jpg)
# py2exe compile - creates .exe but also multiple files in dist
pip install py2exe      
copy altiplan.py to this directory and run   
python setup.py install   
python setup.py py2exe   
# pyinstaller - creates single .exe in dist
python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib file   
python -m PyInstaller --onefile --clean --noconfirm altiplan.py   
