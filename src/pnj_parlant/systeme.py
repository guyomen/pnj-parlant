"""État de la machine affiché sur la page de jeu : carte graphique NVIDIA et modèles chargés par Ollama."""
import json
import subprocess
import urllib.request


def etat_gpu():
    """Utilisation de la carte NVIDIA via nvidia-smi ; None si absent ou en panne."""
    try:
        sortie = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3, check=True).stdout
        nom, usage, utilisee, totale = [x.strip() for x in sortie.splitlines()[0].split(",")]
        return {"nom": nom, "usage": int(usage), "memoire_mo": int(utilisee), "memoire_totale_mo": int(totale)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def etat_ollama(url):
    """{"ok": True, "charges": [{"nom", "vram_mo"}]} ou {"ok": False} si Ollama ne répond pas."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/ps", timeout=2) as r:
            charges = json.loads(r.read()).get("models", [])
        return {"ok": True, "charges": [
            {"nom": m["name"], "vram_mo": round(m.get("size_vram", 0) / 1e6)} for m in charges]}
    except (OSError, ValueError, KeyError):
        return {"ok": False}
