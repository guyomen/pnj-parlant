"""Réglages du serveur modifiables depuis la page Options : catalogue, validation, écriture de config.toml (avec ses
commentaires), application à chaud, mot de passe du MJ."""
import tomllib

import pytest

from conftest import FausseReconnaissance
from pnj_parlant import reglages
from pnj_parlant.config import Config
from pnj_parlant.portraits import Aucun, EnLigne
from pnj_parlant.serveur import create_app

CONFIG = """# Mon univers
[moteurs]
creation = "claude"   # avec le réseau
dialogue = "local"

[claude]
cle_api = "sk-ant-secret"
modele = "claude-haiku-5-5"

[dialogue]
historique = 12       # messages gardés
"""
DISTANT = {"REMOTE_ADDR": "192.168.1.30"}  # le téléphone d'un joueur


@pytest.fixture
def fichier(tmp_path):
    chemin = tmp_path / "config.toml"
    chemin.write_text(CONFIG, encoding="utf-8")
    return chemin


@pytest.fixture
def appli(fichier, moteurs, tts):
    """Le vrai moteur de portraits (pour vérifier qu'il change à chaud), les autres remplacés par des faux."""
    with open(fichier, "rb") as f:
        cfg = Config(tomllib.load(f), fichier.parent, fichier)
    return create_app(cfg, moteurs=moteurs, tts=tts, reconnaissance=FausseReconnaissance())


@pytest.fixture
def web(appli):
    return appli.test_client()


def valeurs(reponse):
    return {r["cle"]: r for g in reponse.get_json()["groupes"] for r in g["reglages"]}


# --- Catalogue et validation -----------------------------------------------------------------
def test_catalogue_coherent():
    cles = [r["cle"] for g in reglages.CATALOGUE for r in g["reglages"]]
    assert len(cles) == len(set(cles))
    for r in reglages.REGLAGES.values():
        assert r["type"] in ("choix", "texte", "url", "entier", "nombre", "booleen", "secret"), r["cle"]
        if r["type"] == "choix":
            assert r["defaut"] in [c[0] for c in r["choix"]], r["cle"]
        if r["type"] in ("entier", "nombre"):
            assert r["min"] <= r["defaut"] <= r["max"], r["cle"]
    assert {"moteurs.dialogue", "lmstudio.modele", "serveur.mot_de_passe_mj"} <= set(cles)


def test_lire_et_poser():
    d = {"claude": {"dialogue": {"effort": "high"}}}
    assert reglages.lire(d, "claude.dialogue.effort") == "high"
    assert reglages.lire(d, "claude.generation.effort") == "low"  # défaut du catalogue
    reglages.poser(d, "portraits.local.etapes", 3)
    assert d["portraits"] == {"local": {"etapes": 3}}


def test_valider():
    assert reglages.valider({"dialogue.historique": "20", "local.temperature": "0.5", "local.reflexion": True,
                             "moteurs.dialogue": "lmstudio", "local.url": " http://pc:11434 ",
                             "claude.cle_api": "", "serveur.mot_de_passe_mj": None}) == {
        "dialogue.historique": 20, "local.temperature": 0.5, "local.reflexion": True, "moteurs.dialogue": "lmstudio",
        "local.url": "http://pc:11434", "serveur.mot_de_passe_mj": ""}  # clé vide : inchangée ; None : effacée


@pytest.mark.parametrize("changements, message", [
    ({}, "Aucun"), ({"serveur.hote": "x"}, "inconnu"), ({"moteurs.dialogue": "gpt"}, "valeur inconnue"),
    ({"dialogue.historique": 1}, "entre 2 et 60"), ({"dialogue.historique": 2.5}, "entier"),
    ({"dialogue.historique": "beaucoup"}, "nombre"), ({"dialogue.historique": True}, "nombre"),
    ({"local.reflexion": "oui"}, "oui ou non"), ({"local.url": "localhost:11434"}, "http"),
])
def test_valider_refuse(changements, message):
    with pytest.raises(ValueError, match=message):
        reglages.valider(changements)


def test_ecrire_garde_les_commentaires(fichier):
    reglages.ecrire(fichier, {"dialogue.historique": 20, "lmstudio.modele": "qwen/qwen3-8b",
                              "claude.generation.effort": "medium"})
    texte = fichier.read_text(encoding="utf-8")
    assert "# Mon univers" in texte and "creation = \"claude\"   # avec le réseau" in texte
    assert "historique = 20       # messages gardés" in texte
    lu = tomllib.loads(texte)
    assert lu["lmstudio"]["modele"] == "qwen/qwen3-8b" and lu["claude"]["generation"]["effort"] == "medium"


def test_autorise():
    assert reglages.autorise({}, None, local=True) and not reglages.autorise({}, None, local=False)
    protege = {"serveur": {"mot_de_passe_mj": "dragon"}}
    assert reglages.autorise(protege, "dragon", local=False)
    assert not reglages.autorise(protege, "Dragon", local=True)  # mot de passe exigé, même depuis le PC


# --- Routes ------------------------------------------------------------------------------------
def test_lecture_sans_secret(web):
    r = web.get("/api/reglages")
    v = valeurs(r)
    assert v["claude.cle_api"]["valeur"] == "" and v["claude.cle_api"]["defini"] is True
    assert v["moteurs.dialogue"]["valeur"] == "local" and v["voix.moteur"]["valeur"] == "piper"  # défaut
    assert "sk-ant-secret" not in r.get_data(as_text=True)
    d = r.get_json()
    assert d["protege"] is False and d["local"] is True and d["fichier"] == "config.toml"


def test_modification_a_chaud_et_dans_le_fichier(web, appli, fichier):
    ctx = appli.extensions["pnj"]
    assert isinstance(ctx.portraits, Aucun)
    r = web.put("/api/reglages", json={"changements": {"dialogue.historique": 20, "portraits.moteur": "en_ligne",
                                                       "serveur.port": 5050, "claude.cle_api": ""}})
    assert r.status_code == 200 and r.get_json()["redemarrage"] == ["Port"]
    assert ctx.historique == 20 and isinstance(ctx.portraits, EnLigne)  # pris en compte sans redémarrer
    assert web.get("/api/config").get_json()["portraits"] == "en_ligne"
    lu = tomllib.loads(fichier.read_text(encoding="utf-8"))
    assert lu["dialogue"]["historique"] == 20 and lu["serveur"]["port"] == 5050
    assert lu["claude"]["cle_api"] == "sk-ant-secret"  # clé laissée vide : inchangée
    assert web.put("/api/reglages", json={"changements": {"serveur.port": 5050}}).get_json()["redemarrage"] == []


def test_refus_ne_change_rien(web, fichier):
    avant = fichier.read_text(encoding="utf-8")
    assert web.put("/api/reglages", json={"changements": {"dialogue.historique": 0}}).status_code == 400
    assert web.put("/api/reglages", json={"changements": {"dialogue.historique": 20}},
                   environ_base=DISTANT).status_code == 403  # sans mot de passe : seulement depuis le PC
    assert fichier.read_text(encoding="utf-8") == avant


def test_mot_de_passe_du_mj(web, monkeypatch):
    monkeypatch.setattr("pnj_parlant.serveur.time.sleep", lambda s: None)
    assert web.put("/api/reglages", json={"changements": {"serveur.mot_de_passe_mj": "dragon"}}).status_code == 200
    d = web.get("/api/reglages", environ_base=DISTANT).get_json()
    assert d["protege"] is True and d["local"] is False
    modif = {"changements": {"dialogue.historique": 30}}
    assert web.put("/api/reglages", json=modif).status_code == 403  # même depuis le PC
    assert web.put("/api/reglages", json=modif, headers={"X-Mot-De-Passe-MJ": "faux"}, environ_base=DISTANT).status_code == 403
    assert web.put("/api/reglages", json=modif, headers={"X-Mot-De-Passe-MJ": "dragon"}, environ_base=DISTANT).status_code == 200
    assert web.post("/api/reglages/verifier", json={"mot_de_passe": "dragon"}).get_json() == {"ok": True}
    assert web.post("/api/reglages/verifier", json={"mot_de_passe": "x"}).status_code == 403
    # le mot de passe s'efface avec le mot de passe actuel ; ensuite, depuis le PC seulement
    effacer = {"changements": {"serveur.mot_de_passe_mj": None}}
    assert web.put("/api/reglages", json=effacer, headers={"X-Mot-De-Passe-MJ": "dragon"}).status_code == 200
    assert web.get("/api/reglages").get_json()["protege"] is False


def test_sans_fichier_en_memoire(client, ctx):
    assert client.put("/api/reglages", json={"changements": {"dialogue.intervention": 0.5}}).status_code == 200
    assert ctx.intervention == 0.5 and client.get("/api/reglages").get_json()["fichier"] is None
