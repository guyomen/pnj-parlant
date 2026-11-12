"""Routes du serveur, avec les faux moteurs de conftest.py."""
import io
import json
import zipfile

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
        assert data["contexte_max"] == 8192


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
        assert client.get("/api/bank").get_json() == [{"id": npc_id, "nom": "Brom", "metier": "", "lieu": ""}]
        npc = client.get(f"/api/bank/{npc_id}").get_json()
        assert npc["salutation"] == "Salut." and npc["voix"]["name"] in {"bob", "carl"}
        npc["metier"] = "forgeron"
        assert client.put(f"/api/bank/{npc_id}", json=npc).status_code == 200
        assert client.get(f"/api/bank/{npc_id}").get_json()["metier"] == "forgeron"
        assert client.delete(f"/api/bank/{npc_id}").status_code == 200
        assert client.get(f"/api/bank/{npc_id}").status_code == 404
        assert client.put(f"/api/bank/{npc_id}", json=npc).status_code == 404

    def test_scenario(self, client):
        client.put("/api/scenario", json={"monde": "Valmer.", "notes_mj": "Secret.", "theme": "sylve"})
        assert client.get("/api/scenario").get_json() == {"monde": "Valmer.", "notes_mj": "Secret.", "theme": "sylve"}


LIEUX = [{"nom": "Auberge du Sanglier", "description": "Une salle enfumée.", "notes_mj": "Une trappe mène aux égouts."},
         {"nom": "Forge de Brom", "description": "Une chaleur d'enfer.", "notes_mj": ""}]


class TestUnivers:
    """Export en zip, import d'un zip ou des fichiers d'un dossier, univers d'exemple."""

    def _remplir(self, client):
        client.put("/api/scenario", json={"monde": "Valmer.", "notes_mj": "Secret."})
        client.put("/api/lieux", json=[{"id": "forge", "nom": "Forge"}])
        return client.post("/api/bank", json=YSOLDE).get_json()["id"]

    def test_export_puis_import_du_zip(self, client):
        ysolde = self._remplir(client)
        reponse = client.get("/api/scenario/export")
        assert reponse.mimetype == "application/zip"
        assert "attachment" in reponse.headers["Content-Disposition"]
        archive = reponse.data
        noms = sorted(zipfile.ZipFile(io.BytesIO(archive)).namelist())
        assert noms == sorted(["_lieux.json", "_scenario.json", f"{ysolde}.json"])
        client.delete(f"/api/bank/{ysolde}")
        r = client.post("/api/scenario/import", data={"fichiers": (io.BytesIO(archive), "univers.zip")},
                        content_type="multipart/form-data").get_json()
        assert r == {"scenario": True, "lieux": 1, "pnj": 1, "ignores": []}
        assert client.get(f"/api/bank/{ysolde}").get_json()["nom"] == "Ysolde"

    def test_import_des_fichiers_d_un_dossier_en_gardant_les_pnj(self, client):
        ysolde = self._remplir(client)
        fichiers = [(io.BytesIO(json.dumps(BROM).encode()), "brom-0002.json"),
                    (io.BytesIO(b'{"monde": "Brumecote"}'), "_scenario.json")]
        r = client.post("/api/scenario/import", data={"fichiers": fichiers, "remplacer": "0"},
                        content_type="multipart/form-data").get_json()
        assert r["pnj"] == 1 and r["scenario"]
        assert sorted(n["id"] for n in client.get("/api/bank").get_json()) == sorted([ysolde, "brom-0002"])
        assert client.get("/api/scenario").get_json()["monde"] == "Brumecote"
        assert client.get("/api/lieux").get_json()[0]["id"] == "forge"  # lieux non fournis : gardés

    def test_import_refuse(self, client):
        reponse = client.post("/api/scenario/import", data={"fichiers": (io.BytesIO(b"x"), "faux.zip")},
                              content_type="multipart/form-data")
        assert reponse.status_code == 400 and "zip" in reponse.get_json()["error"]
        assert client.post("/api/scenario/import", data={}, content_type="multipart/form-data").status_code == 400

    def test_exemples(self, client):
        self._remplir(client)
        exemples = client.get("/api/exemples").get_json()
        assert "pre-novice" in [e["id"] for e in exemples]
        r = client.post("/api/exemples/pre-novice", json={"remplacer": True}).get_json()
        assert r["pnj"] == 5 and r["lieux"] == 3 and r["ignores"] == []  # _infos.json n'est pas importé
        assert "Lyse" in [n["nom"] for n in client.get("/api/bank").get_json()]
        assert client.post("/api/exemples/inconnu", json={}).status_code == 404
        assert client.post("/api/exemples/..", json={}).status_code == 404


class TestLieux:
    def test_enregistrer_et_relire(self, client):
        lieux = client.put("/api/lieux", json=LIEUX).get_json()
        assert [l["id"] for l in lieux] == ["auberge-du-sanglier", "forge-de-brom"]
        assert client.get("/api/lieux").get_json() == lieux

    def test_creation_d_un_pnj_dans_un_lieu(self, client, moteurs):
        client.put("/api/lieux", json=LIEUX)
        npc = client.post("/api/npc/generate", json={"lieu": "auberge-du-sanglier"}).get_json()
        assert npc["lieu"] == "auberge-du-sanglier"
        assert "<lieu_du_pnj>\nAuberge du Sanglier\nUne salle enfumée.\n" in moteurs.derniere_demande
        assert "Une trappe mène aux égouts." in moteurs.derniere_demande  # notes du MJ : pour la création
        assert "- Forge de Brom : Une chaleur d'enfer." in moteurs.derniere_demande

    def test_lieu_inconnu_ignore(self, client):
        assert "lieu" not in client.post("/api/npc/generate", json={"lieu": "nulle-part"}).get_json()

    def test_dialogue_dans_un_lieu(self, client, moteurs):
        client.put("/api/lieux", json=LIEUX)
        npc = {**YSOLDE, "lieu": "auberge-du-sanglier"}
        client.post("/api/npc/talk", json={"npc": npc, "lieu": "forge-de-brom", "history": [{"content": "Salut."}]})
        system, _ = moteurs.appels[-1]
        assert "Tu te trouves en ce moment ici : Forge de Brom. Une chaleur d'enfer." in system
        assert "Ce n'est pas ton lieu habituel (Auberge du Sanglier)" in system
        assert "- Auberge du Sanglier : Une salle enfumée." in system  # lieux connus de tous
        assert "trappe" not in system  # jamais les notes du MJ pendant les dialogues

    def test_dialogue_sans_lieu(self, client, moteurs):
        client.put("/api/lieux", json=LIEUX)
        client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [{"content": "Salut."}]})
        assert "Tu te trouves en ce moment" not in moteurs.appels[-1][0]


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

    def test_longueur_courte_et_longue(self, client, moteurs, ctx):
        ctx.phrases_max = 3
        for longueur, phrases_max, consigne in (
            ("short", 1, "une phrase courte"),
            ("long", 6, "jusqu'à 6 phrases"),
        ):
            reponse = client.post("/api/npc/talk", json={
                "npc": YSOLDE, "history": [{"content": "Salut."}], "longueur": longueur,
            })
            assert reponse.status_code == 200
            assert moteurs.longueurs[-1] == longueur
            assert consigne in moteurs.appels[-1][0]
            assert len([item for item in lignes(reponse) if "phrase" in item]) <= phrases_max

    def test_longueur_inconnue_refusee(self, client, moteurs):
        reponse = client.post("/api/npc/talk", json={
            "npc": YSOLDE, "history": [{"content": "Salut."}], "longueur": "immense",
        })
        assert reponse.status_code == 400
        assert not moteurs.appels

    def test_compteurs_usage_ajoutes_apres_le_stream(self, client, moteurs):
        moteurs.usage = {"input_tokens": 120, "output_tokens": 15}
        reponse = client.post("/api/npc/talk", json={"npc": YSOLDE, "history": [{"content": "Salut."}]})
        assert lignes(reponse) == [{"phrase": "Bonjour."}, {"usage": moteurs.usage}]

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
