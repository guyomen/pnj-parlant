"""
Test de bout en bout de la page de jeu : un vrai navigateur (Edge ou Chrome, sans écran) joue comme un
joueur avec les lieux (arrivée, aborder un PNJ, « allons à la forge », compagnon qui suit ou reste),
puis importe une conversation exportée.

    python tests/e2e/lancer.py                 # depuis la racine du projet (Node 22+ et Edge ou Chrome)
    NAVIGATEUR=/chemin/vers/chrome python tests/e2e/lancer.py

Le serveur tourne sur les données de tests/e2e/donnees (copiées dans un dossier temporaire), avec un faux
Ollama qui répond en citant le PNJ et le lieu reçus dans ses consignes.

Ports (variables d'environnement) : PNJ_E2E_PORT_SERVEUR (5917), PNJ_E2E_PORT_OLLAMA (5918) et
PNJ_E2E_PORT_DEVTOOLS (9333). Si le test échoue, les sorties du serveur et du faux Ollama sont affichées.
"""
import os
import shutil
import socket
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


def port(variable, defaut):
    return int(os.environ.get(variable, defaut))


def occupe(numero):
    """Vrai si quelque chose écoute déjà sur ce port : on testerait alors un autre serveur que le nôtre."""
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", numero)) == 0


def attendre(url, processus, delai=30):
    """Attend que `url` réponde ; s'arrête dès qu'un des processus lancés est mort (au lieu de tourner contre un
    autre serveur resté sur le port, ou d'attendre 30 s pour rien)."""
    for _ in range(delai * 5):
        for p in processus:
            if p.poll() is not None:
                raise RuntimeError(f"un processus de test s'est arrêté (code {p.returncode}) avant que {url} réponde.")
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} ne répond pas.")


def afficher_journaux(journaux):
    for nom, chemin in journaux.items():
        texte = chemin.read_text(encoding="utf-8", errors="replace") if chemin.exists() else ""
        print(f"\n--- {nom} (fin du journal) ---\n{texte[-4000:] or '(vide)'}", file=sys.stderr)


def main():
    p_serveur, p_ollama = port("PNJ_E2E_PORT_SERVEUR", 5917), port("PNJ_E2E_PORT_OLLAMA", 5918)
    p_devtools = port("PNJ_E2E_PORT_DEVTOOLS", 9333)
    for n in (p_serveur, p_ollama, p_devtools):
        if occupe(n):
            raise SystemExit(f"Le port {n} est déjà utilisé : fermez ce qui l'occupe, ou changez-le avec "
                             "PNJ_E2E_PORT_SERVEUR, PNJ_E2E_PORT_OLLAMA ou PNJ_E2E_PORT_DEVTOOLS.")
    code = 1
    # ignore_cleanup_errors : le navigateur garde son profil ouvert quelques instants après sa fermeture
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        dossier = Path(tmp) / "donnees"
        shutil.copytree(ICI / "donnees", dossier)
        config = dossier / "config.toml"  # les ports de la copie suivent les variables d'environnement
        config.write_text(config.read_text(encoding="utf-8").replace("5918", str(p_ollama))
                          .replace("5917", str(p_serveur)), encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(RACINE / "src"), "PYTHONUNBUFFERED": "1",
               "PNJ_E2E_PORT_OLLAMA": str(p_ollama), "PNJ_E2E_PORT_SERVEUR": str(p_serveur),
               "PNJ_E2E_PORT_DEVTOOLS": str(p_devtools)}
        journaux = {"serveur": Path(tmp) / "serveur.log", "faux Ollama": Path(tmp) / "faux_ollama.log"}
        processus = []
        with open(journaux["faux Ollama"], "wb") as j_ollama, open(journaux["serveur"], "wb") as j_serveur:
            try:
                processus.append(subprocess.Popen(
                    [sys.executable, str(ICI / "faux_ollama.py"), str(dossier / "journal.jsonl")], env=env,
                    stdout=j_ollama, stderr=subprocess.STDOUT))
                processus.append(subprocess.Popen([sys.executable, "-m", "pnj_parlant"], cwd=dossier, env=env,
                                                  stdout=j_serveur, stderr=subprocess.STDOUT))
                attendre(f"http://127.0.0.1:{p_ollama}/api/tags", processus)
                attendre(f"http://127.0.0.1:{p_serveur}/", processus)
                code = subprocess.run(["node", str(ICI / "parcours_lieux.mjs"), navigateur(),
                                       str(Path(tmp) / "profil"),
                                       str(dossier / "conversation-import.txt")], env=env, timeout=120).returncode
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                print(f"e2e : {e}", file=sys.stderr)
                code = 1
            finally:
                for p in processus:
                    p.kill()
                    p.wait()
        if code:
            afficher_journaux(journaux)
    sys.exit(code)


if __name__ == "__main__":
    main()
