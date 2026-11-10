"""
Faux moteurs pour tester sans réseau, sans modèle et sans carte graphique :
FauxMoteurs (modèle de langage), FauxTTS (synthèse vocale), FausseReconnaissance (Whisper).
"""
import json

import pytest

from pnj_parlant.config import Config
from pnj_parlant.moteurs import MoteurIndisponible
from pnj_parlant.serveur import create_app

FICHE = {
    "nom": "Ysolde la Rousse", "metier": "aubergiste", "apparence": "Une femme trapue aux bras farineux.",
    "personnalite": "Bavarde et rusée.", "humeur": "joviale",
    "connaissances": ["Le pont est gardé.", "Le meunier boit.", "Un dragon rôde."],
    "secret": "Elle dilue la bière.", "salutation": "*Elle sourit.* Bienvenue, voyageur ! 🍺",
    "genre": "feminin", "timbre": "moyen", "debit": "normal",
}


class FauxMoteurs:
    """Remplace moteurs.Moteurs. `reponses` : liste de morceaux (répliques) ou exception à lever."""

    def __init__(self):
        self.choix = {"creation": "local", "dialogue": "local"}
        self.local_cfg = {"url": "http://localhost:1", "modele": "faux"}
        self.fiche_json = json.dumps(FICHE, ensure_ascii=False)
        self.reponses = ["Bonjour."]
        self.usage = None
        self.appels = []  # (system, messages) de chaque réplique demandée
        self.arrets = []  # séquences d'arrêt de chaque réplique demandée
        self.longueurs = []

    def description(self):
        return {"creation": "local : faux", "dialogue": "local : faux"}

    def contexte_max(self):
        return 8192

    def modeles_locaux(self):
        return []

    def modele_local_installe(self, installes):
        return self.local_cfg["modele"]

    def choisir_modele_local(self, nom):
        raise MoteurIndisponible(f"Modèle local « {nom} » absent d'Ollama.")

    def fiche(self, system, demande, schema):
        self.derniere_demande = demande
        if isinstance(self.fiche_json, Exception):
            raise self.fiche_json
        return self.fiche_json

    def replique(self, system, messages, arrets=(), on_usage=None, longueur="normal"):
        self.appels.append((system, messages))
        self.arrets.append(list(arrets))
        self.longueurs.append(longueur)
        if isinstance(self.reponses, Exception):
            raise self.reponses
        def flux():
            yield from self.reponses
            if on_usage and self.usage:
                on_usage(self.usage)
        return flux()


VOIX = [({"name": "alice", "label": "Alice"}, "feminin"), ({"name": "bea", "label": "Béa"}, "feminin"),
        ({"name": "bob", "label": "Bob"}, "masculin"), ({"name": "carl", "label": "Carl"}, "masculin"),
        ({"name": "nora", "label": "Nora"}, "feminin")]


class FauxTTS:
    """Remplace un moteur de voix.py : cinq voix, « nora » est la voix du narrateur."""
    nom = "faux"
    narrateur = "nora"
    narrateur_locuteur = None

    def __init__(self, voix=VOIX):
        self.voix = voix
        self.lues = []  # (texte, voix) de chaque synthèse

    def catalogue(self):
        return list(self.voix)

    def prechauffer(self):
        pass

    def synthese(self, texte, voix):
        self.lues.append((texte, voix))
        return b"RIFF" + texte.encode(), "audio/wav"


class FausseReconnaissance:
    choisie = False
    dossier = None

    def disponible(self):
        return False


@pytest.fixture
def cfg(tmp_path):
    return Config({"dialogue": {"historique": 12, "intervention": 0.3}, "banque": {"dossier": "pnj"}}, tmp_path)


@pytest.fixture
def moteurs():
    return FauxMoteurs()


@pytest.fixture
def tts():
    return FauxTTS()


@pytest.fixture
def app(cfg, moteurs, tts):
    return create_app(cfg, moteurs=moteurs, tts=tts, reconnaissance=FausseReconnaissance())


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ctx(app):
    return app.extensions["pnj"]
