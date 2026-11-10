"""Routes du serveur, avec les faux moteurs de conftest.py."""
import json

from pnj_parlant.moteurs import MoteurIndisponible

YSOLDE = {"nom": "Ysolde", "metier": "aubergiste", "salutation": "Bienvenue !",
          "voix": {"name": "alice", "moteur": "faux", "genre": "feminin"}, "genre": "feminin"}
BROM = {"nom": "Brom", "metier": "forgeron", "apparence": "Immense.", "secret": "Il a volé une épée.",
        "voix": {"name": "bob"}}


def lignes(reponse):
    return [json.loads(ligne) for ligne in reponse.get_data(as_text=True).splitlines() if ligne.strip()]


class TestPages:
    def test_page_de_jeu_et_module_js(self, client):
        assert b"PNJ parlants" in client.get("/").data
        reponse = client.get("/js/scene.js")
        assert reponse.status_code == 200
        assert "javascript" in reponse.mimetype  # sinon le navigateur refuse le module

    def test_config(self, client):
        data = client.get("/api/config").get_json()
        assert data["tts"] == "faux" and data["stt_local"] is False and data["intervention"] == 0.3


class TestCreation:
    def test_fiche_avec_voix(self, client):
        npc = client.post("/api/npc/generate", json={"role": "aubergiste"}).get_json()
        assert npc["nom"] == "Ysolde la Rousse"
        assert npc["voix"]["name"] in {"alice", "bea", "nora"}

    def test_json_invalide(self, client, moteurs):
        moteurs.fiche_json = "rien"
        assert client.post("/api/npc/generate", json={}).status_code == 502

    def test_moteur_indisponible(self, client, moteurs):
        moteurs.fiche_json = MoteurIndisponible("Docker arrêté.")
        reponse = client.post("/api/npc/generate", json={})
        assert reponse.status_code == 503
        assert reponse.get_json()["error"].startswith("Docker arrêté.")


class TestBanque:
    def test_cycle_complet(self, client):
        assert client.post("/api/bank", json={"nom": "Brom"}).status_code == 400  # pas de salutation
        npc_id = client.post("/api/bank", json={"nom": "Brom", "salutation": "*Grogne.* Salut.",
                                                "genre": "masculin"}).get_json()["id"]
        assert client.get("/api/bank").get_json() == [{"id": npc_id, "nom": "Brom", "metier": ""}]
        npc = client.get(f"/api/bank/{npc_id}").get_json()
        assert npc["salutation"] == "Salut." and npc["voix"]["name"] in {"bob", "carl"}
        npc["metier"] = "forgeron"
        assert client.put(f"/api/bank/{npc_id}", json=npc).status_code == 200
        assert client.get(f"/api/bank/{npc_id}").get_json()["metier"] == "forgeron"
        assert client.delete(f"/api/bank/{npc_id}").status_code == 200
        assert client.get(f"/api/bank/{npc_id}").status_code == 404
        assert client.put(f"/api/bank/{npc_id}", json=npc).status_code == 404

    def test_scenario(self, client):
        client.put("/api/scenario", json={"monde": "Valmer.", "notes_mj": "Secret."})
        assert client.get("/api/scenario").get_json() == {"monde": "Valmer.", "notes_mj": "Secret."}


class TestDialogue:
    def test_une_ligne_par_phrase(self, client, moteurs):
        moteurs.reponses = ["Une bière ? Bien sûr, voyageur, ", "assieds-toi donc près du feu. ", "*Rit.* Voilà."]
        reponse = client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [
            {"speaker": "Ysolde", "content": "Bienvenue !"}, {"speaker": None, "content": "Une bière."}]})
        assert reponse.mimetype == "application/x-ndjson"
        assert lignes(reponse) == [{"phrase": "Une bière ? Bien sûr, voyageur, assieds-toi donc près du feu."},
                                   {"phrase": "Voilà."}]

    def test_scene_a_plusieurs(self, client, moteurs):
        moteurs.reponses = ["Ce forgeron raconte n'importe quoi, crois-moi.\nBrom : Mensonge !"]
        history = [{"speaker": "Ysolde", "content": "Bienvenue !"}, {"speaker": "Brom", "content": "Salut."},
                   {"speaker": None, "content": "Ysolde, Brom dit que tu triches."}]
        reponse = client.post("/api/npc/talk", json={"npc": YSOLDE, "presents": [BROM], "history": history})
        assert lignes(reponse) == [{"phrase": "Ce forgeron raconte n'importe quoi, crois-moi."}]
        system, messages = moteurs.appels[-1]
        assert "Brom, forgeron. Immense." in system and BROM["secret"] not in system
        assert "Brom :" in moteurs.arrets[-1] and "Ysolde :" not in moteurs.arrets[-1]
        assert messages[-1]["content"].startswith("Brom : Salut.\nVoyageur : Ysolde, Brom dit que tu triches.\n")

    def test_trois_phrases_au_plus(self, client, moteurs, ctx):
        moteurs.reponses = ["Ah, voyageur ! Bienvenue dans mon humble auberge du carrefour. ",
                            "Tu veux une bière ? Ou peut-être une chambre pour la nuit ? ",
                            "Ma cousine tient la forge. Elle est très douée. Et mon oncle..."]
        reponse = client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [{"content": "Salut."}]})
        dit = " ".join(ligne["phrase"] for ligne in lignes(reponse))
        assert dit == "Ah, voyageur ! Bienvenue dans mon humble auberge du carrefour. Tu veux une bière ?"
        assert "1 à 3 phrases courtes" in moteurs.appels[-1][0]

    def test_maximum_reglable(self, client, moteurs, ctx):
        ctx.phrases_max = 1
        moteurs.reponses = ["Bien le bonjour, voyageur égaré. Que veux-tu ?"]
        reponse = client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [{"content": "Salut."}]})
        assert lignes(reponse) == [{"phrase": "Bien le bonjour, voyageur égaré."}]
        assert "une phrase courte" in moteurs.appels[-1][0]

    def test_les_notes_du_mj_ne_sont_jamais_envoyees(self, client, moteurs):
        client.put("/api/scenario", json={"monde": "Valmer.", "notes_mj": "Le roi est un imposteur."})
        client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [{"speaker": None, "content": "Salut."}]})
        system, _ = moteurs.appels[-1]
        assert "Valmer." in system and "imposteur" not in system

    def test_requete_incomplete(self, client):
        assert client.post("/api/npc/talk", json={"npc": YSOLDE, "history": []}).status_code == 400
        assert client.post("/api/npc/talk", json={"history": [{"content": "a"}]}).status_code == 400

    def test_moteur_indisponible(self, client, moteurs):
        moteurs.reponses = MoteurIndisponible("Modèle local injoignable.")
        reponse = client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [{"content": "Salut."}]})
        assert reponse.status_code == 503

    def test_coupure_en_cours_de_reponse(self, client, moteurs):
        def coupure():
            yield "Bonjour, voyageur, que puis-je faire pour toi ce soir ? "
            raise MoteurIndisponible("Le modèle local s'est interrompu.")
        moteurs.reponses = coupure()
        reponse = client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [{"content": "Salut."}]})
        assert lignes(reponse)[-1] == {"error": "Le modèle local s'est interrompu."}


class TestVoix:
    def test_synthese_avec_la_voix_du_pnj(self, client, tts):
        reponse = client.post("/api/tts", json={"text": "*Rit.* J'ai 12 pièces.", "voice": YSOLDE["voix"]})
        assert reponse.status_code == 200 and reponse.mimetype == "audio/wav"
        assert tts.lues[-1] == ("J'ai douze pièces.", YSOLDE["voix"])

    def test_narrateur_avec_une_voix_libre(self, client, tts):
        client.post("/api/tts", json={"text": "Il sourit.", "voice": {"name": "nora"}, "narrateur": True,
                                      "eviter": [{"name": "alice"}]})
        assert tts.lues[-1][1]["name"] == "bea"  # ni nora (PNJ), ni alice (autre PNJ), mais féminine

    def test_rien_a_lire(self, client):
        assert client.post("/api/tts", json={"text": "*Rit.*"}).status_code == 400

    def test_autre_voix_en_evitant_celles_de_la_scene(self, client):
        voice = client.post("/api/voice", json={"genre": "masculin", "eviter": [{"name": "bob"}]}).get_json()
        assert voice["name"] == "carl"
        assert client.post("/api/voice", json={"choix": "nora"}).get_json()["name"] == "nora"
        assert client.post("/api/voice", json={"choix": "zorg"}).status_code == 404

    def test_liste_des_voix(self, client):
        assert {"name": "bob", "label": "Bob", "genre": "masculin"} in client.get("/api/voices").get_json()

    def test_moteur_de_voix_inconnu(self, client):
        assert client.put("/api/voice-engine", json={"moteur": "gramophone"}).status_code == 400

    def test_reconnaissance_indisponible(self, client):
        assert client.post("/api/stt").status_code == 404
