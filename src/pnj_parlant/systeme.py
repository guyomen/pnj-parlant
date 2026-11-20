"""État de la machine affiché sur la page Options : carte graphique (NVIDIA, AMD, Intel) et modèles chargés par
Ollama.

Carte graphique, par ordre de préférence :
- nvidia-smi (NVIDIA, Windows et Linux) : activité et mémoire vidéo ;
- Linux, pilote amdgpu (/sys/class/drm/card*/device) : activité et mémoire vidéo, sans outil à installer ;
  autre carte (Intel…) : son fabricant seulement ;
- Windows, toutes marques : nom et mémoire vidéo dédiée dans le registre des cartes d'affichage ; activité et
  mémoire utilisée par les compteurs de performance « GPU Engine » et « GPU Adapter Memory », lus par l'API PDH
  (pdh.dll, ctypes) sous leurs noms anglais, quelle que soit la langue du système.
Chaque valeur inconnue vaut None : {"nom", "usage", "memoire_mo", "memoire_totale_mo"}.
"""
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

FABRICANTS = {"10de": "NVIDIA", "1002": "AMD", "8086": "Intel"}  # identifiants PCI des fabricants
DRM = Path("/sys/class/drm")
# Registre : une sous-clé (0000, 0001…) par carte de la classe « Cartes graphiques »
CLE_CARTES = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
MO = 1024 * 1024
# Compteurs de Windows (noms anglais : PdhAddEnglishCounterW). Instances :
#   moteur  pid_1234_luid_0x00000000_0x00013a83_phys_0_eng_0_engtype_3D (un par processus et par moteur)
#   mémoire luid_0x00000000_0x00013a83_phys_0 (une par carte)
COMPTEUR_MOTEURS = r"\GPU Engine(*)\Utilization Percentage"
COMPTEUR_MEMOIRE = r"\GPU Adapter Memory(*)\Dedicated Usage"
# Le type de moteur peut contenir des espaces (AMD : « Compute 0 », « High Priority Compute », « True Audio »)
RE_MOTEUR = re.compile(r"luid_(0x[0-9a-f]+_0x[0-9a-f]+)_phys_(\d+)_eng_(\d+)_engtype_(.+)$", re.IGNORECASE)
# Écart minimal entre deux relevés : un taux calculé sur quelques millisecondes est du bruit (relevé à 380 % sur une
# RX 6600 XT) ; plusieurs pages Options ouvertes reçoivent alors le dernier relevé
INTERVALLE_MIN = 1.0
RE_CARTE = re.compile(r"luid_(0x[0-9a-f]+_0x[0-9a-f]+)_phys_(\d+)", re.IGNORECASE)


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


def agreger_compteurs(moteurs, memoire):
    """Compteurs bruts de Windows ({instance: valeur}) → {usage, memoire_mo, carte, par_type}.
    Activité d'un moteur = somme sur les processus ; activité d'une carte = son moteur le plus occupé (3D pour un
    jeu, Compute pour un modèle de langage : ne prendre que la 3D sous-estimerait Ollama). La carte retenue est celle
    qui utilise le plus de mémoire dédiée (les cartes virtuelles en ont 0), sinon la plus active. `par_type` : activité
    par type de moteur de cette carte (diagnostic). Valeurs à None si rien n'est mesuré."""
    par_moteur = defaultdict(float)
    for instance, valeur in moteurs.items():
        m = RE_MOTEUR.search(instance)
        if m:
            par_moteur[(m[1].lower(), m[2], m[3], m[4])] += valeur
    activite, par_type = defaultdict(float), defaultdict(lambda: defaultdict(float))
    for (luid, phys, _moteur, type_), valeur in par_moteur.items():
        carte = f"{luid}_phys_{phys}"
        activite[carte] = max(activite[carte], valeur)
        par_type[carte][type_] = max(par_type[carte][type_], valeur)
    octets = {}
    for instance, valeur in memoire.items():
        m = RE_CARTE.search(instance)
        if m:
            octets[f"{m[1].lower()}_phys_{m[2]}"] = valeur
    if octets and max(octets.values()) > 0:
        carte = max(octets, key=octets.get)
    elif activite:
        carte = max(activite, key=activite.get)
    else:
        return {"usage": None, "memoire_mo": None, "carte": None, "par_type": {}}
    return {"usage": round(min(100.0, activite[carte])) if carte in activite else None,
            "memoire_mo": round(octets[carte] / MO) if carte in octets else None, "carte": carte,
            "par_type": {t: round(v, 1) for t, v in sorted(par_type.get(carte, {}).items())}}


class CompteursWindows:
    """Requête PDH gardée ouverte : l'activité est un taux, calculé entre deux relevés ; garder la requête évite
    d'attendre à chaque appel (seul le premier relève deux fois, à 250 ms d'écart). Un appel coûte quelques ms."""
    PDH_FMT_DOUBLE, PDH_FMT_NOCAP100 = 0x200, 0x8000
    PDH_MORE_DATA = 0x800007D2
    ATTENTE_PREMIER_RELEVE = 0.25

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes

        class Valeur(ctypes.Structure):  # PDH_FMT_COUNTERVALUE (union réduite au double)
            _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]

        class Element(ctypes.Structure):  # PDH_FMT_COUNTERVALUE_ITEM_W
            _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", Valeur)]
        self.Element = Element
        pdh = ctypes.WinDLL("pdh")
        for nom, args in (("PdhOpenQueryW", [wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]),
                          ("PdhAddEnglishCounterW", [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_size_t,
                                                     ctypes.POINTER(ctypes.c_void_p)]),
                          ("PdhCollectQueryData", [ctypes.c_void_p]),
                          ("PdhGetFormattedCounterArrayW", [ctypes.c_void_p, wintypes.DWORD,
                                                            ctypes.POINTER(wintypes.DWORD),
                                                            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]),
                          ("PdhCloseQuery", [ctypes.c_void_p])):
            fonction = getattr(pdh, nom)
            fonction.argtypes, fonction.restype = args, ctypes.c_long
        self.pdh = pdh
        self.requete = ctypes.c_void_p()
        self._verifier(pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.requete)), "PdhOpenQueryW")
        self.moteurs, self.memoire = ctypes.c_void_p(), ctypes.c_void_p()
        try:
            for chemin, compteur in ((COMPTEUR_MOTEURS, self.moteurs), (COMPTEUR_MEMOIRE, self.memoire)):
                self._verifier(pdh.PdhAddEnglishCounterW(self.requete, chemin, 0, ctypes.byref(compteur)), chemin)
            self._verifier(pdh.PdhCollectQueryData(self.requete), "PdhCollectQueryData")
            time.sleep(self.ATTENTE_PREMIER_RELEVE)
        except OSError:
            self.fermer()
            raise

    @staticmethod
    def _verifier(statut, quoi):
        if statut:
            raise OSError(f"{quoi} : code PDH 0x{statut & 0xFFFFFFFF:08X}")

    def _valeurs(self, compteur):
        ct, wt = self.ctypes, self.wintypes
        taille, nombre = wt.DWORD(0), wt.DWORD(0)
        format_ = self.PDH_FMT_DOUBLE | self.PDH_FMT_NOCAP100
        statut = self.pdh.PdhGetFormattedCounterArrayW(compteur, format_, ct.byref(taille), ct.byref(nombre), None)
        if statut & 0xFFFFFFFF != self.PDH_MORE_DATA:
            self._verifier(statut, "PdhGetFormattedCounterArrayW")
            return {}
        tampon = ct.create_string_buffer(taille.value)
        self._verifier(self.pdh.PdhGetFormattedCounterArrayW(compteur, format_, ct.byref(taille), ct.byref(nombre),
                                                             tampon), "PdhGetFormattedCounterArrayW")
        elements = ct.cast(tampon, ct.POINTER(self.Element))
        # CStatus 0 (PDH_CSTATUS_VALID_DATA) ou 1 (NEW_DATA) ; un processus apparu depuis le relevé précédent n'a
        # pas encore de taux : ignoré
        return {elements[i].szName: elements[i].FmtValue.doubleValue for i in range(nombre.value)
                if elements[i].FmtValue.CStatus in (0, 1)}

    def lire(self):
        """({instance: % d'activité}, {instance: octets de mémoire dédiée}) depuis le relevé précédent."""
        self._verifier(self.pdh.PdhCollectQueryData(self.requete), "PdhCollectQueryData")
        return self._valeurs(self.moteurs), self._valeurs(self.memoire)

    def fermer(self):
        if self.requete:
            self.pdh.PdhCloseQuery(self.requete)
            self.requete = self.ctypes.c_void_p()


_compteurs = None
_dernier_releve = (float("-inf"), None)  # (time.monotonic(), compteurs bruts)
_verrou_compteurs = threading.Lock()


def compteurs_windows():
    """Compteurs bruts (voir CompteursWindows.lire), ou None s'ils sont illisibles (Windows trop ancien, compteurs
    désactivés) : la requête est alors refaite à l'appel suivant. Moins de INTERVALLE_MIN après un relevé réussi, le
    même est rendu. Sérialisé : les routes Flask tournent en threads."""
    global _compteurs, _dernier_releve
    with _verrou_compteurs:
        quand, releve = _dernier_releve
        if releve is not None and time.monotonic() - quand < INTERVALLE_MIN:
            return releve
        try:
            if _compteurs is None:
                _compteurs = CompteursWindows()
            releve = _compteurs.lire()
            _dernier_releve = (time.monotonic(), releve)
            return releve
        except (OSError, AttributeError, ValueError) as e:
            log.debug("compteurs GPU de Windows illisibles : %s", e)
            if _compteurs is not None:
                _compteurs.fermer()
            _compteurs = None
            return None


def mesures_windows(lire=None):
    """{usage, memoire_mo, carte, par_type} d'après les compteurs de Windows ; valeurs à None s'ils manquent.
    `lire` : compteurs_windows, cherché à l'appel (remplaçable dans les tests)."""
    bruts = (lire or compteurs_windows)()
    if bruts is None:
        return {"usage": None, "memoire_mo": None, "carte": None, "par_type": {}}
    return agreger_compteurs(*bruts)


def gpu_windows(lire=cartes_du_registre, mesurer=None):
    """Nom et mémoire vidéo dédiée de la carte graphique d'après le registre (toutes marques) ; activité et mémoire
    utilisée d'après les compteurs de Windows (None s'ils sont illisibles). Cartes virtuelles (affichage de base,
    bureau à distance : pas de « PCI\\ ») ignorées ; la carte qui a le plus de mémoire dédiée l'emporte. None si
    aucune."""
    try:
        cartes = [c for c in lire() if str(c.get("id_materiel", "")).upper().startswith("PCI\\")]
    except (OSError, ImportError):
        return None
    if not cartes:
        return None
    carte = max(cartes, key=lambda c: c.get("memoire") or 0)
    mesures = (mesurer or mesures_windows)()
    return {"nom": carte["nom"], "usage": mesures["usage"], "memoire_mo": mesures["memoire_mo"],
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
