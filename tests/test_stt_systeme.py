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
        assert systeme.etat_gpu() is None

    @pytest.mark.parametrize("sortie", ["", "pas de virgules", "a, b, c, d", "a, 1, 2"])
    def test_gpu_sortie_illisible(self, monkeypatch, sortie):
        monkeypatch.setattr(systeme.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=sortie))
        assert systeme.etat_gpu() is None

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
