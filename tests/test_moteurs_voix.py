"""Moteurs de synthèse Piper, Pocket TTS et Edge (voix.py) et portraits.Local, sans modèle ni réseau (lot 7.2) :
les paquets piper, pocket_tts, edge_tts, torch et diffusers sont remplacés dans `sys.modules`."""
import io
import json
import sys
import wave
from types import SimpleNamespace

import pytest

from pnj_parlant import portraits, voix
from pnj_parlant.portraits import PortraitIndisponible
from pnj_parlant.voix import VoixIndisponible


def lire_wav(octets):
    with wave.open(io.BytesIO(octets)) as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(w.getnframes())


# --- Piper ---------------------------------------------------------------------------------------
class FauxPiperVoice:
    chargees = []

    def __init__(self, chemin):
        self.chemin = chemin
        self.appels = []

    @classmethod
    def load(cls, chemin):
        v = cls(chemin)
        cls.chargees.append(v)
        return v

    def synthesize_wav(self, texte, wav_file, syn_config=None):
        self.appels.append((texte, syn_config))
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x01\x00" * 4)


class FausseConfigPiper:
    def __init__(self, speaker_id=None, length_scale=1.0):
        self.speaker_id, self.length_scale = speaker_id, length_scale


@pytest.fixture
def piper(tmp_path, monkeypatch):
    """Piper avec un faux paquet et un dossier de voix : siwis (1 locuteur), upmc (2), sans-json, json abîmé."""
    FauxPiperVoice.chargees = []
    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(PiperVoice=FauxPiperVoice,
                                                              SynthesisConfig=FausseConfigPiper))
    dossier = tmp_path / "voices"
    dossier.mkdir()
    for nom, infos in [("fr_FR-siwis-medium", {"num_speakers": 1}), ("fr_FR-upmc-medium", {"num_speakers": 2}),
                       ("sans-json", None), ("abime", "pas du json")]:
        (dossier / f"{nom}.onnx").write_bytes(b"onnx")
        if infos is not None:
            (dossier / f"{nom}.onnx.json").write_text(infos if isinstance(infos, str) else json.dumps(infos))
    genres = {"fr_FR-siwis-medium": "feminin", "fr_FR-upmc-medium": {"feminin": [0], "masculin": [1]}}
    return voix.Piper({"genres": genres}, tmp_path)


class TestPiper:
    def test_catalogue_et_genres(self, piper):
        catalogue = piper.catalogue()
        assert [(v["name"], v["speaker"], g) for v, g in catalogue] == [
            ("abime", 0, None), ("fr_FR-siwis-medium", 0, "feminin"), ("fr_FR-upmc-medium", 0, "feminin"),
            ("fr_FR-upmc-medium", 1, "masculin"), ("sans-json", 0, None)]
        assert catalogue[1][0]["label"] == "siwis · locuteur 0"

    def test_synthese_wav(self, piper):
        audio, mime = piper.synthese("Bonjour.", {"name": "fr_FR-siwis-medium", "length_scale": 1.2})
        assert mime == "audio/wav" and lire_wav(audio)[:3] == (1, 2, 22050)
        texte, config = piper._cache["fr_FR-siwis-medium"].appels[0]
        assert texte == "Bonjour." and config.length_scale == 1.2 and config.speaker_id is None

    def test_locuteur_transmis_seulement_pour_une_voix_multi_locuteurs(self, piper):
        piper.synthese("a", {"name": "fr_FR-upmc-medium", "speaker": 1})
        assert piper._cache["fr_FR-upmc-medium"].appels[0][1].speaker_id == 1
        piper.synthese("a", {"name": "fr_FR-siwis-medium", "speaker": 1})
        assert piper._cache["fr_FR-siwis-medium"].appels[0][1].speaker_id is None

    def test_voix_chargee_une_fois(self, piper):
        for _ in range(3):
            piper.synthese("a", {"name": "sans-json"})
        assert len(FauxPiperVoice.chargees) == 1

    @pytest.mark.parametrize("nom", ["inconnue", "../hors-dossier", None, 12, ["x"]])
    def test_voix_inconnue_ou_chemin_arbitraire(self, piper, nom):
        with pytest.raises(VoixIndisponible):
            piper.synthese("a", {"name": nom})
        assert FauxPiperVoice.chargees == []

    def test_sans_le_paquet(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "piper", None)
        moteur = voix.Piper({}, tmp_path)
        assert moteur.catalogue() == []
        with pytest.raises(VoixIndisponible):
            moteur.synthese("a", {"name": "x"})

    def test_prechauffer_ne_fait_rien(self, piper):
        assert piper.prechauffer() is None and FauxPiperVoice.chargees == []


# --- Pocket TTS ----------------------------------------------------------------------------------
class Tableau:
    """Tient lieu du tenseur de Pocket TTS : clamp, produit, short, numpy et tobytes renvoient les octets prévus."""

    def clamp(self, bas, haut):
        return self

    def __mul__(self, n):
        assert n == 32767
        return self

    def short(self):
        return self

    def numpy(self):
        return self

    def tobytes(self):
        return b"\x05\x00\x06\x00"


class FauxModelePocket:
    sample_rate = 24000

    def __init__(self):
        self.etats, self.generations = [], []
        self.voix_cassees = set()

    def get_state_for_audio_prompt(self, nom):
        if nom in self.voix_cassees:
            raise OSError("voix non téléchargée")
        self.etats.append(nom)
        return f"etat-{nom}"

    def generate_audio(self, etat, texte):
        self.generations.append((etat, texte))
        return Tableau()


@pytest.fixture
def pocket(tmp_path, monkeypatch):
    modele = FauxModelePocket()
    charges = []

    def load_model(language):
        charges.append(language)
        return modele
    monkeypatch.setitem(sys.modules, "pocket_tts", SimpleNamespace(TTSModel=SimpleNamespace(load_model=load_model)))
    moteur = voix.Pocket({"genres": {"estelle": "feminin", "marius": "masculin"}}, tmp_path)
    moteur.faux, moteur.charges = modele, charges
    return moteur


class TestPocket:
    def test_catalogue(self, pocket):
        assert [(v["name"], v["label"], g) for v, g in pocket.catalogue()] == [
            ("estelle", "Estelle", "feminin"), ("marius", "Marius", "masculin")]

    def test_genres_par_defaut(self, tmp_path, pocket):
        assert voix.Pocket({}, tmp_path).genres == voix.POCKET_GENRES

    def test_synthese_charge_le_modele_au_premier_appel(self, pocket):
        audio, mime = pocket.synthese("Salut.", {"name": "estelle"})
        assert mime == "audio/wav" and pocket.charges == ["french"]
        assert lire_wav(audio) == (1, 2, 24000, b"\x05\x00\x06\x00")
        assert pocket.faux.generations == [("etat-estelle", "Salut.")]
        pocket.synthese("Encore.", {"name": "estelle"})
        assert pocket.charges == ["french"] and pocket.faux.etats == ["estelle"]  # modèle et voix en cache

    @pytest.mark.parametrize("nom", ["inconnue", None, 3])
    def test_voix_inconnue(self, pocket, nom):
        with pytest.raises(VoixIndisponible):
            pocket.synthese("a", {"name": nom})

    def test_echec_du_modele_devient_voix_indisponible(self, pocket):
        pocket.faux.voix_cassees.add("estelle")
        with pytest.raises(VoixIndisponible, match="OSError"):
            pocket.synthese("a", {"name": "estelle"})

    def test_prechauffer_ecarte_les_voix_indisponibles(self, pocket, caplog):
        pocket.faux.voix_cassees.add("marius")
        pocket.prechauffer()
        assert [v["name"] for v, _ in pocket.catalogue()] == ["estelle"]
        assert "marius" in caplog.text and pocket.faux.etats == ["estelle"]

    def test_sans_le_paquet(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "pocket_tts", None)
        moteur = voix.Pocket({}, tmp_path)
        assert moteur.catalogue() == []
        with pytest.raises(VoixIndisponible):
            moteur.synthese("a", {"name": "estelle"})


# --- Edge ----------------------------------------------------------------------------------------
class FauxEdge:
    """Remplace le module edge_tts : garde chaque Communicate demandé."""
    demandes = []
    morceaux = [{"type": "WordBoundary", "data": b"ignore"}, {"type": "audio", "data": b"mp3-"},
                {"type": "audio", "data": b"fin"}]
    erreur = None

    class Communicate:
        def __init__(self, texte, voix, rate, pitch):
            FauxEdge.demandes.append({"texte": texte, "voix": voix, "rate": rate, "pitch": pitch})

        def stream_sync(self):
            if FauxEdge.erreur:
                raise FauxEdge.erreur
            return iter(FauxEdge.morceaux)


@pytest.fixture
def edge(tmp_path, monkeypatch):
    FauxEdge.demandes, FauxEdge.erreur = [], None
    FauxEdge.morceaux = [{"type": "WordBoundary", "data": b"ignore"}, {"type": "audio", "data": b"mp3-"},
                         {"type": "audio", "data": b"fin"}]
    monkeypatch.setitem(sys.modules, "edge_tts", FauxEdge)
    return voix.Edge({}, tmp_path)


class TestEdge:
    def test_catalogue(self, edge):
        catalogue = dict((v["name"], (v["label"], g)) for v, g in edge.catalogue())
        assert catalogue["fr-FR-DeniseNeural"] == ("Denise (FR)", "feminin")
        assert catalogue["fr-FR-RemyMultilingualNeural"] == ("Remy (FR)", "masculin")
        assert catalogue["fr-BE-GerardNeural"][0] == "Gerard (BE)"

    def test_synthese_garde_seulement_l_audio(self, edge):
        audio, mime = edge.synthese("Bonjour.", {"name": "fr-FR-DeniseNeural"})
        assert (audio, mime) == (b"mp3-fin", "audio/mpeg")
        assert FauxEdge.demandes[0] == {"texte": "Bonjour.", "voix": "fr-FR-DeniseNeural", "rate": "+0%",
                                        "pitch": "+0Hz"}

    @pytest.mark.parametrize(("echelle", "timbre", "rate", "pitch"), [
        (1.25, "grave", "-20%", "-8Hz"),   # débit lent : length_scale 1,25 → 80 % de la vitesse
        (0.8, "aigu", "+25%", "+8Hz"),      # débit rapide
        (1.0, "moyen", "+0%", "+0Hz"),
        (5.0, None, "-50%", "+0Hz"),        # échelle bornée à 2
        ("abc", None, "+0%", "+0Hz"),       # illisible : débit normal
    ])
    def test_debit_et_hauteur_de_la_fiche(self, edge, echelle, timbre, rate, pitch):
        edge.synthese("a", {"name": "fr-FR-DeniseNeural", "length_scale": echelle, "timbre": timbre})
        assert (FauxEdge.demandes[0]["rate"], FauxEdge.demandes[0]["pitch"]) == (rate, pitch)

    @pytest.mark.parametrize("nom", ["fr-FR-Inconnue", None, 4])
    def test_voix_inconnue(self, edge, nom):
        with pytest.raises(VoixIndisponible):
            edge.synthese("a", {"name": nom})
        assert FauxEdge.demandes == []

    def test_reseau_coupe(self, edge):
        FauxEdge.erreur = ConnectionError("hors ligne")
        with pytest.raises(VoixIndisponible, match="ConnectionError"):
            edge.synthese("a", {"name": "fr-FR-DeniseNeural"})

    def test_aucun_son(self, edge):
        FauxEdge.morceaux = [{"type": "WordBoundary", "data": b"x"}]
        with pytest.raises(VoixIndisponible, match="aucun son"):
            edge.synthese("a", {"name": "fr-FR-DeniseNeural"})

    def test_sans_le_paquet(self, tmp_path, monkeypatch):
        monkeypatch.setitem(sys.modules, "edge_tts", None)
        moteur = voix.Edge({}, tmp_path)
        assert moteur.catalogue() == []
        with pytest.raises(VoixIndisponible):
            moteur.synthese("a", {"name": "fr-FR-DeniseNeural"})


# --- portraits.Local -----------------------------------------------------------------------------
class FausseImage:
    def save(self, tampon, format):
        tampon.write(b"\x89PNG-" + format.encode())


class FauxPipe:
    def __init__(self):
        self.appels, self.appareil, self.options = [], None, []

    def to(self, appareil):
        self.appareil = appareil
        return self

    def enable_attention_slicing(self):
        self.options.append("slicing")

    def set_progress_bar_config(self, disable):
        self.options.append(f"barre-{disable}")

    def __call__(self, **kwargs):
        self.appels.append(kwargs)
        return SimpleNamespace(images=[FausseImage()])


@pytest.fixture
def sd(monkeypatch):
    """Faux torch et diffusers ; `sd.pipe` est le pipeline chargé, `sd.cuda` choisit l'appareil automatique."""
    etat = SimpleNamespace(pipe=FauxPipe(), cuda=False, chargements=[], erreur=None, graines=[])

    def from_pretrained(modele, torch_dtype, variant):
        if etat.erreur:
            raise etat.erreur
        etat.chargements.append((modele, torch_dtype, variant))
        return etat.pipe
    torch = SimpleNamespace(
        float16="f16", float32="f32", cuda=SimpleNamespace(is_available=lambda: etat.cuda),
        Generator=lambda device: SimpleNamespace(manual_seed=lambda g: etat.graines.append((device, g)) or "gen"))
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "diffusers", SimpleNamespace(
        AutoPipelineForText2Image=SimpleNamespace(from_pretrained=from_pretrained)))
    monkeypatch.setattr(portraits.importlib.util, "find_spec", lambda nom: object())
    return etat


class TestPortraitLocal:
    def test_generation_sur_le_processeur(self, sd):
        local = portraits.Local({"etapes": 3, "taille": 256})
        assert local.disponible()
        assert local.generer("un nain", 42) == (b"\x89PNG-PNG", "png")
        assert sd.chargements == [("stabilityai/sd-turbo", "f32", "fp16")]
        assert sd.pipe.appareil == "cpu" and sd.pipe.options == ["barre-True"]
        assert sd.pipe.appels == [{"prompt": "un nain", "num_inference_steps": 3, "guidance_scale": 0.0,
                                   "width": 256, "height": 256, "generator": "gen"}]
        assert sd.graines == [("cpu", 42)]

    def test_cuda_automatique_demi_precision_et_decoupage(self, sd):
        sd.cuda = True
        portraits.Local({}).generer("x", 1)
        assert sd.chargements[0][1] == "f16" and sd.pipe.appareil == "cuda" and "slicing" in sd.pipe.options

    def test_appareil_force(self, sd):
        sd.cuda = True
        portraits.Local({"appareil": "cpu"}).generer("x", 1)
        assert sd.pipe.appareil == "cpu"

    def test_modele_charge_une_seule_fois(self, sd):
        local = portraits.Local({})
        local.generer("a", 1)
        local.generer("b", 2)
        assert len(sd.chargements) == 1 and len(sd.pipe.appels) == 2

    def test_modele_introuvable(self, sd):
        sd.erreur = OSError("hors ligne")
        with pytest.raises(PortraitIndisponible, match="introuvable.*télécharge"):
            portraits.Local({}).generer("x", 1)

    def test_paquets_absents(self, sd, monkeypatch):
        monkeypatch.setattr(portraits.importlib.util, "find_spec", lambda nom: None if nom == "diffusers" else object())
        local = portraits.Local({})
        assert not local.disponible()
        with pytest.raises(PortraitIndisponible, match="option portraits"):
            local.generer("x", 1)
