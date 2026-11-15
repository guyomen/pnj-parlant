"""Lot 9 : certificat HTTPS réel (sans pyopenssl), licences et métadonnées du paquet."""
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from pnj_parlant import config as configuration
from pnj_parlant import serveur

RACINE = Path(__file__).parents[1]
PYPROJECT = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))


def test_certificat_https_genere_sans_pyopenssl(tmp_path):
    """Le vrai certificat auto-signé se fabrique avec `cryptography` seul (pyopenssl n'est plus nécessaire)."""
    code = ("import sys; sys.modules['OpenSSL'] = None; "
            "from pnj_parlant import config, serveur; import pathlib; "
            "c, k = serveur.certificat(config.Config({}, pathlib.Path(sys.argv[1]))); print(c); print(k)")
    sortie = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, timeout=120,
                            env={**os.environ, "PYTHONPATH": str(RACINE / "src")})
    assert sortie.returncode == 0, sortie.stderr
    cert, cle = sortie.stdout.split()
    assert Path(cert).read_text().startswith("-----BEGIN CERTIFICATE-----")
    assert "PRIVATE KEY" in Path(cle).read_text()


def test_certificat_reutilise_les_fichiers_existants(tmp_path):
    cfg = configuration.Config({}, tmp_path)
    premier = serveur.certificat(cfg)
    contenu = Path(premier[0]).read_bytes()
    assert serveur.certificat(cfg) == premier and Path(premier[0]).read_bytes() == contenu


def test_licence_gpl_et_polices_ofl():
    assert PYPROJECT["project"]["license"] == "GPL-3.0-or-later"
    licence = (RACINE / "LICENSE").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in licence and "Version 3, 29 June 2007" in licence
    assert "END OF TERMS AND CONDITIONS" in licence
    ofl = RACINE / "src" / "pnj_parlant" / "static" / "fonts" / "OFL.txt"
    texte = ofl.read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in texte and "Alegreya Sans" in texte and "IM Fell English" in texte
    # le fichier part avec le paquet (package-data « static/** ») et avec ses métadonnées
    assert "static/**/*" in PYPROJECT["tool"]["setuptools"]["package-data"]["pnj_parlant"]
    assert "src/pnj_parlant/static/fonts/OFL.txt" in PYPROJECT["project"]["license-files"]


def test_dependances_bornees_et_sans_pyopenssl():
    p = PYPROJECT["project"]
    toutes = list(p["dependencies"]) + [d for lot in p["optional-dependencies"].values() for d in lot]
    assert not any(d.lower().startswith("pyopenssl") for d in toutes)
    assert any(d.startswith("cryptography") for d in p["dependencies"])
    sans_borne = [d for d in toutes if "<" not in d and not d.startswith("pnj-parlant[")]
    assert sans_borne == []
