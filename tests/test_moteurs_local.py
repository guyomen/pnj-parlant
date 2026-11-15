"""Branches de moteurs.py sans test jusque-là (lot 7.2) : Ollama hors flux (`_local`, fiche), modèle absent (404),
liste des modèles installés, Claude (connexion, refus, coupure à max_tokens), LM Studio hors flux. Même montage
que test_moteurs.py : `urllib.request.urlopen` remplacé, aucun réseau."""
import io
import json
from types import SimpleNamespace

import anthropic
import pytest
from test_moteurs import CONFIG

from pnj_parlant import moteurs as module
from pnj_parlant.moteurs import MoteurIndisponible, Moteurs

MESSAGE = [{"role": "user", "content": "Salut"}]


def moteurs(**changements):
    config = json.loads(json.dumps(CONFIG))
    for cle, valeur in changements.items():
        config.setdefault(cle, {}).update(valeur)
    return Moteurs(config)


class Reponse(io.BytesIO):
    """Réponse HTTP simple : un corps JSON lu d'un coup, utilisable comme gestionnaire de contexte."""

    def __init__(self, donnees):
        super().__init__(donnees if isinstance(donnees, bytes) else json.dumps(donnees).encode())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def erreur_http(code, corps=b"", url="http://ollama:11434/api/chat"):
    return module.urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(corps))


def urlopen_renvoie(monkeypatch, valeur):
    """`urlopen` renvoie `valeur` (ou la lève si c'est une exception) ; renvoie la liste des requêtes reçues."""
    vues = []

    def urlopen(req, timeout=None):
        vues.append((req, timeout))
        if isinstance(valeur, Exception):
            raise valeur
        return valeur
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    return vues


# --- Ollama : fiche (réponse d'un bloc) ----------------------------------------------------------
class TestOllamaFiche:
    def test_fiche_au_schema_json(self, monkeypatch):
        vues = urlopen_renvoie(monkeypatch, Reponse({"message": {"content": '{"nom": "Ysolde"}'}}))
        assert moteurs().fiche("s", "demande", {"type": "object"}) == '{"nom": "Ysolde"}'
        corps = json.loads(vues[0][0].data)
        assert corps["stream"] is False and corps["format"] == {"type": "object"}
        assert corps["messages"][-1] == {"role": "user", "content": "demande"}
        assert corps["options"]["num_predict"] == 1500 and vues[0][1] == 180
        assert vues[0][0].full_url == "http://ollama:11434/api/chat"

    def test_erreur_renvoyee_dans_la_reponse(self, monkeypatch):
        urlopen_renvoie(monkeypatch, Reponse({"error": "modèle déchargé"}))
        with pytest.raises(MoteurIndisponible, match="modèle déchargé"):
            moteurs().fiche("s", "d", {})

    @pytest.mark.parametrize("corps", [b"[1, 2]", b"{}"])
    def test_reponse_sans_message_donne_un_texte_vide(self, monkeypatch, corps):
        urlopen_renvoie(monkeypatch, Reponse(corps))
        assert moteurs().fiche("s", "d", {}) == ""

    def test_reponse_illisible(self, monkeypatch):
        urlopen_renvoie(monkeypatch, Reponse(b"pas du json"))
        with pytest.raises(MoteurIndisponible, match="interrompu"):
            moteurs().fiche("s", "d", {})

    def test_modele_absent_404(self, monkeypatch):
        urlopen_renvoie(monkeypatch, erreur_http(404, b'{"error":"model not found"}'))
        with pytest.raises(MoteurIndisponible, match=r"« qwen3:4b-instruct » absent.*ollama pull qwen3:4b-instruct"):
            moteurs(local={"modele": "qwen3:4b-instruct"}).fiche("s", "d", {})

    def test_modele_absent_aussi_en_dialogue(self, monkeypatch):
        urlopen_renvoie(monkeypatch, erreur_http(404))
        with pytest.raises(MoteurIndisponible, match="absent"):
            moteurs().replique("s", MESSAGE)

    def test_autre_erreur_http_avec_son_detail_tronque(self, monkeypatch):
        urlopen_renvoie(monkeypatch, erreur_http(500, b"x" * 500))
        with pytest.raises(MoteurIndisponible) as e:
            moteurs().replique("s", MESSAGE)
        assert "erreur" in str(e.value) and str(e.value).count("x") == 200

    @pytest.mark.parametrize("panne", [ConnectionRefusedError(), module.urllib.error.URLError("refusé")])
    def test_injoignable(self, monkeypatch, panne):
        urlopen_renvoie(monkeypatch, panne)
        with pytest.raises(MoteurIndisponible, match="docker compose up"):
            moteurs().fiche("s", "d", {})

    def test_reflexion_et_delai_de_la_configuration(self, monkeypatch):
        vues = urlopen_renvoie(monkeypatch, Reponse({"message": {"content": "x"}}))
        moteurs(local={"reflexion": True, "delai_max": 7, "contexte": 2048}).fiche("s", "d", {})
        corps = json.loads(vues[0][0].data)
        assert corps["think"] is True and vues[0][1] == 7 and corps["options"]["num_ctx"] == 2048


# --- Ollama : modèles installés ------------------------------------------------------------------
class TestModelesLocaux:
    def test_liste(self, monkeypatch):
        vues = urlopen_renvoie(monkeypatch, Reponse({"models": [{"name": "qwen3:4b", "size": 2_000_000_000},
                                                                {"name": "mistral-nemo:latest"}]}))
        assert moteurs().modeles_locaux() == [{"nom": "qwen3:4b", "taille": 2_000_000_000},
                                              {"nom": "mistral-nemo:latest", "taille": 0}]
        assert vues[0][0] == "http://ollama:11434/api/tags" and vues[0][1] == 3

    @pytest.mark.parametrize("valeur", [OSError("refusé"), b"pas du json", b'{"autre": []}',
                                        b'{"models": [{"size": 1}]}'])
    def test_ollama_ne_repond_pas_liste_vide(self, monkeypatch, valeur):
        urlopen_renvoie(monkeypatch, valeur if isinstance(valeur, Exception) else Reponse(valeur))
        assert moteurs().modeles_locaux() == []

    def test_modele_installe_avec_ou_sans_latest(self):
        m = moteurs(local={"modele": "mistral-nemo"})
        installes = [{"nom": "autre:1b"}, {"nom": "mistral-nemo:latest"}]
        assert m.modele_local_installe(installes) == "mistral-nemo:latest"
        assert m.modele_local_installe([{"nom": "autre:1b"}]) == "mistral-nemo"  # pas installé : le nom configuré
        assert m.modele_local_installe([{"nom": "mistral-nemo"}]) == "mistral-nemo"
        assert m.modele_local_installe([]) == "mistral-nemo"


# --- Claude ---------------------------------------------------------------------------------------
def claude():
    return moteurs(moteurs={"creation": "claude", "dialogue": "claude"})


class TestClaudeErreurs:
    @staticmethod
    def lever(monkeypatch, m, erreur):
        def create(**kwargs):
            raise erreur
        monkeypatch.setattr(m.client.messages, "create", create)

    def test_pas_de_connexion(self, monkeypatch):
        m = claude()
        self.lever(monkeypatch, m, anthropic.APIConnectionError(request=module.httpx.Request("POST", "http://x")))
        with pytest.raises(MoteurIndisponible, match="Pas de connexion"):
            m.fiche("s", "d", {})
        with pytest.raises(MoteurIndisponible, match="Pas de connexion"):
            m.replique("s", MESSAGE)

    def test_requete_refusee_avec_son_code(self, monkeypatch):
        m = claude()
        reponse = module.httpx.Response(401, request=module.httpx.Request("POST", "http://x"))
        self.lever(monkeypatch, m, anthropic.AuthenticationError("clé", response=reponse, body=None))
        with pytest.raises(MoteurIndisponible, match=r"refusé la requête \(401\)"):
            m.fiche("s", "d", {})
        with pytest.raises(MoteurIndisponible, match=r"\(401\)"):
            m.replique("s", MESSAGE)

    def test_erreur_http_de_bas_niveau_en_flux(self, monkeypatch):
        m = claude()
        self.lever(monkeypatch, m, module.httpx.ConnectError("réseau coupé"))
        with pytest.raises(MoteurIndisponible, match="interrompue"):
            m.replique("s", MESSAGE)

    def test_fiche_coupee_a_max_tokens_garde_le_texte(self, monkeypatch, capsys):
        m = claude()
        msg = SimpleNamespace(stop_reason="max_tokens", content=[SimpleNamespace(type="text", text='{"nom": "Y')])
        monkeypatch.setattr(m.client.messages, "create", lambda **kw: msg)
        assert m.fiche("s", "d", {}) == '{"nom": "Y'
        assert "max_tokens=2000" in capsys.readouterr().out

    def test_flux_complet_texte_usage_et_fermeture(self, monkeypatch, capsys):
        m = claude()
        evenements = [
            SimpleNamespace(type="message_start", message=SimpleNamespace(usage=SimpleNamespace(
                input_tokens=10, cache_read_input_tokens=5, cache_creation_input_tokens=None))),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="Salut ")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="input_json_delta", text="?")),
            SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text="voyageur.")),
            SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="max_tokens"),
                            usage=SimpleNamespace(output_tokens=7)),
        ]
        etat = {"ferme": False}

        class Flux:
            def __iter__(self):
                return iter(evenements)

            def close(self):
                etat["ferme"] = True
        appels = []
        monkeypatch.setattr(m.client.messages, "create", lambda **kw: appels.append(kw) or Flux())
        usage = {}
        assert "".join(m.replique("s", MESSAGE, ["Léo :"], on_usage=usage.update)) == "Salut voyageur."
        assert usage == {"input_tokens": 15, "output_tokens": 7} and etat["ferme"]
        assert appels[0]["stop_sequences"] == ["Léo :"] and appels[0]["stream"] is True
        assert "coupée" in capsys.readouterr().out


# --- LM Studio hors flux --------------------------------------------------------------------------
class TestLMStudioFiche:
    def lmstudio(self, **cfg):
        return moteurs(moteurs={"creation": "lmstudio", "dialogue": "lmstudio"},
                       lmstudio={"modele": "qwen", **cfg})

    def test_fiche_sans_raisonnement(self, monkeypatch):
        vues = urlopen_renvoie(monkeypatch, Reponse({"choices": [
            {"message": {"content": "<think>hum</think>\n{\"nom\": \"Ysolde\"}"}, "finish_reason": "length"}]}))
        assert self.lmstudio().fiche("s", "d", {"type": "object"}) == '{"nom": "Ysolde"}'
        corps = json.loads(vues[0][0].data)
        assert corps["response_format"]["json_schema"]["schema"] == {"type": "object"}
        assert corps["reasoning_effort"] == "none" and corps["stream"] is False

    def test_message_sans_contenu(self, monkeypatch):
        urlopen_renvoie(monkeypatch, Reponse({"choices": [{"message": {"content": None}}]}))
        assert self.lmstudio().fiche("s", "d", {}) == ""

    def test_erreur_http(self, monkeypatch):
        urlopen_renvoie(monkeypatch, erreur_http(400, b"schema invalide", "http://lm/v1/chat/completions"))
        with pytest.raises(MoteurIndisponible, match="schema invalide"):
            self.lmstudio().fiche("s", "d", {})

    def test_erreur_dans_la_reponse(self, monkeypatch):
        urlopen_renvoie(monkeypatch, Reponse({"error": {"message": "aucun modèle"}}))
        with pytest.raises(MoteurIndisponible, match="aucun modèle"):
            self.lmstudio().fiche("s", "d", {})

    def test_contexte_max_sans_serveur(self, monkeypatch):
        urlopen_renvoie(monkeypatch, OSError("refusé"))
        m = moteurs(moteurs={"creation": "lmstudio", "dialogue": "lmstudio"})
        assert m.contexte_max() is None  # aucun modèle connu : pas d'exception

