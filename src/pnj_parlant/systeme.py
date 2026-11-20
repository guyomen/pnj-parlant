"""État de la machine affiché sur la page Options : carte graphique (NVIDIA, AMD, Intel) et modèles chargés par
Ollama.

Carte graphique, par ordre de préférence :
- nvidia-smi (NVIDIA, Windows et Linux) : activité et mémoire vidéo ;
- Linux, pilote amdgpu (/sys/class/drm/card*/device) : activité et mémoire vidéo, sans outil à installer ;
  autre carte (Intel…) : son fabricant seulement ;
- Windows, registre des cartes d'affichage : nom et mémoire vidéo dédiée, sans activité (Windows ne la donne
  que par des compteurs lents et traduits selon la langue du système).
Chaque valeur inconnue vaut None : {"nom", "usage", "memoire_mo", "memoire_totale_mo"}.
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

FABRICANTS = {"10de": "NVIDIA", "1002": "AMD", "8086": "Intel"}  # identifiants PCI des fabricants
DRM = Path("/sys/class/drm")
# Registre : une sous-clé (0000, 0001…) par carte de la classe « Cartes graphiques »
CLE_CARTES = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
MO = 1024 * 1024


def etat_gpu():
    """Carte graphique la mieux renseignée ; None si aucune n'est trouvée."""
    gpu = gpu_nvidia()
    if gpu is None and sys.platform.startswith("linux"):
        gpu = gpu_linux()
    if gpu is None and os.name == "nt":
        gpu = gpu_windows()
    return gpu


def gpu_nvidia():
    """Utilisation de la carte NVIDIA via nvidia-smi ; None si absent ou en panne."""
    try:
        sortie = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3, check=True).stdout
        nom, usage, utilisee, totale = [x.strip() for x in sortie.splitlines()[0].split(",")]
        return {"nom": nom, "usage": int(usage), "memoire_mo": int(utilisee), "memoire_totale_mo": int(totale)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _lire(fichier):
    try:
        return fichier.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _entier(texte):
    try:
        return int(texte)
    except (TypeError, ValueError):
        return None


def gpu_linux(racine=DRM):
    """Carte graphique d'après le noyau Linux : le pilote amdgpu y publie activité (gpu_busy_percent) et mémoire
    vidéo (mem_info_vram_*) ; les autres cartes, leur fabricant seulement. La carte qui a le plus de mémoire vidéo
    l'emporte (carte dédiée plutôt que puce intégrée). None si aucune."""
    cartes = []
    try:
        dossiers = sorted(racine.glob("card[0-9]*/device"))
    except OSError:
        return None
    for d in dossiers:
        if "-" in d.parent.name:  # card0-HDMI-A-1… : sorties d'écran, pas des cartes
            continue
        fabricant = (_lire(d / "vendor") or "").lower().removeprefix("0x")
        if not fabricant:
            continue
        totale, utilisee = _entier(_lire(d / "mem_info_vram_total")), _entier(_lire(d / "mem_info_vram_used"))
        nom = _lire(d / "product_name") or f"Carte {FABRICANTS.get(fabricant, 'graphique')}"
        cartes.append({"nom": nom, "usage": _entier(_lire(d / "gpu_busy_percent")),
                       "memoire_mo": utilisee // MO if utilisee is not None and totale else None,
                       "memoire_totale_mo": totale // MO if totale else None})
    return max(cartes, key=lambda c: c["memoire_totale_mo"] or 0, default=None)


def cartes_du_registre():
    """Cartes d'affichage déclarées dans le registre de Windows : [{nom, id_materiel, memoire (octets ou None)}]."""
    import winreg  # Windows seulement
    cartes = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLE_CARTES) as classe:
        i = 0
        while True:
            try:
                nom_cle = winreg.EnumKey(classe, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(classe, nom_cle) as cle:
                    valeurs = {}
                    for nom in ("DriverDesc", "MatchingDeviceId", "HardwareInformation.qwMemorySize",
                                "HardwareInformation.MemorySize"):
                        try:
                            valeurs[nom] = winreg.QueryValueEx(cle, nom)[0]
                        except OSError:
                            pass
            except OSError:  # « Properties » et autres sous-clés protégées
                continue
            if "DriverDesc" not in valeurs:
                continue
            memoire = valeurs.get("HardwareInformation.qwMemorySize")
            if memoire is None:  # ancien format : DWORD, ou 4 ou 8 octets bruts
                ancienne = valeurs.get("HardwareInformation.MemorySize")
                memoire = int.from_bytes(ancienne, "little") if isinstance(ancienne, bytes) else ancienne
            cartes.append({"nom": valeurs["DriverDesc"], "id_materiel": valeurs.get("MatchingDeviceId") or "",
                           "memoire": memoire if isinstance(memoire, int) and memoire > 0 else None})
    return cartes


def gpu_windows(lire=cartes_du_registre):
    """Nom et mémoire vidéo dédiée de la carte graphique d'après le registre (toutes marques), sans activité.
    Cartes virtuelles (affichage de base, bureau à distance : pas de « PCI\\ ») ignorées ; la carte qui a le plus de
    mémoire dédiée l'emporte. None si aucune."""
    try:
        cartes = [c for c in lire() if str(c.get("id_materiel", "")).upper().startswith("PCI\\")]
    except (OSError, ImportError):
        return None
    if not cartes:
        return None
    carte = max(cartes, key=lambda c: c.get("memoire") or 0)
    return {"nom": carte["nom"], "usage": None, "memoire_mo": None,
            "memoire_totale_mo": carte["memoire"] // MO if carte.get("memoire") else None}


def etat_ollama(url):
    """{"ok": True, "charges": [{"nom", "vram_mo"}]} ou {"ok": False} si Ollama ne répond pas."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/ps", timeout=2) as r:
            charges = json.loads(r.read()).get("models", [])
        return {"ok": True, "charges": [
            {"nom": m["name"], "vram_mo": round(m.get("size_vram", 0) / 1e6)} for m in charges]}
    except (OSError, ValueError, KeyError):
        return {"ok": False}
