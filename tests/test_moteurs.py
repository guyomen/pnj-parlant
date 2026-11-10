"""Requêtes envoyées aux modèles de langage, sans réseau : Ollama et Claude sont simulés."""
import json

import pytest

from pnj_parlant import moteurs as module
from pnj_parlant.moteurs import MoteurIndisponible, Moteurs

CONFIG = {
    "moteurs": {"creation": "local", "dialogue": "local"},
    "claude": {"cle_api": "sk-ant-test", "modele": "claude-haiku-5-5",
               "generation": {"max_tokens": 2000, "effort": "low"}, "dialogue": {"max_tokens": 250, "effort": "low"}},
    "local": {"url": "http://ollama:11434", "modele": "qwen3:4b-instruct", "reflexion": False,
              "generation": {"max_tokens": 1500}, "dialogue": {"max_tokens": 200}},
}
ARRETS = ["Léonard :", "Léonard:"]


class FausseReponseOllama:
    """Réponse HTTP en streaming d'Ollama : une ligne JSON par morceau de texte."""

    def __init__(self, morceaux):
        self.lignes = [json.dumps({"message": {"content": m}}).encode() + b"\n" for m in morceaux]
        self.fermee = False

    def __iter__(self):
        return iter(self.lignes)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fermee = True


@pytest.fixture
def ollama(monkeypatch):
    """Remplace l'appel HTTP à Ollama ; garde le corps de chaque requête envoyée."""
    etat = {"requetes": [], "reponse": FausseReponseOllama(["Bonjour, ", "voyageur."])}

    def urlopen(req, timeout=None):
        etat["requetes"].append(json.loads(req.data))
        return etat["reponse"]
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    return etat


class TestOllama:
    def test_sequences_d_arret_envoyees_dans_les_options(self, ollama):
        moteurs = Moteurs(json.loads(json.dumps(CONFIG)))
        assert "".join(moteurs.replique("Tu es Berthe.", [{"role": "user", "content": "Salut"}], ARRETS)) == \
            "Bonjour, voyageur."
        corps = ollama["requetes"][-1]
        assert corps["options"]["stop"] == ARRETS
        assert corps["options"]["num_predict"] == 200 and corps["stream"] is True and corps["think"] is False
        assert corps["messages"][0] == {"role": "system", "content": "Tu es Berthe."}

    def test_sans_arret_pas_d_option_stop(self, ollama):
        list(Moteurs(json.loads(json.dumps(CONFIG))).replique("Tu es Berthe.", [{"role": "user", "content": "a"}]))
        assert "stop" not in ollama["requetes"][-1]["options"]

    def test_reponse_abandonnee_la_connexion_est_fermee(self, ollama):
        flux = Moteurs(json.loads(json.dumps(CONFIG))).replique("s", [{"role": "user", "content": "a"}], ARRETS)
        next(flux)
        flux.close()  # ce que fait dialogue.repliques quand il coupe la réponse
        assert ollama["reponse"].fermee

    def test_ollama_injoignable(self, monkeypatch):
        def urlopen(req, timeout=None):
            raise module.urllib.error.URLError("refusé")
        monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
        with pytest.raises(MoteurIndisponible):
            Moteurs(json.loads(json.dumps(CONFIG))).replique("s", [{"role": "user", "content": "a"}])


def test_claude_recoit_les_sequences_d_arret(monkeypatch):
    config = json.loads(json.dumps(CONFIG))
    config["moteurs"]["dialogue"] = "claude"
    moteurs = Moteurs(config)
    appels = []

    class FluxVide(list):
        def close(self):
            pass

    def create(**kwargs):
        appels.append(kwargs)
        return FluxVide()
    monkeypatch.setattr(moteurs.client.messages, "create", create)
    list(moteurs.replique("Tu es Berthe.", [{"role": "user", "content": "Salut"}], ARRETS))
    assert appels[-1]["stop_sequences"] == ARRETS and appels[-1]["stream"] is True
