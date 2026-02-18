# py2exe compile - creates .exe but also multiple files in dist
pip install py2exe      
copy altiplan.py to this directory and run   
python setup.py install   
python setup.py py2exe   
# pyinstaller - creates single .exe in dist
python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib file   
python -m PyInstaller --onefile --clean --noconfirm altiplan.py   
