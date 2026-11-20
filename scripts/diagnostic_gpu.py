"""
Diagnostic de la carte graphique : ce que lit systeme.py (page Options, « État ») et les sources brutes autour,
pour vérifier la détection sur une machine qu'on ne peut pas joindre (carte AMD, Intel…).

    python scripts/diagnostic_gpu.py          (ou scripts\\diagnostic-gpu.bat sous Windows)

Lancé depuis une copie à jour du dépôt, sans installation : seulement la bibliothèque standard de Python (3.11 ou
plus). Rien n'est modifié sur la machine. Écrit le rapport dans diagnostic-gpu.txt (dossier du dépôt) et à l'écran.
Le rapport ne contient ni nom de machine ni nom d'utilisateur : chemins personnels remplacés par « ~ ».
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

DEPOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPOT / "src"))  # pnj_parlant sans installation

RAPPORT = DEPOT / "diagnostic-gpu.txt"
lignes = []


def ecrire(texte=""):
    texte = str(texte).replace(str(Path.home()), "~")
    lignes.append(texte)
    try:
        print(texte)
    except UnicodeEncodeError:  # console Windows sans UTF-8
        print(texte.encode("ascii", "replace").decode())


def titre(texte):
    ecrire()
    ecrire(f"=== {texte} " + "=" * max(3, 70 - len(texte)))


def octets_lisibles(valeur):
    """Valeur binaire du registre : nombre (4 ou 8 octets) ou texte UTF-16 (nom de la puce, du BIOS…)."""
    if len(valeur) in (4, 8):
        return f"octets {valeur.hex()} = {int.from_bytes(valeur, 'little')}"
    try:
        return f"texte {valeur.decode('utf-16-le').rstrip(chr(0))!r}"
    except UnicodeDecodeError:
        return f"octets {valeur.hex()}"


def commande(args, delai=15):
    """Sortie d'une commande (ou l'erreur), avec sa durée. PowerShell écrit en UTF-8 (accents d'un Windows français)."""
    if args[0] == "powershell":
        args = [*args[:-1], "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + args[-1]]
    debut = time.perf_counter()
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=delai, encoding="utf-8", errors="replace")
        sortie = (r.stdout + (f"\n[stderr] {r.stderr}" if r.stderr.strip() else "")).strip()
        etat = f"code {r.returncode}"
    except (OSError, subprocess.SubprocessError) as e:
        sortie, etat = f"{type(e).__name__}: {e}", "échec"
    ecrire(f"$ {' '.join(args) if len(' '.join(args)) < 160 else args[0] + ' …'}  ({etat}, "
           f"{(time.perf_counter() - debut) * 1000:.0f} ms)")
    for ligne in sortie.splitlines() or ["(rien)"]:
        ecrire(f"    {ligne}")


def appel(nom, fonction):
    """Résultat d'une fonction de systeme.py, avec sa durée ; une exception est rapportée, pas levée."""
    debut = time.perf_counter()
    try:
        resultat = fonction()
    except Exception:  # noqa: BLE001 : un diagnostic rapporte tout
        resultat = "EXCEPTION\n" + traceback.format_exc()
    ecrire(f"{nom} ({(time.perf_counter() - debut) * 1000:.1f} ms) : {resultat}")
    return resultat


def section_systeme():
    titre("Système")
    ecrire(f"Système : {platform.system()} {platform.release()} ({platform.version()}), {platform.machine()}")
    ecrire(f"Python : {sys.version.split()[0]} ({sys.executable})")
    try:
        import pnj_parlant
        ecrire(f"pnj_parlant : {pnj_parlant.__version__} ({Path(pnj_parlant.__file__).parent})")
    except Exception as e:  # noqa: BLE001
        ecrire(f"pnj_parlant introuvable : {e}")
    commande(["git", "-C", str(DEPOT), "log", "-1", "--format=%h %ad %s", "--date=short"])


def section_systeme_py():
    titre("Ce que lit systeme.py (page Options, rubrique État)")
    from pnj_parlant import systeme
    gpu = appel("etat_gpu()", systeme.etat_gpu)
    appel("gpu_nvidia()", systeme.gpu_nvidia)
    if sys.platform.startswith("linux"):
        appel("gpu_linux()", systeme.gpu_linux)
    if os.name == "nt":
        appel("cartes_du_registre()", systeme.cartes_du_registre)
        appel("gpu_windows()", systeme.gpu_windows)
    return gpu if isinstance(gpu, dict) or gpu is None else None


def section_affichage(gpu):
    """Texte que montrerait la page (lignesEtat de scene.js), si Node est installé."""
    titre("Affichage dans la page Options (lignesEtat de static/js/scene.js)")
    if not shutil.which("node"):
        ecrire("Node n'est pas installé : affichage non calculé (le résultat de etat_gpu() ci-dessus suffit).")
        return
    module = (DEPOT / "src/pnj_parlant/static/js/scene.js").as_uri()
    code = (f"const s = await import({json.dumps(module)}); const etat = {{gpu: {json.dumps(gpu)}}};"
            "for (const d of [false, true]) console.log(d ? 'mode MJ    :' : 'mode joueur:', "
            "JSON.stringify(s.lignesEtat(etat, d)));")
    commande(["node", "--input-type=module", "-e", code])


def section_nvidia():
    titre("NVIDIA (nvidia-smi)")
    if shutil.which("nvidia-smi"):
        commande(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                  "--format=csv,noheader,nounits"])
    else:
        ecrire("nvidia-smi absent (normal sans carte NVIDIA).")


def section_windows():
    titre("Windows : registre des cartes graphiques (source de gpu_windows)")
    try:
        import winreg

        from pnj_parlant.systeme import CLE_CARTES
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
                        j, valeurs = 0, []
                        while True:
                            try:
                                nom, valeur, type_ = winreg.EnumValue(cle, j)
                            except OSError:
                                break
                            j += 1
                            if any(m in nom for m in ("Desc", "DeviceId", "Memory", "Provider", "DriverVersion",
                                                      "ChipType", "AdapterString", "BiosString")):
                                if isinstance(valeur, bytes):
                                    valeur = octets_lisibles(valeur)
                                valeurs.append(f"{nom} = {valeur!r} (type {type_})")
                except OSError as e:
                    ecrire(f"[{nom_cle}] illisible : {e}")
                    continue
                ecrire(f"[{nom_cle}]")
                for v in valeurs or ["(aucune valeur utile)"]:
                    ecrire(f"    {v}")
    except Exception:  # noqa: BLE001
        ecrire(traceback.format_exc())

    titre("Windows : WMI (Win32_VideoController), pour comparaison")
    commande(["powershell", "-NoProfile", "-Command",
              "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterCompatibility, AdapterRAM, "
              "DriverVersion, PNPDeviceID, VideoProcessor | Format-List"])

    titre("Windows : compteurs de performance GPU (pour mesurer l'activité plus tard)")
    # Jeux de compteurs GPU dans la langue du système ; puis une mesure chronométrée de l'activité 3D et de la
    # mémoire dédiée utilisée (compteurs repérés par leurs instances, pas par leurs noms traduits)
    commande(["powershell", "-NoProfile", "-Command", COMPTEURS_GPU], delai=40)


COMPTEURS_GPU = r"""
$jeux = Get-Counter -ListSet *GPU* -ErrorAction SilentlyContinue
if (-not $jeux) { 'aucun jeu de compteurs GPU'; return }
foreach ($j in $jeux) { $j.CounterSetName; $j.Counter | ForEach-Object { '  ' + $_ } }
# Activité : jeu dont les instances sont des moteurs (engtype_3D), compteur en pourcentage
$moteur = $jeux | Where-Object { ($_.PathsWithInstances -match 'engtype_3D').Count } | Select-Object -First 1
if ($moteur) {
  $p = $moteur.Paths | Where-Object { $_ -match 'tili|%' } | Select-Object -First 1
  $p = $p -replace '\(\*\)', '(*engtype_3D)'
  $t = Measure-Command { $c = Get-Counter -Counter $p -ErrorAction SilentlyContinue }
  $somme = [math]::Round(($c.CounterSamples | Measure-Object CookedValue -Sum).Sum, 1)
  "activité 3D : $p -> $somme % en $([int]$t.TotalMilliseconds) ms"
} else { 'aucun compteur par moteur (engtype_3D)' }
# Mémoire : jeu par carte (instances luid_…_phys_N, sans pid_ : pas la mémoire par processus), compteur « dédiée »
$memoire = $jeux | Where-Object {
  ($_.PathsWithInstances -match 'phys_\d+\)').Count -and -not ($_.PathsWithInstances -match 'pid_').Count -and
  ($_.Paths -match 'edicat|dédi').Count } | Select-Object -First 1
if ($memoire) {
  $p = $memoire.Paths | Where-Object { $_ -match 'edicat|dédi' } | Select-Object -First 1
  $t = Measure-Command { $c = Get-Counter -Counter $p -ErrorAction SilentlyContinue }
  foreach ($e in $c.CounterSamples) {
    "mémoire dédiée : $($e.InstanceName) -> $([math]::Round($e.CookedValue / 1MB)) Mo"
  }
  "($p, en $([int]$t.TotalMilliseconds) ms)"
} else { 'aucun compteur de mémoire dédiée' }
"""


def section_linux():
    titre("Linux : /sys/class/drm (source de gpu_linux)")
    racine = Path("/sys/class/drm")
    dossiers = sorted(racine.glob("card*")) if racine.exists() else []
    if not dossiers:
        ecrire("Aucune carte dans /sys/class/drm.")
    for carte in dossiers:
        if "-" in carte.name:
            ecrire(f"{carte.name} : sortie d'écran (ignorée)")
            continue
        ecrire(f"{carte.name} :")
        d = carte / "device"
        for f in ("vendor", "device", "product_name", "gpu_busy_percent", "mem_info_vram_used", "mem_info_vram_total",
                  "mem_info_vis_vram_total", "mem_info_gtt_total"):
            try:
                ecrire(f"    {f} = {(d / f).read_text(errors='replace').strip()}")
            except OSError as e:
                ecrire(f"    {f} : absent ({type(e).__name__})")
        try:
            ecrire(f"    pilote = {os.path.basename(os.readlink(d / 'driver'))}")
        except OSError:
            pass
    titre("Linux : outils")
    if shutil.which("lspci"):
        commande(["sh", "-c", "lspci -nn | grep -Ei 'vga|3d|display'"])
    for outil, args in (("rocm-smi", ["rocm-smi", "--showuse", "--showmemuse", "--showmeminfo", "vram"]),
                        ("amd-smi", ["amd-smi", "static", "--asic"])):
        if shutil.which(outil):
            commande(args)
        else:
            ecrire(f"{outil} absent.")


def section_ollama():
    titre("Ollama (http://localhost:11434), s'il tourne sur cette machine")
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=2) as r:
            ecrire(f"/api/ps : {r.read().decode(errors='replace')}")
    except (OSError, ValueError) as e:
        ecrire(f"Ollama ne répond pas : {e}")


def main():
    debut = time.strftime("%Y-%m-%d %H:%M:%S")
    ecrire(f"Diagnostic de la carte graphique — PNJ parlants — {debut}")
    section_systeme()
    gpu = section_systeme_py()
    section_affichage(gpu)
    section_nvidia()
    if os.name == "nt":
        section_windows()
    if sys.platform.startswith("linux"):
        section_linux()
    section_ollama()
    RAPPORT.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print()
    print(f"Rapport écrit dans {RAPPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
