"""
Hook Claude Code (événement Stop) : garde la documentation à jour automatiquement.

Si du code a changé dans l'arbre de travail (fichiers non commités) sans qu'aucun fichier de documentation n'ait
changé, Claude est renvoyé au travail une fois, avec la consigne de mettre à jour README.md, docs/ et les règles
de .claude/. Il ne bloque jamais deux fois de suite (stop_hook_active), ni hors d'un dépôt git.
Configuré dans .claude/settings.json ; testé par tests/test_hook_doc.py.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

CODE = ("src/", "config.toml.example", "pyproject.toml", "lancer.bat", "docker-compose.yml", "scripts/")
DOC = ("README.md", "docs/", ".claude/CLAUDE.md", ".claude/rules/")


def racine_du_projet():
    """Racine du dépôt : CLAUDE_PROJECT_DIR (fourni par Claude Code), sinon deux niveaux au-dessus de ce fichier.
    Le hook s'exécute dans le dossier courant de la session, qui peut avoir changé (cd) en cours de route."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])


def fichiers_modifies():
    """Chemins modifiés, ajoutés ou nouveaux d'après git status (vide hors d'un dépôt git)."""
    try:
        sortie = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                cwd=racine_du_projet(), capture_output=True, text=True, encoding="utf-8",
                                timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    chemins = []
    for ligne in sortie.splitlines():
        chemin = ligne[3:].strip().strip('"')
        chemins.append(chemin.split(" -> ")[-1])  # renommage : nouveau nom
    return chemins


def main():
    try:
        entree = json.load(sys.stdin)
    except ValueError:
        entree = {}
    if entree.get("stop_hook_active"):
        return 0  # déjà relancé par ce hook : on laisse s'arrêter
    modifies = fichiers_modifies()
    code = [c for c in modifies if c.startswith(CODE) and "__pycache__" not in c]
    doc = [c for c in modifies if c.startswith(DOC)]
    if code and not doc:
        print(json.dumps({
            "decision": "block",
            "reason": ("Du code a changé sans la documentation (" + ", ".join(code[:6])
                       + (", …" if len(code) > 6 else "") + "). Mets à jour ce qui en dépend : README.md, "
                       "docs/installation-windows.md, .claude/CLAUDE.md et les règles de .claude/rules/ "
                       "(voir la convention de CLAUDE.md). Si rien ne change pour l'utilisateur ni pour le contexte, "
                       "dis-le en une phrase et termine."),
        }))  # ASCII échappé (é…) : lisible quel que soit l'encodage de la console (cp1252 sous Windows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
