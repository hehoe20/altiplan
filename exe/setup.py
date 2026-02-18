from distutils.core import setup
import py2exe

options = {
    "py2exe": {
        "packages": [
            "lxml",
            "requests",
            "bs4",
            "urllib3",
        ],
        "includes": [
            "lxml._elementpath",
            # requests kan trække ekstra ind; typisk fanger packages det,
            # men denne hjælper nogle gange:
            "requests",
            "bs4",
        ],
        # Hvis du vil undgå SSL/cert issues, kan certifi være relevant:
        # "packages": [..., "certifi"],
    }
}

setup(
    console=["altiplan.py"],   # tilpas til dit entry script
    options=options,
)
