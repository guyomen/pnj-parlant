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


def test_taille_de_fenetre_de_contexte_connue_ou_non():
    config = json.loads(json.dumps(CONFIG))
    moteurs = Moteurs(config)
    assert moteurs.contexte_max() == 8192
    moteurs.local_cfg["contexte"] = 4096
    assert moteurs.contexte_max() == 4096
    moteurs.choix["dialogue"] = "claude"
    assert moteurs.contexte_max() is None
    moteurs.claude_cfg["contexte"] = 200000
    assert moteurs.contexte_max() == 200000
    moteurs.claude_cfg["contexte"] = True
    assert moteurs.contexte_max() is None


class FausseReponseOllama:
    """Réponse HTTP en streaming d'Ollama : une ligne JSON par morceau de texte."""

    def __init__(self, morceaux, usage=None):
        self.lignes = [json.dumps({"message": {"content": m}}).encode() + b"\n" for m in morceaux]
        if usage:
            self.lignes.append(json.dumps({"done": True, **usage}).encode() + b"\n")
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

    def test_compteurs_usage_ollama(self, ollama):
        ollama["reponse"] = FausseReponseOllama(["Salut."], {"prompt_eval_count": 123, "eval_count": 9})
        usage = {}
        moteur = Moteurs(json.loads(json.dumps(CONFIG)))
        assert "".join(moteur.replique("s", [{"role": "user", "content": "a"}],
                                       on_usage=usage.update)) == "Salut."
        assert usage == {"input_tokens": 123, "output_tokens": 9}

    @pytest.mark.parametrize(("longueur", "attendu"), [("short", 100), ("normal", 200), ("long", 400)])
    def test_budget_tokens_selon_longueur(self, ollama, longueur, attendu):
        moteur = Moteurs(json.loads(json.dumps(CONFIG)))
        list(moteur.replique("s", [{"role": "user", "content": "a"}], longueur=longueur))
        assert ollama["requetes"][-1]["options"]["num_predict"] == attendu

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


def test_compteurs_usage_claude(monkeypatch):
    from types import SimpleNamespace

    config = json.loads(json.dumps(CONFIG))
    config["moteurs"]["dialogue"] = "claude"
    moteurs = Moteurs(config)
    events = [
        SimpleNamespace(type="message_start", message=SimpleNamespace(usage=SimpleNamespace(
            input_tokens=10, cache_read_input_tokens=2, cache_creation_input_tokens=1))),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="Salut.")),
        SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn"),
                         usage=SimpleNamespace(output_tokens=4)),
    ]

    class Flux(list):
        def close(self):
            pass

    monkeypatch.setattr(moteurs.client.messages, "create", lambda **kwargs: Flux(events))
    usage = {}
    assert "".join(moteurs.replique("s", [{"role": "user", "content": "a"}],
                                    on_usage=usage.update)) == "Salut."
    assert usage == {"input_tokens": 13, "output_tokens": 4}


class FausseReponseLMStudio(FausseReponseOllama):
    """Réponse HTTP de LM Studio : flux SSE au format OpenAI, ou JSON d'un bloc (`corps`)."""

    def __init__(self, morceaux=(), usage=None, corps=None):
        super().__init__([])
        self.corps = corps
        self.lignes = [b"data: " + json.dumps({"choices": [{"delta": {"content": m}}]}).encode() + b"\n\n"
                       for m in morceaux]
        if usage:
            self.lignes.append(b"data: " + json.dumps({"choices": [], "usage": usage}).encode() + b"\n\n")
        self.lignes.append(b"data: [DONE]\n\n")

    def read(self):
        return json.dumps(self.corps).encode()


MODELES_LMSTUDIO = {"data": [
    {"id": "nomic-embed", "type": "embeddings", "state": "loaded"},
    {"id": "gemma-pas-charge", "type": "llm", "state": "not-loaded"},
    {"id": "qwen-charge", "type": "llm", "state": "loaded", "loaded_context_length": 32768},
]}


@pytest.fixture
def lmstudio(monkeypatch):
    """Remplace les appels HTTP à LM Studio ; garde le corps de chaque requête de dialogue."""
    etat = {"requetes": [], "modeles": MODELES_LMSTUDIO,
            "reponse": FausseReponseLMStudio(["Bonjour, ", "voyageur."])}

    def urlopen(req, timeout=None):
        if isinstance(req, str):  # liste des modèles
            return FausseReponseLMStudio(corps=etat["modeles"])
        etat["requetes"].append(json.loads(req.data))
        return etat["reponse"]
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    config = json.loads(json.dumps(CONFIG))
    config["moteurs"] = {"creation": "lmstudio", "dialogue": "lmstudio"}
    config["lmstudio"] = {"url": "http://lmstudio:1234", "modele": "", "reflexion": False,
                          "generation": {"max_tokens": 1500}, "dialogue": {"max_tokens": 200}}
    etat["moteurs"] = Moteurs(config)
    return etat


class TestLMStudio:
    def test_replique_en_flux_avec_le_modele_charge(self, lmstudio):
        assert "".join(lmstudio["moteurs"].replique("Tu es Berthe.", [{"role": "user", "content": "Salut"}],
                                                    ARRETS)) == "Bonjour, voyageur."
        corps = lmstudio["requetes"][-1]
        assert corps["model"] == "qwen-charge"  # ni le modèle d'embedding, ni un modèle non chargé
        assert corps["stop"] == ARRETS and corps["stream"] is True and corps["max_tokens"] == 200
        assert corps["reasoning_effort"] == "none"
        assert corps["messages"][0] == {"role": "system", "content": "Tu es Berthe."}

    def test_compteurs_usage_lmstudio(self, lmstudio):
        lmstudio["reponse"] = FausseReponseLMStudio(["Salut."], {"prompt_tokens": 50, "completion_tokens": 3})
        usage = {}
        list(lmstudio["moteurs"].replique("s", [{"role": "user", "content": "a"}], on_usage=usage.update))
        assert usage == {"input_tokens": 50, "output_tokens": 3}

    def test_reponse_abandonnee_la_connexion_est_fermee(self, lmstudio):
        flux = lmstudio["moteurs"].replique("s", [{"role": "user", "content": "a"}])
        next(flux)
        flux.close()
        assert lmstudio["reponse"].fermee

    def test_fiche_au_schema_json_sans_raisonnement(self, lmstudio):
        lmstudio["reponse"] = FausseReponseLMStudio(corps={"choices": [
            {"finish_reason": "stop", "message": {"content": '<think>hmm</think>{"nom": "Brom"}'}}]})
        assert lmstudio["moteurs"].fiche("s", "Un forgeron", {"type": "object"}) == '{"nom": "Brom"}'
        corps = lmstudio["requetes"][-1]
        assert corps["response_format"]["json_schema"]["schema"] == {"type": "object"}
        assert corps["stream"] is False and corps["max_tokens"] == 1500

    def test_taille_de_contexte_du_modele_charge(self, lmstudio):
        assert lmstudio["moteurs"].contexte_max() == 32768

    def test_aucun_modele_charge(self, lmstudio):
        lmstudio["modeles"] = {"data": [MODELES_LMSTUDIO["data"][1]]}
        with pytest.raises(MoteurIndisponible, match="Aucun modèle chargé"):
            lmstudio["moteurs"].replique("s", [{"role": "user", "content": "a"}])

    def test_lmstudio_injoignable(self, monkeypatch, lmstudio):
        def urlopen(req, timeout=None):
            raise module.urllib.error.URLError("refusé")
        monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
        with pytest.raises(MoteurIndisponible, match="LM Studio injoignable"):
            lmstudio["moteurs"].replique("s", [{"role": "user", "content": "a"}])
        assert lmstudio["moteurs"].contexte_max() is None
