"""Contrôle d'accès de l'univers (décision D1) et limites de taille des requêtes.

Depuis le PC du serveur, rien ne change. Ailleurs, toute écriture demande le mot de passe du MJ (en-tête
X-Mot-De-Passe-MJ) et les secrets des PNJ et les notes du MJ sont retirés des réponses. Les essais de mot de passe
sont freinés par adresse."""
import io
import json
from urllib.parse import quote

import pytest
from conftest import FICHE, PNG, FausseReconnaissance

from pnj_parlant import reglages, serveur
from pnj_parlant.serveur import create_app, masquer, mot_de_passe_recu

DISTANT = {"REMOTE_ADDR": "192.168.1.30"}   # le téléphone d'un joueur
LOCAL = {"REMOTE_ADDR": "127.0.0.1"}
BON = {"X-Mot-De-Passe-MJ": "dragon"}
FAUX = {"X-Mot-De-Passe-MJ": "faux"}


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    monkeypatch.setattr("pnj_parlant.serveur.time.sleep", lambda s: None)  # pause d'un mauvais mot de passe


@pytest.fixture
def univers(ctx):
    """Un scénario, un lieu et un PNJ (avec portrait), secret et notes du MJ compris ; renvoie l'identifiant du PNJ."""
    ctx.banque.enregistrer_scenario({"monde": "Le Val", "notes_mj": "Le baron est un loup."})
    ctx.banque.enregistrer_lieux([{"id": "forge", "nom": "Forge", "description": "Chaude.", "notes_mj": "Trappe."}])
    npc_id = ctx.banque.ajouter({**FICHE, "lieu": "forge"})
    ctx.banque.enregistrer_portrait(npc_id, PNG, "png")
    return npc_id


@pytest.fixture
def mdp(ctx):
    """Mot de passe du MJ défini."""
    ctx.cfg.reglages["serveur"] = {"mot_de_passe_mj": "dragon"}


# (méthode, adresse, arguments de la requête, codes attendus une fois autorisée) ; « {id} » = PNJ de l'univers
ECRITURES = [
    ("put", "/api/scenario", lambda: {"json": {"monde": "Autre"}}, 200),
    ("put", "/api/styles", lambda: {"json": {"themes": {}, "portraits": {}}}, 200),
    ("put", "/api/lieux", lambda: {"json": [{"nom": "Moulin"}]}, 200),
    ("get", "/api/scenario/export", lambda: {}, 200),
    ("post", "/api/scenario/import", lambda: {"data": {"fichiers": (io.BytesIO(b'{"monde": "Nouveau"}'),
                                                                    "_scenario.json")},
                                              "content_type": "multipart/form-data"}, 200),
    ("post", "/api/exemples/pre-novice", lambda: {"json": {"remplacer": False}}, 200),
    ("delete", "/api/univers", lambda: {}, 200),
    ("post", "/api/bank", lambda: {"json": dict(FICHE)}, 200),
    ("put", "/api/bank/{id}", lambda: {"json": dict(FICHE)}, 200),
    ("delete", "/api/bank/{id}", lambda: {}, 200),
    ("post", "/api/bank/{id}/portrait", lambda: {"json": {}}, 200),
    ("delete", "/api/bank/{id}/portrait", lambda: {}, 200),
    ("put", "/api/voice-engine", lambda: {"json": {"moteur": "faux"}}, 200),
]
IDS = [f"{m} {a}" for m, a, _, _ in ECRITURES]


def envoyer(client, ctx, npc_id, methode, adresse, args, **options):
    return getattr(client, methode)(adresse.replace("{id}", npc_id), **args(), **options)


class TestEcritures:
    @pytest.mark.parametrize("methode,adresse,args,code", ECRITURES, ids=IDS)
    def test_depuis_le_pc_rien_ne_change(self, client, ctx, univers, mdp, methode, adresse, args, code):
        # même avec un mot de passe défini, et sans l'envoyer
        assert envoyer(client, ctx, univers, methode, adresse, args, environ_base=LOCAL).status_code == code

    @pytest.mark.parametrize("methode,adresse,args,code", ECRITURES, ids=IDS)
    def test_distant_sans_mot_de_passe_defini(self, client, ctx, univers, methode, adresse, args, code):
        avant = ctx.banque.exporter_zip()
        r = envoyer(client, ctx, univers, methode, adresse, args, environ_base=DISTANT, headers=BON)
        assert r.status_code == 403
        assert "PC du serveur" in r.get_json()["error"] and "mot_de_passe" not in r.get_json()
        assert ctx.banque.exporter_zip() == avant and ctx.tts.nom == "faux"

    @pytest.mark.parametrize("methode,adresse,args,code", ECRITURES, ids=IDS)
    def test_distant_avec_mot_de_passe(self, client, ctx, univers, mdp, methode, adresse, args, code):
        avant = ctx.banque.exporter_zip()
        sans = envoyer(client, ctx, univers, methode, adresse, args, environ_base=DISTANT)
        assert sans.status_code == 403 and sans.get_json()["mot_de_passe"] is True  # la page peut le demander
        faux = envoyer(client, ctx, univers, methode, adresse, args, environ_base=DISTANT, headers=FAUX)
        assert faux.status_code == 403 and faux.get_json()["error"] == "Mot de passe du MJ incorrect."
        assert ctx.banque.exporter_zip() == avant
        bon = envoyer(client, ctx, univers, methode, adresse, args, environ_base=DISTANT, headers=BON)
        assert bon.status_code == code

    def test_mot_de_passe_avec_accents(self, client, ctx, univers):
        ctx.cfg.reglages["serveur"] = {"mot_de_passe_mj": "dragée à l'œil"}
        en_tete = {"X-Mot-De-Passe-MJ": quote("dragée à l'œil", safe="")}  # comme encodeURIComponent
        assert client.delete(f"/api/bank/{univers}", environ_base=DISTANT, headers=en_tete).status_code == 200
        assert mot_de_passe_recu("abc") == "abc" and mot_de_passe_recu(None) is None

    def test_lectures_et_partie_restent_ouvertes(self, client, univers, mdp, moteurs):
        for adresse in ("/api/scenario", "/api/lieux", "/api/bank", f"/api/bank/{univers}", "/api/styles",
                        "/api/exemples", "/api/config", f"/api/bank/{univers}/portrait"):
            assert client.get(adresse, environ_base=DISTANT).status_code in (200, 404), adresse
        assert client.post("/api/npc/generate", json={"role": "forgeron"}, environ_base=DISTANT).status_code == 200
        assert client.post("/api/voice", json=dict(FICHE), environ_base=DISTANT).status_code == 200
        r = client.post("/api/npc/talk", json={"npc": dict(FICHE), "history": [{"speaker": None, "content": "Salut"}]},
                        environ_base=DISTANT)
        assert r.status_code == 200

    def test_autre_page_web_refusee(self, client, univers):
        """Une page d'un autre site ouverte sur le PC ne peut pas écrire (pas de pré-vérification CORS pour un
        import multipart ou un POST sans corps)."""
        r = client.post("/api/exemples/pre-novice", headers={"Origin": "http://piege.example"}, environ_base=LOCAL)
        assert r.status_code == 403 and "autre page" in r.get_json()["error"]
        assert client.delete("/api/univers", headers={"Origin": "null"}, environ_base=LOCAL).status_code == 403
        assert client.get("/api/scenario", headers={"Origin": "http://piege.example"}).status_code == 200
        meme = {"Origin": "http://localhost"}  # Host du client de test : localhost
        assert client.delete(f"/api/bank/{univers}", headers=meme, environ_base=LOCAL).status_code == 200


class TestMasquage:
    def test_masquer(self):
        assert masquer({"a": 1, "secret": 2, "notes_mj": 3}, "secret", "notes_mj") == {"a": 1}

    @pytest.mark.parametrize("environ,en_tete,voit", [(LOCAL, {}, True), (DISTANT, {}, False),
                                                      (DISTANT, FAUX, False), (DISTANT, BON, True)])
    def test_secrets_et_notes(self, client, univers, mdp, environ, en_tete, voit):
        options = {"environ_base": environ, "headers": en_tete}
        scenario = client.get("/api/scenario", **options).get_json()
        lieux = client.get("/api/lieux", **options).get_json()
        npc = client.get(f"/api/bank/{univers}", **options).get_json()
        assert scenario["monde"] == "Le Val" and lieux[0]["description"] == "Chaude." and npc["nom"] == FICHE["nom"]
        assert ("notes_mj" in scenario) is voit and ("notes_mj" in lieux[0]) is voit and ("secret" in npc) is voit
        if voit:
            assert npc["secret"] == FICHE["secret"] and scenario["notes_mj"] == "Le baron est un loup."

    def test_sans_mot_de_passe_defini_tout_est_masque_ailleurs(self, client, univers):
        assert "secret" not in client.get(f"/api/bank/{univers}", environ_base=DISTANT, headers=BON).get_json()
        assert "secret" in client.get(f"/api/bank/{univers}").get_json()  # client de test : 127.0.0.1

    def test_acces(self, client, mdp):
        assert client.get("/api/acces").get_json() == {"mj": True, "protege": True, "local": True}
        assert client.get("/api/acces", environ_base=DISTANT).get_json()["mj"] is False
        assert client.get("/api/acces", environ_base=DISTANT, headers=BON).get_json() == {
            "mj": True, "protege": True, "local": False}


class TestChampsMasquesGardes:
    """Une fiche, un scénario ou des lieux lus sans mot de passe, puis renvoyés avec : le champ absent ne
    les efface pas."""

    def test_fiche_sans_secret(self, client, ctx, univers):
        fiche = client.get(f"/api/bank/{univers}", environ_base=DISTANT).get_json()
        fiche["humeur"] = "grognon"
        assert client.put(f"/api/bank/{univers}", json=fiche).status_code == 200
        assert ctx.banque.lire(univers)["secret"] == FICHE["secret"]
        assert ctx.banque.lire(univers)["humeur"] == "grognon"
        assert client.put(f"/api/bank/{univers}", json={**fiche, "secret": ""}).status_code == 200
        assert ctx.banque.lire(univers)["secret"] == ""  # vidé exprès : c'est voulu

    def test_portrait_avec_une_fiche_sans_secret(self, client, ctx, univers):
        assert client.post(f"/api/bank/{univers}/portrait", json={"apparence": "Barbu."}).status_code == 200
        assert ctx.banque.lire(univers)["secret"] == FICHE["secret"]

    def test_scenario_sans_notes(self, client, ctx, univers):
        r = client.put("/api/scenario", json={"monde": "Le Val gelé", "theme": ""}).get_json()
        assert r["notes_mj"] == "Le baron est un loup." and r["monde"] == "Le Val gelé"
        client.put("/api/scenario", json={"monde": "x", "notes_mj": ""})
        assert ctx.banque.scenario()["notes_mj"] == ""

    def test_lieux_sans_notes(self, client, ctx, univers):
        lieux = client.get("/api/lieux", environ_base=DISTANT).get_json()
        lieux[0]["nom"] = "Grande forge"
        lieux.append({"nom": "Moulin", "description": "Bruyant."})
        lieux.append({"id": ["piège"], "nom": "Tour"})
        r = client.put("/api/lieux", json=lieux).get_json()
        assert [(lieu["nom"], lieu["notes_mj"]) for lieu in r] == [("Grande forge", "Trappe."), ("Moulin", ""),
                                                                   ("Tour", "")]


class TestDialogue:
    def test_secret_relu_dans_la_banque(self, client, univers, moteurs):
        """La partie reçoit les fiches sans secret : /api/npc/talk le relit par l'identifiant du PNJ."""
        fiche = client.get(f"/api/bank/{univers}", environ_base=DISTANT).get_json()
        assert "secret" not in fiche
        corps = {"npc": fiche, "history": [{"speaker": None, "content": "Bonjour"}]}
        client.post("/api/npc/talk", json=corps, environ_base=DISTANT).get_data()
        assert FICHE["secret"] in moteurs.appels[-1][0]
        # un secret envoyé par le navigateur ne remplace pas celui de la banque
        client.post("/api/npc/talk", json={**corps, "npc": {**fiche, "secret": "inventé"}}).get_data()
        assert FICHE["secret"] in moteurs.appels[-1][0] and "inventé" not in moteurs.appels[-1][0]

    def test_pnj_invente_garde_son_secret(self, client, moteurs):
        corps = {"npc": {**FICHE, "id": "absent-0000", "secret": "Il a volé la cloche."},
                 "history": [{"speaker": None, "content": "Bonjour"}]}
        client.post("/api/npc/talk", json=corps).get_data()
        assert "Il a volé la cloche." in moteurs.appels[-1][0]


class TestFrein:
    def test_delai_croissant_puis_oubli(self):
        t = [0.0]
        frein = reglages.Frein(horloge=lambda: t[0])
        for _ in range(4):
            frein.echec("a")
        assert frein.attente("a") == 0  # quatre erreurs de frappe : pas de verrou
        frein.echec("a")
        assert frein.attente("a") == 5
        frein.echec("a")
        assert frein.attente("a") == 10 and frein.attente("b") == 0  # par adresse
        for _ in range(20):
            frein.echec("a")
        assert frein.attente("a") == 300  # plafond
        t[0] = 301
        assert frein.attente("a") == 0
        frein.succes("a")
        frein.echec("a")
        assert frein.attente("a") == 0  # un succès remet le compte à zéro
        t[0] = 301 + 3600
        frein.echec("b")
        assert "a" not in frein.essais  # adresse oubliée au bout d'une heure

    def test_verrou_sur_les_routes(self, client, ctx, univers, mdp):
        for _ in range(reglages.Frein.SEUIL):
            assert client.delete("/api/univers", environ_base=DISTANT, headers=FAUX).status_code == 403
        r = client.delete("/api/univers", environ_base=DISTANT, headers=BON)  # même le bon : adresse verrouillée
        assert r.status_code == 429 and "réessayez dans 5 s" in r.get_json()["error"]
        assert client.get("/api/acces", environ_base=DISTANT, headers=BON).status_code == 429
        assert "secret" not in client.get(f"/api/bank/{univers}", environ_base=DISTANT, headers=BON).get_json()
        assert client.put("/api/reglages", json={"changements": {}}, environ_base=DISTANT,
                          headers=BON).status_code == 429
        autre = {"REMOTE_ADDR": "192.168.1.31"}
        assert client.get("/api/acces", environ_base=autre, headers=BON).get_json()["mj"] is True
        assert client.delete(f"/api/bank/{univers}", environ_base=LOCAL).status_code == 200  # le PC passe toujours
        ctx.frein.essais.clear()
        assert client.delete("/api/univers", environ_base=DISTANT, headers=BON).status_code == 200

    def test_verification_des_reglages_freinee(self, client, ctx, mdp):
        for _ in range(reglages.Frein.SEUIL):
            assert client.post("/api/reglages/verifier", json={"mot_de_passe": "x"},
                               environ_base=DISTANT).status_code == 403
        assert client.post("/api/reglages/verifier", json={"mot_de_passe": "dragon"},
                           environ_base=DISTANT).status_code == 429

    def test_sans_mot_de_passe_essaye_rien_n_est_compte(self, client, ctx, mdp):
        for _ in range(10):
            client.delete("/api/univers", environ_base=DISTANT)  # joueur qui clique : aucun mot de passe envoyé
        assert ctx.frein.essais == {}


class TestTailles:
    def test_plafond_global_celui_de_l_import(self, app):
        assert app.config["MAX_CONTENT_LENGTH"] == serveur.IMPORT_MAX_OCTETS + serveur.MARGE_MULTIPART

    def test_corps_json_trop_gros(self, client, ctx, univers):
        r = client.put("/api/scenario", data=json.dumps({"monde": "x" * serveur.CORPS_MAX}),
                       content_type="application/json")
        assert r.status_code == 413 and r.get_json()["error"] == "Requête trop volumineuse."
        assert ctx.banque.scenario()["monde"] == "Le Val"  # rien n'est effacé

    def test_audio_trop_long(self, cfg, moteurs, tts, portraits, monkeypatch):
        class Reconnaissance(FausseReconnaissance):
            def disponible(self):
                return True

            def transcrire(self, audio, indice):
                return "bonjour"
        client = create_app(cfg, moteurs=moteurs, tts=tts, reconnaissance=Reconnaissance(),
                            portraits=portraits).test_client()
        def stt(octets):
            return client.post("/api/stt", data={"audio": (io.BytesIO(octets), "q.webm")},
                               content_type="multipart/form-data")
        assert stt(b"x" * 1000).get_json() == {"text": "bonjour"}
        monkeypatch.setattr(serveur, "STT_MAX_OCTETS", 500)
        assert stt(b"x" * 1000).status_code == 413

    def test_import_cumul_et_nombre(self, client, ctx, monkeypatch):
        def importer(*noms):
            fichiers = [(io.BytesIO(json.dumps({**FICHE, "nom": n}).encode()), f"{n}.json") for n in noms]
            return client.post("/api/scenario/import", data={"fichiers": fichiers},
                               content_type="multipart/form-data")
        monkeypatch.setattr(serveur, "IMPORT_MAX_FICHIERS", 2)
        assert importer("a", "b", "c").status_code == 413
        assert importer("a", "b").status_code == 200
        monkeypatch.setattr(serveur, "IMPORT_MAX_OCTETS", 600)  # chaque fiche passe, pas les deux ensemble
        r = importer("d", "e")
        assert r.status_code == 413 and "au total" in r.get_json()["error"]
        assert not any(n["nom"] in ("d", "e") for n in ctx.banque.liste())
