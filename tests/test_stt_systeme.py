"""Reconnaissance vocale (stt.py), POST /api/stt, état de la machine (systeme.py, GET /api/etat), moteur de voix
(GET/PUT /api/voice-engine, Contexte.changer_tts) et accès depuis ::1 (lot 7.2). Aucun modèle, réseau ni processus."""
import io
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from faux import VOIX, FauxTTS

from pnj_parlant import serveur, stt, systeme


# --- stt.Reconnaissance --------------------------------------------------------------------------
class FauxWhisperModel:
    instances = []
    segments = []

    def __init__(self, dossier, device, compute_type):
        self.args = (dossier, device, compute_type)
        self.appels = []
        FauxWhisperModel.instances.append(self)

    def transcribe(self, flux, **options):
        self.appels.append((flux.read(), options))
        if isinstance(FauxWhisperModel.segments, Exception):
            raise FauxWhisperModel.segments
        return iter(FauxWhisperModel.segments), None


@pytest.fixture
def whisper(monkeypatch):
    FauxWhisperModel.instances = []
    FauxWhisperModel.segments = [SimpleNamespace(text=" Bonjour "), SimpleNamespace(text="aubergiste. ")]
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FauxWhisperModel))
    return FauxWhisperModel


def reconnaissance(tmp_path, avec_modele=True, **cfg):
    r = stt.Reconnaissance({"moteur": "local", "dossier": "stt", "modele": "small", **cfg}, tmp_path)
    if avec_modele:
        r.dossier.mkdir(parents=True)
        (r.dossier / "model.bin").write_bytes(b"x")
    return r


class TestReconnaissance:
    def test_disponible_seulement_choisie_installee_et_avec_modele(self, tmp_path, whisper):
        assert reconnaissance(tmp_path).disponible()
        assert not reconnaissance(tmp_path / "vide", avec_modele=False).disponible()  # sans model.bin
        navigateur = stt.Reconnaissance({"moteur": "navigateur"}, tmp_path)
        assert not navigateur.choisie and not navigateur.disponible()
        assert not stt.Reconnaissance({}, tmp_path).choisie  # défaut : le navigateur

    def test_faster_whisper_absent(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "faster_whisper", None)  # `import faster_whisper` lève ImportError
        assert not reconnaissance(tmp_path).disponible()

    def test_charger_une_seule_fois_avec_les_reglages(self, tmp_path, whisper):
        r = reconnaissance(tmp_path, appareil="cpu", precision="int8")
        assert r.charger() is r.charger() and len(whisper.instances) == 1
        assert whisper.instances[0].args == (str(r.dossier), "cpu", "int8")

    def test_cuda_precharge_les_bibliotheques_et_prend_float16(self, tmp_path, whisper, monkeypatch):
        appels = []
        monkeypatch.setattr(stt, "precharger_cuda12", lambda: appels.append(1))
        reconnaissance(tmp_path, appareil="cuda").charger()
        assert appels == [1] and whisper.instances[0].args[1:] == ("cuda", "float16")

    def test_transcrire(self, tmp_path, whisper):
        r = reconnaissance(tmp_path, beam_size=3)
        assert r.transcrire(b"audio", "Ysolde, aubergiste") == "Bonjour aubergiste."
        octets, options = whisper.instances[0].appels[0]
        assert octets == b"audio"
        assert options["language"] == "fr" and options["beam_size"] == 3
        assert options["initial_prompt"] == "Ysolde, aubergiste" and options["vad_filter"] is True

    def test_enregistrement_illisible_donne_un_texte_vide(self, tmp_path, whisper):
        whisper.segments = ValueError("pas de flux audio")
        assert reconnaissance(tmp_path).transcrire(b"") == ""

    def test_precharger_cuda12(self, tmp_path, monkeypatch):
        cublas = tmp_path / "nvidia" / "cublas" / "lib"
        cublas.mkdir(parents=True)
        (cublas / "libcublas.so.12").write_bytes(b"")
        chargees = []
        monkeypatch.setattr(stt.site, "getsitepackages", lambda: [str(tmp_path), str(tmp_path / "absent")])
        monkeypatch.setattr(stt.ctypes, "CDLL", lambda chemin, mode: chargees.append(chemin))
        monkeypatch.setattr(stt.ctypes, "RTLD_GLOBAL", 0x100, raising=False)
        stt.precharger_cuda12()
        assert [p.replace("\\", "/").rsplit("/", 1)[-1] for p in chargees] == ["libcublas.so.12"]


# --- POST /api/stt -------------------------------------------------------------------------------
class RecoRoute:
    choisie, dossier = True, None

    def __init__(self):
        self.vus = []

    def disponible(self):
        return True

    def transcrire(self, audio, indice=None):
        self.vus.append((audio, indice))
        return "bonjour"


class TestRouteStt:
    @pytest.fixture
    def reco(self, ctx):
        ctx.reconnaissance = RecoRoute()
        return ctx.reconnaissance

    def envoyer(self, client, audio=b"webm", **form):
        data = {**form}
        if audio is not None:
            data["audio"] = (io.BytesIO(audio), "q.webm")
        return client.post("/api/stt", data=data, content_type="multipart/form-data")

    def test_sans_enregistrement(self, client, reco):
        assert self.envoyer(client, audio=None).status_code == 400 and reco.vus == []

    def test_texte_renvoye(self, client, reco):
        assert self.envoyer(client, indice="Ysolde").get_json() == {"text": "bonjour"}
        assert reco.vus == [(b"webm", "Ysolde")]

    def test_indice_tronque_a_200_caracteres_ou_absent(self, client, reco):
        self.envoyer(client, indice="  " + "x" * 300 + "  ")
        self.envoyer(client, indice="   ")
        self.envoyer(client)
        assert len(reco.vus[0][1]) == 200 and reco.vus[1][1] is None and reco.vus[2][1] is None

    def test_indisponible(self, client):
        assert self.envoyer(client, audio=None).status_code == 404


# --- systeme.py ----------------------------------------------------------------------------------
class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestSysteme:
    def test_gpu(self, monkeypatch):
        monkeypatch.setattr(systeme.subprocess, "run", lambda *a, **k: SimpleNamespace(
            stdout="NVIDIA T400 4GB, 12, 300, 4096\n"))
        assert systeme.etat_gpu() == {"nom": "NVIDIA T400 4GB", "usage": 12, "memoire_mo": 300,
                                      "memoire_totale_mo": 4096}

    @pytest.mark.parametrize("panne", [FileNotFoundError("nvidia-smi"), subprocess.CalledProcessError(9, "x"),
                                       subprocess.TimeoutExpired("x", 3)])
    def test_gpu_absent_ou_en_panne(self, monkeypatch, panne):
        def run(*a, **k):
            raise panne
        monkeypatch.setattr(systeme.subprocess, "run", run)
        assert systeme.gpu_nvidia() is None

    @pytest.mark.parametrize("sortie", ["", "pas de virgules", "a, b, c, d", "a, 1, 2"])
    def test_gpu_sortie_illisible(self, monkeypatch, sortie):
        monkeypatch.setattr(systeme.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=sortie))
        assert systeme.gpu_nvidia() is None

    @pytest.mark.parametrize("plateforme, nom_os, attendu", [("linux", "posix", "linux"), ("win32", "nt", "windows"),
                                                              ("darwin", "posix", None)])
    def test_gpu_sans_nvidia_selon_le_systeme(self, monkeypatch, plateforme, nom_os, attendu):
        monkeypatch.setattr(systeme, "gpu_nvidia", lambda: None)
        monkeypatch.setattr(systeme, "gpu_linux", lambda: "linux")
        monkeypatch.setattr(systeme, "gpu_windows", lambda: "windows")
        monkeypatch.setattr(systeme.sys, "platform", plateforme)
        monkeypatch.setattr(systeme.os, "name", nom_os)
        assert systeme.etat_gpu() == attendu

    def test_gpu_nvidia_d_abord(self, monkeypatch):
        monkeypatch.setattr(systeme, "gpu_nvidia", lambda: {"nom": "NVIDIA"})
        monkeypatch.setattr(systeme, "gpu_linux", lambda: pytest.fail("pas de repli avec nvidia-smi"))
        monkeypatch.setattr(systeme, "gpu_windows", lambda: pytest.fail("pas de repli avec nvidia-smi"))
        assert systeme.etat_gpu() == {"nom": "NVIDIA"}

    @staticmethod
    def carte_linux(racine, nom, **fichiers):
        d = racine / nom / "device"
        d.mkdir(parents=True)
        for f, v in fichiers.items():
            (d / f).write_text(f"{v}\n", encoding="utf-8")

    def test_gpu_linux_amd(self, tmp_path):
        mo = 1024 * 1024
        self.carte_linux(tmp_path, "card0", vendor="0x8086")  # puce Intel intégrée : rien de mesuré
        self.carte_linux(tmp_path, "card1", vendor="0x1002", gpu_busy_percent=37, mem_info_vram_used=1024 * mo,
                         mem_info_vram_total=8192 * mo)
        self.carte_linux(tmp_path, "card1-HDMI-A-1", vendor="0x1002")  # sortie d'écran, pas une carte
        assert systeme.gpu_linux(tmp_path) == {"nom": "Carte AMD", "usage": 37, "memoire_mo": 1024,
                                               "memoire_totale_mo": 8192}

    def test_gpu_linux_autre_carte_et_nom(self, tmp_path):
        self.carte_linux(tmp_path / "intel", "card0", vendor="0x8086")
        assert systeme.gpu_linux(tmp_path / "intel") == {"nom": "Carte Intel", "usage": None, "memoire_mo": None,
                                                         "memoire_totale_mo": None}
        # nom donné par le pilote ; activité illisible et mémoire nulle = inconnues
        self.carte_linux(tmp_path / "amd", "card0", vendor="0x1002", product_name="AMD Radeon RX 6600",
                         gpu_busy_percent="illisible", mem_info_vram_used=0, mem_info_vram_total=0)
        assert systeme.gpu_linux(tmp_path / "amd") == {"nom": "AMD Radeon RX 6600", "usage": None, "memoire_mo": None,
                                                       "memoire_totale_mo": None}

    def test_gpu_linux_aucune(self, tmp_path):
        assert systeme.gpu_linux(tmp_path) is None
        assert systeme.gpu_linux(tmp_path / "absent") is None
        (tmp_path / "card0" / "device").mkdir(parents=True)  # sans fabricant
        assert systeme.gpu_linux(tmp_path) is None

    def test_gpu_windows(self):
        cartes = [{"nom": "Microsoft Basic Display Adapter", "id_materiel": "ROOT\\BasicDisplay", "memoire": 1 << 40},
                  {"nom": "Intel(R) UHD Graphics 620", "id_materiel": "PCI\\VEN_8086&DEV_3EA0", "memoire": 1 << 30},
                  {"nom": "AMD Radeon RX 6600", "id_materiel": "pci\\ven_1002&dev_73ff", "memoire": 8 << 30}]
        sans_compteurs = lambda: {"usage": None, "memoire_mo": None, "carte": None, "par_type": {}}  # noqa: E731
        assert systeme.gpu_windows(lambda: cartes, sans_compteurs) == {
            "nom": "AMD Radeon RX 6600", "usage": None, "memoire_mo": None, "memoire_totale_mo": 8192}
        assert systeme.gpu_windows(lambda: [{"nom": "Intel", "id_materiel": "PCI\\X", "memoire": None}],
                                   sans_compteurs) == {
            "nom": "Intel", "usage": None, "memoire_mo": None, "memoire_totale_mo": None}
        assert systeme.gpu_windows(lambda: cartes[:1], sans_compteurs) is None  # carte virtuelle seule
        # compteurs de Windows : activité et mémoire utilisée (rapport de la RX 6600 XT : 66 %, 4218 Mo)
        mesures = lambda: {"usage": 66, "memoire_mo": 4218, "carte": "x", "par_type": {}}  # noqa: E731
        assert systeme.gpu_windows(lambda: cartes, mesures) == {
            "nom": "AMD Radeon RX 6600", "usage": 66, "memoire_mo": 4218, "memoire_totale_mo": 8192}

    def test_agreger_compteurs(self):
        amd, virtuelle = "luid_0x00000000_0x00013a83_phys_0", "luid_0x00000000_0x0001560f_phys_0"
        moteurs = {
            # deux processus sur le moteur 3D (additionnés), Ollama sur un moteur Compute (le plus occupé l'emporte)
            f"pid_100_{amd}_eng_0_engtype_3D": 20.0, f"pid_200_{amd}_eng_0_engtype_3D": 15.5,
            f"pid_300_{amd}_eng_4_engtype_Compute_0": 87.0, f"pid_300_{amd}_eng_1_engtype_Copy": 2.0,
            f"pid_400_{virtuelle}_eng_0_engtype_3D": 99.0, "instance illisible": 50.0}
        memoire = {amd.upper().replace("LUID", "luid").replace("PHYS", "phys"): 4218 * 1024 * 1024,
                   virtuelle: 0.0, "autre": 1.0}
        assert systeme.agreger_compteurs(moteurs, memoire) == {
            "usage": 87, "memoire_mo": 4218, "carte": "0x00000000_0x00013a83_phys_0",
            "par_type": {"3D": 35.5, "Compute_0": 87.0, "Copy": 2.0}}
        # au-delà de 100 % (plusieurs processus) : plafonné
        assert systeme.agreger_compteurs({f"pid_1_{amd}_eng_0_engtype_3D": 70.0,
                                          f"pid_2_{amd}_eng_0_engtype_3D": 60.0}, {amd: 1.0})["usage"] == 100

    def test_agreger_compteurs_sans_memoire_ni_mesure(self):
        a, b = "luid_0x0_0x1_phys_0", "luid_0x0_0x2_phys_0"
        # mémoire nulle partout (puce intégrée) : la carte la plus active
        m = systeme.agreger_compteurs({f"pid_1_{a}_eng_0_engtype_3D": 3.0, f"pid_1_{b}_eng_0_engtype_3D": 9.0},
                                      {a: 0.0, b: 0.0})
        assert (m["usage"], m["memoire_mo"], m["carte"]) == (9, 0, "0x0_0x2_phys_0")
        # mémoire connue, aucun moteur : activité inconnue
        assert systeme.agreger_compteurs({}, {a: 2 * 1024 * 1024})["usage"] is None
        assert systeme.agreger_compteurs({}, {}) == {"usage": None, "memoire_mo": None, "carte": None, "par_type": {}}
        assert systeme.mesures_windows(lambda: None)["usage"] is None  # compteurs illisibles

    def test_compteurs_windows_requete_gardee_puis_refaite_apres_panne(self, monkeypatch):
        ouvertes, fermees = [], []

        class FauxCompteurs:
            def __init__(self):
                ouvertes.append(self)
                self.releves = 0

            def lire(self):
                self.releves += 1
                if self.releves == 3:
                    raise OSError("compteur disparu")
                return {"m": 1.0}, {"c": 2.0}

            def fermer(self):
                fermees.append(self)
        monkeypatch.setattr(systeme, "CompteursWindows", FauxCompteurs)
        monkeypatch.setattr(systeme, "_compteurs", None)
        assert systeme.compteurs_windows() == ({"m": 1.0}, {"c": 2.0})
        assert systeme.compteurs_windows() == ({"m": 1.0}, {"c": 2.0})
        assert len(ouvertes) == 1  # requête gardée entre deux appels
        assert systeme.compteurs_windows() is None  # panne : requête fermée…
        assert fermees == ouvertes
        assert systeme.compteurs_windows() == ({"m": 1.0}, {"c": 2.0})  # … et refaite à l'appel suivant
        assert len(ouvertes) == 2

    def test_compteurs_windows_illisibles(self, monkeypatch):
        def ouvrir():
            raise OSError("PdhAddEnglishCounterW : code PDH 0xC0000BB8")
        monkeypatch.setattr(systeme, "CompteursWindows", ouvrir)
        monkeypatch.setattr(systeme, "_compteurs", None)
        assert systeme.compteurs_windows() is None

    @pytest.mark.skipif(sys.platform != "win32", reason="API PDH de Windows")
    def test_compteurs_windows_reels(self, monkeypatch):
        monkeypatch.setattr(systeme, "_compteurs", None)
        bruts = systeme.compteurs_windows()
        if bruts is None:
            pytest.skip("compteurs GPU absents de ce Windows")
        moteurs, memoire = bruts
        assert all(isinstance(v, float) for v in [*moteurs.values(), *memoire.values()])
        assert systeme.compteurs_windows() is not None  # requête gardée, relue
        systeme._compteurs.fermer()

    @pytest.mark.parametrize("panne", [OSError("registre"), ImportError("winreg")])
    def test_gpu_windows_registre_illisible(self, panne):
        def lire():
            raise panne
        assert systeme.gpu_windows(lire) is None

    def test_cartes_du_registre(self, monkeypatch):
        # faux winreg : sous-clés 0000 (format récent), 0001 (ancien format en octets), 0002 (sans DriverDesc),
        # Properties (protégée)
        cles = {"0000": {"DriverDesc": "AMD Radeon RX 6600", "MatchingDeviceId": "PCI\\VEN_1002",
                         "HardwareInformation.qwMemorySize": 8 << 30},
                "0001": {"DriverDesc": "Intel(R) UHD Graphics",
                         "HardwareInformation.MemorySize": (1 << 30).to_bytes(4, "little")},
                "0002": {"MatchingDeviceId": "PCI\\X"}, "Properties": None}

        class Cle:
            def __init__(self, valeurs):
                self.valeurs = valeurs

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def ouvrir(parent, nom):
            if parent == "HKLM":
                return Cle(None)
            if cles[nom] is None:
                raise PermissionError(nom)
            return Cle(cles[nom])

        def enumerer(_cle, i):
            if i >= len(cles):
                raise OSError("fin")
            return list(cles)[i]

        def valeur(cle, nom):
            if nom not in cle.valeurs:
                raise FileNotFoundError(nom)
            return cle.valeurs[nom], 0

        monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
            HKEY_LOCAL_MACHINE="HKLM", OpenKey=ouvrir, EnumKey=enumerer, QueryValueEx=valeur))
        assert systeme.cartes_du_registre() == [
            {"nom": "AMD Radeon RX 6600", "id_materiel": "PCI\\VEN_1002", "memoire": 8 << 30},
            {"nom": "Intel(R) UHD Graphics", "id_materiel": "", "memoire": 1 << 30}]

    def test_ollama(self, monkeypatch):
        urls = []

        def urlopen(url, timeout=None):
            urls.append(url)
            return Reponse(json.dumps({"models": [{"name": "qwen3:4b", "size_vram": 2_500_000_000},
                                                  {"name": "autre"}]}).encode())
        monkeypatch.setattr(systeme.urllib.request, "urlopen", urlopen)
        assert systeme.etat_ollama("http://ollama:11434/") == {"ok": True, "charges": [
            {"nom": "qwen3:4b", "vram_mo": 2500}, {"nom": "autre", "vram_mo": 0}]}
        assert urls == ["http://ollama:11434/api/ps"]

    @pytest.mark.parametrize("reponse", [OSError("refusé"), b"pas du json", b'{"models": [{"size": 1}]}'])
    def test_ollama_ne_repond_pas(self, monkeypatch, reponse):
        def urlopen(url, timeout=None):
            if isinstance(reponse, Exception):
                raise reponse
            return Reponse(reponse)
        monkeypatch.setattr(systeme.urllib.request, "urlopen", urlopen)
        assert systeme.etat_ollama("http://x") == {"ok": False}


class TestRouteEtat:
    @pytest.fixture(autouse=True)
    def simule(self, monkeypatch):
        self.appels = []
        monkeypatch.setattr(serveur.systeme, "etat_gpu", lambda: {"nom": "GPU"})
        monkeypatch.setattr(serveur.systeme, "etat_ollama", lambda url: self.appels.append(url) or {"ok": True})

    def test_ollama_interroge_a_l_adresse_configuree(self, client, moteurs):
        moteurs.local_cfg["url"] = "http://ollama:11434"
        assert client.get("/api/etat").get_json() == {"gpu": {"nom": "GPU"}, "ollama": {"ok": True}, "lmstudio": None}
        assert self.appels == ["http://ollama:11434"]

    def test_tout_claude_pas_d_ollama_ni_lmstudio(self, client, moteurs):
        moteurs.choix = {"creation": "claude", "dialogue": "claude"}
        d = client.get("/api/etat").get_json()
        assert d["ollama"] is None and d["lmstudio"] is None and self.appels == []

    def test_lmstudio(self, client, moteurs):
        moteurs.choix = {"creation": "claude", "dialogue": "lmstudio"}
        moteurs.etat_lmstudio = lambda: {"ok": False, "message": "arrêté"}
        assert client.get("/api/etat").get_json()["lmstudio"] == {"ok": False, "message": "arrêté"}


# --- /api/voice-engine ---------------------------------------------------------------------------
class TestMoteurDeVoix:
    @pytest.fixture
    def charges(self, monkeypatch):
        """Remplace voix.charger : un faux moteur par nom (catalogue vide pour « pocket »)."""
        construits = []

        def charger(reglages, racine, moteur=None):
            tts = FauxTTS([] if moteur == "pocket" else VOIX)
            tts.nom = moteur
            construits.append(tts)
            return tts
        monkeypatch.setattr(serveur.voix, "charger", charger)
        return construits

    def test_lecture(self, client):
        assert client.get("/api/voice-engine").get_json() == {"actuel": "faux", "moteurs": ["piper", "pocket", "edge"]}

    def test_changement(self, client, ctx, charges):
        ctx._sante = (float("inf"), [])
        r = client.put("/api/voice-engine", json={"moteur": "edge"})
        assert r.status_code == 200 and r.get_json() == {"actuel": "edge"}
        assert ctx.tts is charges[0] and ctx.tts_charges["edge"] is ctx.tts and ctx._sante is None
        assert client.get("/api/voice-engine").get_json()["actuel"] == "edge"
        client.put("/api/voice-engine", json={"moteur": "edge"})
        assert len(charges) == 1  # déjà chargé : pas reconstruit

    def test_moteur_sans_voix_refuse(self, client, ctx, charges):
        tts = ctx.tts
        r = client.put("/api/voice-engine", json={"moteur": "pocket"})
        assert r.status_code == 400 and "pocket" in r.get_json()["error"]
        assert ctx.tts is tts and "pocket" not in ctx.tts_charges

    @pytest.mark.parametrize("corps", [{"moteur": "gramophone"}, {"moteur": None}, {}])
    def test_moteur_inconnu_ou_absent(self, client, corps):
        assert client.put("/api/voice-engine", json=corps).status_code == 400


# --- Accès depuis ::1 ----------------------------------------------------------------------------
def test_reglages_depuis_ipv6_local(client):
    ipv6 = {"REMOTE_ADDR": "::1"}
    assert client.get("/api/reglages", environ_base=ipv6).get_json()["local"] is True
    r = client.put("/api/reglages", json={"changements": {"dialogue.intervention": 0.5}}, environ_base=ipv6)
    assert r.status_code == 200
    assert client.get("/api/acces", environ_base=ipv6).get_json()["local"] is True
    assert client.get("/api/reglages", environ_base={"REMOTE_ADDR": "fe80::1"}).get_json()["local"] is False
