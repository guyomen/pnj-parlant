"""
Test de bout en bout de la page de jeu : un vrai navigateur (Edge ou Chrome, sans écran) joue comme un
joueur avec les lieux (arrivée, aborder un PNJ, « allons à la forge », compagnon qui suit ou reste),
puis importe une conversation exportée.

    python tests/e2e/lancer.py                 # depuis la racine du projet (Node 22+ et Edge ou Chrome)
    NAVIGATEUR=/chemin/vers/chrome python tests/e2e/lancer.py

Le serveur tourne sur les données de tests/e2e/donnees (copiées dans un dossier temporaire), avec un faux
Ollama qui répond en citant le PNJ et le lieu reçus dans ses consignes. Ports utilisés : 5917 et 5918.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ICI = Path(__file__).parent
RACINE = ICI.parents[1]
NAVIGATEURS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge",
]


def navigateur():
    chemin = os.environ.get("NAVIGATEUR") or next((n for n in NAVIGATEURS if Path(n).exists()), None)
    if not chemin:
        raise SystemExit("Aucun navigateur trouvé : indiquez-le avec la variable NAVIGATEUR.")
    return chemin


def attendre(url, delai=30):
    for _ in range(delai * 5):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise SystemExit(f"{url} ne répond pas.")


def main():
    # ignore_cleanup_errors : le navigateur garde son profil ouvert quelques instants après sa fermeture
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        dossier = Path(tmp) / "donnees"
        shutil.copytree(ICI / "donnees", dossier)
        env = {**os.environ, "PYTHONPATH": str(RACINE / "src")}
        processus = [
            subprocess.Popen([sys.executable, str(ICI / "faux_ollama.py"), str(dossier / "journal.jsonl")],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            subprocess.Popen([sys.executable, "-m", "pnj_parlant"], cwd=dossier, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        ]
        try:
            attendre("http://127.0.0.1:5918/api/tags")
            attendre("http://127.0.0.1:5917/")
            code = subprocess.run(["node", str(ICI / "parcours_lieux.mjs"), navigateur(),
                                   str(Path(tmp) / "profil"),
                                   str(dossier / "conversation-import.txt")], timeout=120).returncode
        finally:
            for p in processus:
                p.kill()
    sys.exit(code)


if __name__ == "__main__":
    main()
