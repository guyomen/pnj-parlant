"""Lot 1 de l'audit : aucune entrée ni panne prévisible ne donne une erreur 500 ou un silence."""
import json
import math
from types import SimpleNamespace

import anthropic
import pytest
from test_api import BROM, YSOLDE, lignes
from test_moteurs import CONFIG, FausseReponseLMStudio, FausseReponseOllama

from pnj_parlant import banque as module_banque
from pnj_parlant import moteurs as module
from pnj_parlant import reglages, texte, voix
from pnj_parlant.moteurs import DEFAUTS, MoteurIndisponible, Moteurs
from pnj_parlant.portraits import Local, PortraitIndisponible

MESSAGE = [{"role": "user", "content": "Salut"}]


@pytest.fixture
def banque(tmp_path):
    return module_banque.Banque(tmp_path / "pnj")


def lmstudio_repond(monkeypatch, reponse):
    """LM Studio simulé : `reponse` pour la requête de dialogue, une liste vide pour celle des modèles."""
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda req, timeout=None: (
        FausseReponseLMStudio(corps={"data": []}) if isinstance(req, str) else reponse))


def copie(config=CONFIG):
    return json.loads(json.dumps(config))


# --- 1.1 / 1.2 : configuration incomplète ------------------------------------------
class TestDefauts:
    def test_configuration_vide(self):
        moteurs = Moteurs({})
        assert moteurs.choix == {"creation": "local", "dialogue": "local"}  # décision D3
        assert moteurs.local_cfg["dialogue"]["max_tokens"] == 200
        assert moteurs.description()["dialogue"] == "local : qwen3:8b"
        assert moteurs.contexte_max() == 8192

    def test_le_catalogue_et_le_code_ont_les_memes_defauts(self):
        for cle, reglage in reglages.REGLAGES.items():
            section, *chemin = cle.split(".")
            if section not in DEFAUTS:
                continue
            valeur = DEFAUTS[section]
            for partie in chemin:
                valeur = valeur.get(partie, reglage["defaut"]) if isinstance(valeur, dict) else valeur
            assert valeur == reglage["defaut"], cle

    def test_defauts_de_config_toml_example(self, tmp_path):
        import tomllib
        from pathlib import Path
        exemple = tomllib.loads((Path(__file__).parent.parent / "config.toml.example").read_text(encoding="utf-8"))
        for section in ("moteurs", "local", "lmstudio"):
            for cle, valeur in exemple[section].items():
                if not isinstance(valeur, dict):
                    assert DEFAUTS[section][cle] == valeur, f"{section}.{cle}"
        assert exemple["local"]["generation"] == DEFAUTS["local"]["generation"]
        assert exemple["claude"]["dialogue"] == DEFAUTS["claude"]["dialogue"]

    def test_section_incomplete_completee(self):
        moteurs = Moteurs({"moteurs": {"creation": "lmstudio", "dialogue": "lmstudio"}, "lmstudio": {"modele": "x"}})
        assert moteurs.lmstudio_cfg["dialogue"]["max_tokens"] == 200
        assert moteurs.lmstudio_cfg["modele"] == "x" and moteurs.lmstudio_cfg["url"] == "http://localhost:1234"

    def test_section_qui_n_est_pas_une_table(self):
        assert Moteurs({"local": "oups"}).local_cfg["url"] == "http://localhost:11434"

    def test_lmstudio_sans_max_tokens_de_dialogue(self, monkeypatch):
        reponse = FausseReponseLMStudio(["Bonjour."])
        lmstudio_repond(monkeypatch, reponse)
        moteurs = Moteurs({"moteurs": {"creation": "lmstudio", "dialogue": "lmstudio"},
                           "lmstudio": {"modele": "qwen"}})
        assert "".join(moteurs.replique("s", MESSAGE)) == "Bonjour."

    def test_ollama_sans_max_tokens_de_dialogue(self, monkeypatch):
        monkeypatch.setattr(module.urllib.request, "urlopen",
                            lambda req, timeout=None: FausseReponseOllama(["Bonjour."]))
        assert "".join(Moteurs({}).replique("s", MESSAGE)) == "Bonjour."

    def test_reflexion_absente_envoie_false(self, monkeypatch):
        corps = []
        monkeypatch.setattr(module.urllib.request, "urlopen",
                            lambda req, timeout=None: corps.append(json.loads(req.data)) or FausseReponseOllama(["a"]))
        list(Moteurs({}).replique("s", MESSAGE))
        assert corps[-1]["think"] is False


# --- 1.3, 1.4, 1.6 : Claude ----------------------------------------------------------
class TestClaude:
    def moteurs(self):
        config = copie()
        config["moteurs"] = {"creation": "claude", "dialogue": "claude"}
        return Moteurs(config)

    def test_cle_absente(self, monkeypatch):
        moteurs = self.moteurs()

        def create(**kwargs):
            raise TypeError("Could not resolve authentication method")
        monkeypatch.setattr(moteurs.client.messages, "create", create)
        with pytest.raises(MoteurIndisponible, match="Clé API Claude absente"):
            moteurs.replique("s", MESSAGE)
        with pytest.raises(MoteurIndisponible, match="Clé API Claude absente"):
            moteurs.fiche("s", "demande", {})

    def test_erreur_du_sdk_generique(self, monkeypatch):
        moteurs = self.moteurs()

        def create(**kwargs):
            raise anthropic.APIError("boum", request=None, body=None)
        monkeypatch.setattr(moteurs.client.messages, "create", create)
        with pytest.raises(MoteurIndisponible):
            moteurs.fiche("s", "demande", {})

    def test_coupure_pendant_le_flux(self, monkeypatch):
        moteurs = self.moteurs()

        class Flux:
            def __iter__(self):
                raise module.httpx.ReadError("coupé")

            def close(self):
                pass
        monkeypatch.setattr(moteurs.client.messages, "create", lambda **kwargs: Flux())
        with pytest.raises(MoteurIndisponible, match="interrompue"):
            list(moteurs.replique("s", MESSAGE))

    def test_delai_borne(self):
        moteurs = self.moteurs()
        assert moteurs.client.timeout.read == 60 and moteurs.client.timeout.connect == 5
        assert moteurs.client.max_retries == 1
        config = copie()
        config["claude"]["delai_max"] = 15
        assert Moteurs(config).client.timeout.read == 15
        config["claude"]["delai_max"] = "abc"
        assert Moteurs(config).client.timeout.read == 60


# --- 1.5, 1.13 : Ollama et LM Studio en cours de route -----------------------------
class TestFluxLocaux:
    def ollama(self, monkeypatch, reponse):
        monkeypatch.setattr(module.urllib.request, "urlopen", lambda req, timeout=None: reponse)
        return Moteurs(copie())

    def test_erreur_dans_le_flux_ollama(self, monkeypatch):
        reponse = FausseReponseOllama([], termine=False)
        reponse.lignes = [json.dumps({"error": "out of memory"}).encode() + b"\n"]
        with pytest.raises(MoteurIndisponible, match="out of memory"):
            list(self.ollama(monkeypatch, reponse).replique("s", MESSAGE))

    def test_flux_ollama_coupe_net(self, monkeypatch):
        reponse = FausseReponseOllama(["Bonjour, "], termine=False)
        with pytest.raises(MoteurIndisponible, match="interrompu"):
            list(self.ollama(monkeypatch, reponse).replique("s", MESSAGE))

    def test_delai_depasse_en_lisant_la_fiche(self, monkeypatch):
        class Lente:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                pass

            def read(self):
                raise TimeoutError("lent")
        moteurs = self.ollama(monkeypatch, Lente())
        with pytest.raises(MoteurIndisponible, match="trop de temps"):
            moteurs.fiche("s", "demande", {})

    def test_delai_depasse_a_la_connexion_n_est_pas_injoignable(self, monkeypatch):
        def urlopen(req, timeout=None):
            raise module.urllib.error.URLError(TimeoutError("délai"))
        monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
        with pytest.raises(MoteurIndisponible, match="trop de temps"):
            Moteurs(copie()).replique("s", MESSAGE)

    def test_erreur_du_flux_lmstudio(self, monkeypatch):
        reponse = FausseReponseLMStudio()
        reponse.lignes = [b'data: {"error": {"message": "modele decharge"}}\n\n']
        lmstudio_repond(monkeypatch, reponse)
        moteurs = Moteurs({"moteurs": {"dialogue": "lmstudio"}, "lmstudio": {"modele": "q"}})
        with pytest.raises(MoteurIndisponible, match="modele decharge"):
            list(moteurs.replique("s", MESSAGE))

    def test_reponse_lmstudio_inattendue(self, monkeypatch):
        reponse = FausseReponseLMStudio(corps={"choices": []})
        reponse.read = lambda: b'{"choices": []}'
        lmstudio_repond(monkeypatch, reponse)
        moteurs = Moteurs({"moteurs": {"creation": "lmstudio"}, "lmstudio": {"modele": "q"}})
        with pytest.raises(MoteurIndisponible, match="inattendue"):
            moteurs.fiche("s", "demande", {})


# --- 1.7 : entrées client ------------------------------------------------------------
ROUTES = [
    ("post", "/api/npc/talk"), ("post", "/api/bank"), ("put", "/api/scenario"), ("post", "/api/npc/generate"),
    ("post", "/api/tts"), ("post", "/api/voice"), ("put", "/api/voice-engine"), ("put", "/api/reglages"),
    ("post", "/api/reglages/verifier"), ("post", "/api/exemples/pre-novice"),
]


class TestEntreesInvalides:
    @pytest.mark.parametrize(("methode", "url"), ROUTES)
    @pytest.mark.parametrize("corps", [[1, 2], "texte", 12])
    def test_corps_qui_n_est_pas_un_objet(self, client, methode, url, corps):
        reponse = getattr(client, methode)(url, json=corps)
        assert reponse.status_code == 400
        assert "error" in reponse.get_json()

    def test_lieux_attend_une_liste(self, client):
        assert client.put("/api/lieux", json={"a": 1}).status_code == 400

    def test_bank_put(self, client):
        assert client.put("/api/bank/inconnu", json=[1]).status_code == 400

    @pytest.mark.parametrize("corps", [
        {"npc": "Ysolde", "history": [{"content": "x"}]},
        {"npc": [], "history": [{"content": "x"}]},
        {"npc": {"nom": "Ysolde"}, "history": "salut"},
        {"npc": {"nom": ["a"]}, "history": [{"content": "x"}]},
        {"npc": None},
    ])
    def test_talk_entrees_etranges(self, client, corps):
        assert client.post("/api/npc/talk", json=corps).status_code == 400

    def test_talk_champs_de_la_fiche_mal_types(self, client, moteurs):
        npc = {"nom": 12, "metier": None, "connaissances": None, "apparence": ["a"], "secret": {"x": 1}}
        reponse = client.post("/api/npc/talk", json={"npc": npc, "presents": "Brom", "history": [{"content": "x"}]})
        assert reponse.status_code == 200 and lignes(reponse)
        assert "Tu es 12" in moteurs.appels[-1][0]

    def test_talk_connaissances_melangees(self, client, moteurs):
        npc = {**YSOLDE, "connaissances": ["Le pont", 3, None, ["x"]]}
        assert client.post("/api/npc/talk", json={"npc": npc, "history": [{"content": "x"}]}).status_code == 200
        assert "- Le pont\n- 3" in moteurs.appels[-1][0]

    def test_generate_role_null(self, client, moteurs):
        reponse = client.post("/api/npc/generate", json={"role": None, "nom": 5, "genre": [], "consignes": {}})
        assert reponse.status_code == 200

    def test_tts_texte_numerique(self, client):
        assert client.post("/api/tts", json={"text": 12}).status_code == 200
        assert client.post("/api/tts", json={"text": None}).status_code == 400

    def test_tts_voix_etrange(self, client):
        assert client.post("/api/tts", json={"text": "a", "voice": "alice"}).status_code == 200
        reponse = client.post("/api/tts", json={"text": "a", "narrateur": True, "voice": {"name": ["x"]},
                                                "eviter": "bob"})
        assert reponse.status_code == 200

    def test_bank_champs_non_textuels(self, client):
        assert client.post("/api/bank", json={"nom": 12, "salutation": ["a"]}).status_code == 400

    def test_voice_eviter_mal_forme(self, client):
        assert client.post("/api/voice", json={"nom": "X", "genre": "feminin", "eviter": 5}).status_code == 200

    def test_corps_vide_ou_illisible_reste_accepte(self, client):
        assert client.post("/api/bank", data="pas du json").status_code == 400  # fiche incomplète, pas 500
        assert client.put("/api/scenario", data="").status_code == 200


class TestVoixInvalides:
    @pytest.mark.parametrize("valeur", [0, "abc", None, math.nan, 1e9, -3, [1]])
    def test_echelle_de_debit_toujours_valide(self, valeur):
        assert 0.5 <= voix.echelle_debit({"length_scale": valeur}) <= 2

    def test_echelle_normale_conservee(self):
        assert voix.echelle_debit({"length_scale": 1.2}) == 1.2 and voix.echelle_debit({}) == 1.0

    def test_cle_hachable(self):
        hash(voix.cle({"name": ["a"], "speaker": {"x": 1}}))


# --- 1.8 : fiche abîmée ----------------------------------------------------------------
class TestFicheAbimee:
    def test_lire_fiche_illisible(self, banque):
        banque.dossier.mkdir(parents=True, exist_ok=True)
        (banque.dossier / "abimee.json").write_text("{pas du json", encoding="utf-8")
        (banque.dossier / "liste.json").write_text("[1]", encoding="utf-8")
        assert banque.lire("abimee") is None and banque.lire("liste") is None

    def test_la_liste_ignore_les_fiches_qui_ne_sont_pas_des_objets(self, banque):
        banque.ajouter({"nom": "Brom", "metier": "forgeron", "salutation": "Salut."})
        (banque.dossier / "liste.json").write_text("[1]", encoding="utf-8")
        (banque.dossier / "abimee.json").write_text("{", encoding="utf-8")
        assert [p["nom"] for p in banque.liste()] == ["Brom"]

    def test_route_fiche_abimee(self, client, ctx):
        ctx.banque.dossier.mkdir(parents=True, exist_ok=True)
        (ctx.banque.dossier / "abimee.json").write_text("{", encoding="utf-8")
        assert client.get("/api/bank/abimee").status_code == 404
        assert client.get("/api/bank").status_code == 200


# --- 1.9 : réglages ----------------------------------------------------------------------
class TestReglagesNonFinis:
    @pytest.mark.parametrize("valeur", [math.nan, math.inf, -math.inf, 1e999, "nan", "inf", "", [1], {"a": 1}])
    def test_nombres_refuses(self, valeur):
        with pytest.raises(ValueError):
            reglages.valider({"local.temperature": valeur})
        with pytest.raises(ValueError):
            reglages.valider({"local.contexte": valeur})

    def test_json_avec_nan_et_infini(self, client):
        brut = '{"changements": {"local.temperature": NaN}}'
        assert client.put("/api/reglages", data=brut, content_type="application/json").status_code == 400
        brut = '{"changements": {"local.temperature": 1e999}}'
        assert client.put("/api/reglages", data=brut, content_type="application/json").status_code == 400

    @pytest.mark.parametrize("cle", ["local.modele", "local.url", "claude.modele"])
    def test_texte_doit_etre_une_chaine(self, cle):
        with pytest.raises(ValueError):
            reglages.valider({cle: ["a"]})

    def test_valeurs_normales_toujours_acceptees(self):
        assert reglages.valider({"local.temperature": 0.5, "local.modele": " qwen3:8b ",
                                 "dialogue.pnj_max": 4}) == {"local.temperature": 0.5, "local.modele": "qwen3:8b",
                                                             "dialogue.pnj_max": 4}


# --- 1.10 : historique ---------------------------------------------------------------------
class TestHistorique:
    @pytest.mark.parametrize(("valeur", "attendu"), [(0, 2), (-5, 2), (1, 2), (12, 12), ("abc", 12), (None, 12),
                                                     (4.7, 4)])
    def test_borne(self, cfg, ctx, valeur, attendu):
        cfg.reglages["dialogue"]["historique"] = valeur
        ctx.parametres()
        assert ctx.historique == attendu

    def test_la_limite_garde_les_derniers_messages(self, client, cfg, ctx, moteurs):
        cfg.reglages["dialogue"]["historique"] = 0
        ctx.parametres()
        history = [{"speaker": None, "content": f"m{i}"} for i in range(6)]
        client.post("/api/npc/talk", json={"npc": YSOLDE, "history": history})
        envoye = "\n".join(m["content"] for m in moteurs.appels[-1][1])
        assert "m5" in envoye and "m4" in envoye and "m0" not in envoye


# --- 1.11 : PNJ en scène (décision D2) -------------------------------------------------------
class TestPnjEnScene:
    def autres(self, n):
        return [{"nom": f"Pnj{i}", "metier": "passant"} for i in range(n)]

    def test_par_defaut_trois_en_tout(self, client, ctx, moteurs):
        assert ctx.pnj_max == 3
        client.post("/api/npc/talk", json={"npc": YSOLDE, "presents": self.autres(5),
                                           "history": [{"content": "x"}]})
        system = moteurs.appels[-1][0]
        assert "Pnj1" in system and "Pnj2" not in system  # Ysolde + 2 autres

    def test_reglable(self, client, cfg, ctx, moteurs):
        cfg.reglages["dialogue"]["pnj_max"] = 5
        ctx.parametres()
        client.post("/api/npc/talk", json={"npc": YSOLDE, "presents": self.autres(8),
                                           "history": [{"content": "x"}]})
        system = moteurs.appels[-1][0]
        assert "Pnj3" in system and "Pnj4" not in system

    @pytest.mark.parametrize(("valeur", "attendu"), [(0, 1), (99, 6), ("x", 3), (4, 4)])
    def test_borne(self, cfg, ctx, valeur, attendu):
        cfg.reglages["dialogue"]["pnj_max"] = valeur
        ctx.parametres()
        assert ctx.pnj_max == attendu

    def test_fourni_a_l_interface(self, client, cfg, ctx):
        assert client.get("/api/config").get_json()["pnj_max"] == 3
        cfg.reglages["dialogue"]["pnj_max"] = 4
        ctx.parametres()
        assert client.get("/api/config").get_json()["pnj_max"] == 4

    def test_dans_le_catalogue_et_applique_a_chaud(self, client):
        assert reglages.REGLAGES["dialogue.pnj_max"]["defaut"] == 3
        assert "petits modèles locaux" in reglages.REGLAGES["dialogue.pnj_max"]["aide"]
        assert client.put("/api/reglages", json={"changements": {"dialogue.pnj_max": 5}}).status_code == 200
        assert client.get("/api/config").get_json()["pnj_max"] == 5

    def test_brom_present(self, client, moteurs):
        client.post("/api/npc/talk", json={"npc": YSOLDE, "presents": [BROM], "history": [{"content": "x"}]})
        assert "Brom, forgeron" in moteurs.appels[-1][0]


# --- 1.12 : nettoyage du texte --------------------------------------------------------------------
class TestNettoyerEmojis:
    def test_exemple_de_l_audit(self):
        assert texte.nettoyer("Il rit * et part ⭐ ⏳ 👍🏽 ok") == "Il rit et part ok"

    def test_asterisque_isole_et_paires(self):
        assert texte.nettoyer("*Il rit.* Ah * oui") == "Ah oui"

    def test_selecteurs_et_jonctions(self):
        assert texte.nettoyer("coeur❤️ famille 👨‍👩‍👧 fin") == "coeur famille fin"

    def test_texte_normal_intact(self):
        assert texte.nettoyer("Ça coûte 3 pièces d'or, voyageur !") == "Ça coûte 3 pièces d'or, voyageur !"


# --- 1.14 : portrait local sans mémoire -----------------------------------------------------------
def test_portrait_local_erreur_cuda(monkeypatch):
    import sys
    local = Local({})
    monkeypatch.setattr(local, "disponible", lambda: True)

    class Pipe:
        def __call__(self, **kwargs):
            raise RuntimeError("CUDA out of memory")
    local._pipe, local._appareil = Pipe(), "cpu"
    faux_torch = SimpleNamespace(Generator=lambda device: SimpleNamespace(manual_seed=lambda g: g))
    monkeypatch.setitem(sys.modules, "torch", faux_torch)
    with pytest.raises(PortraitIndisponible, match="mémoire"):
        local.generer("prompt", 1)


# --- 1.15 : identifiants --------------------------------------------------------------------------
def test_identifiant_avec_saut_de_ligne_refuse(banque):
    assert banque.chemin("abc\n") is None
    assert not module_banque.NPC_ID.fullmatch("abc\n")
    assert module_banque.THEME.fullmatch("donjon") and not module_banque.THEME.fullmatch("donjon\n")
    assert banque.lire("abc\n") is None and not banque.existe("abc\n")
