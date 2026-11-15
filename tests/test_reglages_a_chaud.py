"""Application à chaud des réglages quand les moteurs ne sont PAS injectés (lot 7.1) : les gardes
`injectes[...]` de Contexte._appliquer_reglages sont toujours fausses dans les autres tests, qui injectent leurs
faux. Ici `serveur.Moteurs`, `serveur.voix.charger` et `serveur.Reconnaissance` sont remplacés."""
import sys
import threading
import tomllib

import pytest
from faux import FauxMoteurs, FauxTTS

from pnj_parlant import serveur
from pnj_parlant.config import Config
from pnj_parlant.serveur import create_app

CONFIG = """[moteurs]
creation = "local"
dialogue = "local"

[claude]
modele = "claude-haiku-5-5"

[voix]
moteur = "piper"

[reconnaissance]
moteur = "navigateur"

[dialogue]
historique = 12
"""
VOIX = [({"name": "alice", "label": "Alice"}, "feminin")]


class MoteursConstruits(FauxMoteurs):
    """Remplace moteurs.Moteurs : garde les réglages avec lesquels il a été construit."""
    construits = []

    def __init__(self, reglages):
        super().__init__()
        self.reglages = reglages
        MoteursConstruits.construits.append(self)


class Voix(FauxTTS):
    def __init__(self, nom, voix):
        super().__init__(voix)
        self.nom = nom
        self.prechauffee = threading.Event()

    def prechauffer(self):
        self.prechauffee.set()


class Reco:
    """Remplace stt.Reconnaissance : `chargee` permet de vérifier le préchargement en arrière-plan."""
    construites = []
    installee = True
    choisie = False
    dossier = None

    def __init__(self, cfg, racine):
        self.cfg = cfg
        self.chargee = threading.Event()
        Reco.construites.append(self)

    def disponible(self):
        return Reco.installee

    def charger(self):
        self.chargee.set()


@pytest.fixture
def chaud(tmp_path, monkeypatch):
    """(client, contexte, config.toml, voix construites, catalogues) : serveur sans aucun moteur injecté."""
    MoteursConstruits.construits = []
    Reco.construites, Reco.installee = [], True
    voix_construites = []
    catalogues = {"piper": VOIX, "pocket": VOIX, "edge": VOIX}

    def charger(reglages, racine, moteur=None):
        nom = moteur or reglages["voix"]["moteur"]
        v = Voix(nom, catalogues[nom])
        voix_construites.append(v)
        return v
    monkeypatch.setattr(serveur, "Moteurs", MoteursConstruits)
    monkeypatch.setattr(serveur.voix, "charger", charger)
    monkeypatch.setattr(serveur, "Reconnaissance", Reco)
    monkeypatch.setattr(serveur.time, "sleep", lambda s: None)
    fichier = tmp_path / "config.toml"
    fichier.write_text(CONFIG, encoding="utf-8")
    app = create_app(Config(tomllib.loads(CONFIG), tmp_path, fichier))
    return app.test_client(), app.extensions["pnj"], fichier, voix_construites, catalogues


def mettre(client, **changements):
    return client.put("/api/reglages", json={"changements": changements})


def test_modele_claude_reconstruit_les_moteurs(chaud):
    client, ctx, fichier, _, _ = chaud
    avant = ctx.moteurs
    assert mettre(client, **{"claude.modele": "claude-sonnet-5-5"}).status_code == 200
    assert ctx.moteurs is not avant and ctx.moteurs is MoteursConstruits.construits[-1]
    assert ctx.moteurs.reglages["claude"]["modele"] == "claude-sonnet-5-5"
    assert tomllib.loads(fichier.read_text(encoding="utf-8"))["claude"]["modele"] == "claude-sonnet-5-5"


def test_reglage_sans_rapport_garde_les_moteurs(chaud):
    client, ctx, _, voix_construites, _ = chaud
    avant, tts = ctx.moteurs, ctx.tts
    assert mettre(client, **{"dialogue.historique": 20}).status_code == 200
    assert ctx.moteurs is avant and ctx.tts is tts and len(voix_construites) == 1 and ctx.historique == 20
    assert mettre(client, **{"claude.modele": "claude-haiku-5-5"}).status_code == 200  # même valeur : rien à refaire
    assert ctx.moteurs is avant


def test_moteur_de_voix_change_et_prechauffe(chaud):
    client, ctx, fichier, _, _ = chaud
    assert mettre(client, **{"voix.moteur": "edge"}).status_code == 200
    assert ctx.tts.nom == "edge" and ctx.tts_charges["edge"] is ctx.tts and "piper" in ctx.tts_charges
    assert ctx.tts.prechauffee.wait(2)
    assert tomllib.loads(fichier.read_text(encoding="utf-8"))["voix"]["moteur"] == "edge"
    piper = ctx.tts_charges["piper"]
    assert mettre(client, **{"voix.moteur": "piper"}).status_code == 200
    assert ctx.tts is piper  # un moteur déjà chargé n'est pas reconstruit


def test_moteur_de_voix_sans_voix_refuse_et_ne_change_rien(chaud):
    client, ctx, fichier, _, catalogues = chaud
    catalogues["pocket"] = []
    avant, tts = fichier.read_text(encoding="utf-8"), ctx.tts
    r = mettre(client, **{"voix.moteur": "pocket", "dialogue.historique": 30})
    assert r.status_code == 400 and "pocket" in r.get_json()["error"] and "utilisable" in r.get_json()["error"]
    assert fichier.read_text(encoding="utf-8") == avant  # config.toml inchangé, même pour l'autre réglage
    assert ctx.tts is tts and ctx.cfg.reglages["voix"]["moteur"] == "piper" and ctx.historique == 12
    assert "pocket" not in ctx.tts_charges


def test_reconnaissance_reconstruite_et_prechargee(chaud):
    client, ctx, fichier, _, _ = chaud
    avant = ctx.reconnaissance
    assert mettre(client, **{"reconnaissance.moteur": "local"}).status_code == 200
    assert ctx.reconnaissance is not avant and ctx.reconnaissance is Reco.construites[-1]
    assert ctx.reconnaissance.cfg["moteur"] == "local"
    assert ctx.reconnaissance.chargee.wait(2)  # le modèle est chargé en arrière-plan
    assert tomllib.loads(fichier.read_text(encoding="utf-8"))["reconnaissance"]["moteur"] == "local"


def test_reconnaissance_indisponible_n_est_pas_prechargee(chaud):
    client, ctx, *_ = chaud
    Reco.installee = False
    assert mettre(client, **{"reconnaissance.moteur": "local"}).status_code == 200
    assert not ctx.reconnaissance.chargee.wait(0.2)


def test_ecriture_impossible_laisse_la_memoire_intacte(chaud, monkeypatch):
    client, ctx, fichier, _, _ = chaud

    def echec(chemin, changements):
        raise OSError("disque plein")
    monkeypatch.setattr(serveur.reglages, "ecrire", echec)
    avant, moteurs, reglages_avant = fichier.read_text(encoding="utf-8"), ctx.moteurs, ctx.cfg.reglages
    r = mettre(client, **{"claude.modele": "claude-sonnet-5-5", "dialogue.historique": 30})
    assert r.status_code == 500 and "config.toml" in r.get_json()["error"] and "disque plein" in r.get_json()["error"]
    assert ctx.cfg.reglages is reglages_avant and ctx.cfg.reglages["claude"]["modele"] == "claude-haiku-5-5"
    assert ctx.moteurs is moteurs and ctx.historique == 12
    assert fichier.read_text(encoding="utf-8") == avant


def test_tomlkit_absent_refuse_sans_rien_changer(chaud, monkeypatch):
    client, ctx, fichier, _, _ = chaud
    monkeypatch.setitem(sys.modules, "tomlkit", None)  # `import tomlkit` lève ImportError
    avant, moteurs = fichier.read_text(encoding="utf-8"), ctx.moteurs
    r = mettre(client, **{"claude.modele": "claude-sonnet-5-5"})
    assert r.status_code == 400 and "tomlkit" in r.get_json()["error"]
    assert ctx.moteurs is moteurs and ctx.cfg.reglages["claude"]["modele"] == "claude-haiku-5-5"
    assert fichier.read_text(encoding="utf-8") == avant


def test_diagnostic_refait_apres_un_changement(chaud):
    client, ctx, *_ = chaud
    ctx._sante = (float("inf"), [])  # diagnostic en cache (problemes() interroge Ollama : lent)
    mettre(client, **{"dialogue.historique": 20})
    assert ctx._sante is None
