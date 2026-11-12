"""
Vérifie que l'environnement Python contient les dépendances de pyproject.toml, sans rien installer.

Lancé par lancer.bat avec l'environnement existant (python src/pnj_parlant/dependances.py) : bibliothèque
standard seulement, pour marcher même si le paquet pnj_parlant n'est pas installé. Vérifie la présence des
paquets (pas leur version), puis que l'application s'importe : un .venv endommagé est signalé.
Code de sortie 1 s'il manque une dépendance obligatoire (l'application ne démarrerait pas), 0 sinon :
sans les options voix ou stt, le navigateur lit les répliques et reconnaît la parole lui-même.
"""
import importlib
import re
import shutil
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

PROJET = "pnj-parlant"
OPTIONS = {"voix": "la synthèse vocale sur le serveur", "stt": "la reconnaissance vocale sur le serveur"}


def _nom(exigence):
    """« flask>=3.0 » → « flask »."""
    return re.match(r"[A-Za-z0-9._-]+", exigence.strip()).group(0)


def _installe(nom):
    try:
        distribution(nom)
        return True
    except PackageNotFoundError:
        return False


def manquantes(pyproject):
    """{"obligatoires": [...], "voix": [...], "stt": [...]} : paquets de pyproject.toml absents de l'environnement.
    Le paquet pnj-parlant lui-même compte parmi les obligatoires (python -m pnj_parlant en a besoin)."""
    with open(pyproject, "rb") as f:
        projet = tomllib.load(f)["project"]
    exigences = {"obligatoires": [PROJET, *projet.get("dependencies", [])]}
    for option in OPTIONS:
        exigences[option] = projet.get("optional-dependencies", {}).get(option, [])
    return {groupe: [n for n in map(_nom, liste) if not _installe(n)] for groupe, liste in exigences.items()}


def erreur_import(module="pnj_parlant.serveur"):
    """Erreur à l'import du module (None s'il s'importe) : des paquets présents peuvent être inutilisables, par
    exemple compilés pour une autre version de Python que celle de .venv."""
    try:
        importlib.import_module(module)
    except Exception as e:  # pylint: disable=broad-except
        return f"{type(e).__name__}: {e}"
    return None


def main():
    racine = Path(__file__).resolve().parents[2]
    absents = manquantes(racine / "pyproject.toml")
    if not absents["obligatoires"]:
        erreur = erreur_import()
        if erreur:
            print(f"\nL'environnement .venv est endommagé ({erreur}).")
            print("Supprimez le dossier .venv, puis relancez lancer.bat : il le recréera.\n")
            return 1
    if not any(absents.values()):
        return 0
    print()
    if absents["obligatoires"]:
        print("Dépendances manquantes, l'application ne peut pas démarrer :", ", ".join(absents["obligatoires"]))
    for option, role in OPTIONS.items():
        if absents[option]:
            print(f"Pour {role} (sinon le navigateur s'en charge), il manque :", ", ".join(absents[option]))
    commande = 'uv pip install -e ".[tout]"' if shutil.which("uv") else 'pip install -e ".[tout]"'
    print(f"Pour les installer dans .venv, depuis le dossier du projet, environnement activé : {commande}")
    print()
    return 1 if absents["obligatoires"] else 0


if __name__ == "__main__":
    # Lancé comme fichier : son dossier (config.py, voix.py…) ne doit pas masquer des modules du même nom.
    sys.path = [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
    sys.exit(main())
