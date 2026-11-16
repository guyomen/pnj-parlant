"""Aventuriers (personnages des joueurs) : fiche, systèmes de jeu, jets, ce qu'en voit le PNJ, stockage, routes."""
import io
import json
import zipfile

import pytest
from faux import PNG

from pnj_parlant import aventuriers, dialogue
from pnj_parlant.banque import AVENTURIER, Banque, lire_zip

DISTANT = {"REMOTE_ADDR": "192.168.1.30"}  # le téléphone d'un joueur, sans mot de passe du MJ défini

ALDRIC = {"nom": "Aldric", "genre": "masculin", "classe": "Paladin humain",
          "apparence": "Grand, cheveux blonds, armure cabossée.", "systeme": "dnd5", "niveau": 5,
          "caracteristiques": {"for": 16, "dex": 10, "con": 14, "int": 8, "sag": 12, "cha": 16},
          "maitrises": {"persuasion": 1, "intimidation": 2, "athletisme": 1}}
MAELYS = {"nom": "Maëlys", "genre": "feminin", "classe": "Voleuse elfe", "apparence": "Petite, capuche verte.",
          "systeme": "cof2", "caracteristiques": {"agi": 3, "cha": 2, "for": -1, "per": 1},
          "superieures": ["agi"], "capacites": [{"nom": "Baratin", "carac": "cha", "bonus": 5}]}


def jet(fiche, jet_id):
    return next(j for j in aventuriers.jets(aventuriers.normaliser(fiche)) if j["id"] == jet_id)


class TestFiche:
    def test_sans_systeme(self):
        av = aventuriers.normaliser({"nom": "  Lina  la   Rousse ", "apparence": 3, "systeme": "gurps", "x": 1})
        assert av == {"nom": "Lina la Rousse", "classe": "", "apparence": "3", "systeme": ""}
        assert aventuriers.jets(av) == []

    def test_valeurs_bornees_et_champs_inconnus_retires(self):
        av = aventuriers.normaliser({**ALDRIC, "id": "x", "jets": [], "portrait": 3, "niveau": 99,
                                     "caracteristiques": {"for": 50, "dex": "12", "con": None, "cha": True},
                                     "maitrises": {"persuasion": 3, "tromperie": 2, "vol": 1, "arcanes": True}})
        assert "id" not in av and "jets" not in av and "portrait" not in av
        assert av["niveau"] == 20
        assert av["caracteristiques"] == {"for": 30, "dex": 12, "con": 10, "int": 10, "sag": 10, "cha": 10}
        assert av["maitrises"] == {"tromperie": 2}
        assert "capacites" not in av and "superieures" not in av  # propres à COF

    def test_cof2(self):
        av = aventuriers.normaliser({**MAELYS, "superieures": ["agi", "xyz"],
                                     "capacites": [*MAELYS["capacites"], {"nom": "", "bonus": 2}, "abîmé",
                                                   {"nom": "Esquive", "carac": "inconnue", "bonus": 99}]})
        assert av["caracteristiques"] == {"agi": 3, "con": 0, "for": -1, "per": 1, "cha": 2, "int": 0, "vol": 0}
        assert av["superieures"] == ["agi"]
        assert av["capacites"] == [{"nom": "Baratin", "carac": "cha", "bonus": 5},
                                   {"nom": "Esquive", "carac": "agi", "bonus": 20}]
        assert "maitrises" not in av

    def test_catalogue_pour_la_page(self):
        systemes = aventuriers.systemes_pour_la_page()
        assert set(systemes) == {"dnd5", "cof2"}
        assert len(systemes["dnd5"]["competences"]) == 18 and len(systemes["cof2"]["caracteristiques"]) == 7
        cof = [c["abrev"] for c in systemes["cof2"]["caracteristiques"]]
        assert cof == ["AGI", "CON", "FOR", "PER", "CHA", "INT", "VOL"]


class TestJets:
    def test_dnd5_modificateurs_et_maitrise(self):
        assert jet(ALDRIC, "car:for")["bonus"] == 3 and jet(ALDRIC, "car:int")["bonus"] == -1
        assert jet(ALDRIC, "comp:persuasion")["bonus"] == 3 + 3      # CHA +3, maîtrise +3 au niveau 5
        assert jet(ALDRIC, "comp:intimidation")["bonus"] == 3 + 6    # expertise : maîtrise doublée
        assert jet(ALDRIC, "comp:arcanes") == {"id": "comp:arcanes", "nom": "Arcanes", "groupe": "Compétences",
                                               "carac": "INT", "bonus": -1, "avantage": False}

    def test_bonus_de_maitrise(self):
        assert [aventuriers.bonus_de_maitrise(n) for n in (1, 4, 5, 9, 13, 17, 20)] == [2, 2, 3, 4, 5, 6, 6]

    def test_cof2_valeur_directe_de_bonus_et_capacites(self):
        assert jet(MAELYS, "car:agi") == {"id": "car:agi", "nom": "Agilité", "groupe": "Caractéristiques",
                                          "carac": "AGI", "bonus": 3, "avantage": True}
        assert jet(MAELYS, "car:cha")["avantage"] is False
        assert jet(MAELYS, "cap:0") == {"id": "cap:0", "nom": "Baratin", "groupe": "Capacités", "carac": "CHA",
                                        "bonus": 2 + 5, "avantage": False}


class TestCeQueVoitLePnj:
    def test_portrait(self):
        texte = aventuriers.portrait_pour_le_pnj(aventuriers.normaliser(ALDRIC))
        assert "Qui te parle : le voyageur." in texte and "armure cabossée" in texte and "Paladin humain" in texte
        assert "d'une force impressionnante" in texte and "d'un charisme saisissant" in texte
        assert "pas très futé" in texte                       # INT 8 : modificateur -1
        assert "doué en persuasion" in texte and "remarquable en intimidation" in texte
        assert "athlétisme" not in texte                      # pas un talent qui compte dans une conversation
        assert "Son nom est Aldric, mais tu ne le sais pas encore" in texte
        assert not any(c.isdigit() for c in texte)            # jamais de chiffres

    def test_aventuriere_et_capacites(self):
        texte = aventuriers.portrait_pour_le_pnj(aventuriers.normaliser(MAELYS))
        assert "la voyageuse" in texte and "vif et agile" in texte and "doué en baratin" in texte
        assert "qu'elle s'est présentée" in texte

    def test_sans_aventurier(self):
        assert aventuriers.portrait_pour_le_pnj(None) == "" and aventuriers.portrait_pour_le_pnj({"nom": ""}) == ""
        assert aventuriers.mots(None)["etiquette"] == "Voyageur"

    def test_consignes(self):
        npc = {"nom": "Brom", "metier": "forgeron"}
        sans = dialogue.consignes(npc)
        assert "Qui te parle" not in sans and "Jet de" not in sans  # cas de base inchangé
        avec = dialogue.consignes(npc, aventurier=aventuriers.normaliser(MAELYS), des=True)
        assert "Qui te parle : la voyageuse." in avec
        assert "si la voyageuse gagne vraiment ta confiance" in avec
        assert "« Jet de » ou « Jet d' » est un jet de dé de la voyageuse" in avec

    def test_scene_a_plusieurs_avec_une_aventuriere(self):
        av = aventuriers.normaliser(MAELYS)
        consignes = dialogue.consignes({"nom": "Brom"}, presents=[{"nom": "Ysolde"}], aventurier=av)
        assert "Tu n'es pas seul avec la voyageuse" in consignes and "« Voyageuse : »" in consignes
        messages = dialogue.messages("Brom", [{"speaker": None, "content": "Salut."}], [{"nom": "Ysolde"}], av)
        assert messages[0]["content"].startswith("(Une voyageuse s'approche.)\nVoyageuse : Salut.")
        assert "Maëlys" not in json.dumps(messages, ensure_ascii=False)  # le PNJ ne sait pas encore son nom

    def test_a_des_jets(self):
        assert not dialogue.a_des_jets([{"speaker": None, "content": "Bonjour."}])
        assert not dialogue.a_des_jets([{"speaker": "Brom", "content": "(Jet de chance, dit-il.)"}])
        assert dialogue.a_des_jets([{"speaker": None, "content": "(Jet de Persuasion : bon résultat.)"}])
        assert dialogue.a_des_jets([{"speaker": None, "content": "(Jet d'Intimidation : échec critique.)"}])

    def test_le_pnj_ne_garde_pas_la_replique_du_joueur(self):
        phrases = list(dialogue.repliques(iter(["Bien le bonjour, voyageur, que veux-tu donc ? ",
                                                "Aldric : Je cherche le sceptre."]),
                                          "Brom", aventurier={"nom": "Aldric"}))
        assert phrases == ["Bien le bonjour, voyageur, que veux-tu donc ?"]


@pytest.fixture
def banque(tmp_path):
    return Banque(tmp_path / "pnj")


class TestStockage:
    def test_aventurier_a_part_des_pnj(self, banque):
        av_id = banque.ajouter_aventurier(ALDRIC)
        assert av_id.startswith("aldric-") and (banque.dossier / f"{AVENTURIER}{av_id}.json").exists()
        assert banque.liste() == []  # jamais pris pour un PNJ
        lu = banque.lire_aventurier(av_id)
        assert lu["id"] == av_id and lu["portrait"] == 0 and lu["caracteristiques"]["for"] == 16
        assert [a["id"] for a in banque.aventuriers()] == [av_id]
        assert banque.lire_aventurier("../x") is None and banque.lire_aventurier("absent") is None

    def test_portrait_et_suppression(self, banque):
        av_id = banque.ajouter_aventurier(ALDRIC)
        assert banque.enregistrer_portrait(av_id, PNG, "png", AVENTURIER)
        assert banque.lire_aventurier(av_id)["portrait"] > 0 and banque.portrait(av_id) is None  # pas celui d'un PNJ
        assert not banque.enregistrer_portrait("absent-0001", PNG, "png", AVENTURIER)
        assert banque.supprimer_aventurier(av_id) and not list(banque.dossier.iterdir())
        assert not banque.supprimer_aventurier(av_id)

    def test_fichier_abime_ignore(self, banque):
        banque.dossier.mkdir(parents=True)
        (banque.dossier / f"{AVENTURIER}abime-0001.json").write_text("{pas du json", encoding="utf-8")
        (banque.dossier / f"{AVENTURIER}sans-nom-0001.json").write_text("{}", encoding="utf-8")
        assert banque.aventuriers() == []

    def test_nombre_limite(self, banque, monkeypatch):
        monkeypatch.setattr("pnj_parlant.banque.AVENTURIERS_MAX", 1)
        banque.ajouter_aventurier(ALDRIC)
        with pytest.raises(ValueError):
            banque.ajouter_aventurier(MAELYS)

    def test_nouvelle_table(self, banque):
        av_id = banque.ajouter_aventurier(ALDRIC)
        banque.enregistrer_portrait(av_id, PNG, "png", AVENTURIER)
        banque.vider()
        assert banque.aventuriers() == [] and not list(banque.dossier.glob(f"{AVENTURIER}*"))

    def test_export_et_import(self, banque, tmp_path):
        av_id = banque.ajouter_aventurier(ALDRIC)
        banque.enregistrer_portrait(av_id, PNG, "png", AVENTURIER)
        banque.ajouter({"nom": "Brom", "salutation": "Salut."})
        fichiers = lire_zip(banque.exporter_zip())
        assert f"{AVENTURIER}{av_id}.json" in fichiers and f"{AVENTURIER}{av_id}.png" in fichiers

        autre = Banque(tmp_path / "autre")
        autre.ajouter_aventurier(MAELYS)  # remplacé : absent de l'import
        r = autre.importer(fichiers)
        assert r["aventuriers"] == 1 and r["pnj"] == 1 and r["ignores"] == []
        assert [a["nom"] for a in autre.aventuriers()] == ["Aldric"]
        assert autre.lire_aventurier(av_id)["portrait"] > 0

        garde = Banque(tmp_path / "garde")
        maelys = garde.ajouter_aventurier(MAELYS)
        garde.importer(fichiers, remplacer=False)
        assert {a["id"] for a in garde.aventuriers()} == {av_id, maelys}

    def test_import_d_un_aventurier_seul_renomme_a_la_main(self, banque):
        r = banque.importer({f"{AVENTURIER}Mon Héros.json": json.dumps(ALDRIC).encode(),
                             f"{AVENTURIER}Mon Héros.png": PNG})
        assert r["aventuriers"] == 1 and r["ignores"] == []
        (av,) = banque.aventuriers()
        assert av["id"].startswith("aldric-") and av["portrait"] > 0


class TestRoutes:
    def test_systemes(self, client):
        assert set(client.get("/api/systemes").get_json()) == {"dnd5", "cof2"}

    def test_creer_lire_modifier_supprimer(self, client):
        assert client.get("/api/aventuriers").get_json() == []
        av_id = client.post("/api/aventuriers", json=ALDRIC).get_json()["id"]
        (lu,) = client.get("/api/aventuriers").get_json()
        assert lu["id"] == av_id and lu["nom"] == "Aldric"
        assert any(j["id"] == "comp:persuasion" and j["bonus"] == 6 for j in lu["jets"])  # bonus calculés ici
        assert client.put(f"/api/aventuriers/{av_id}", json={**lu, "nom": "Aldric le Brave"}).status_code == 200
        assert client.get(f"/api/aventuriers/{av_id}").get_json()["nom"] == "Aldric le Brave"
        assert client.delete(f"/api/aventuriers/{av_id}").status_code == 200
        assert client.get(f"/api/aventuriers/{av_id}").status_code == 404

    def test_erreurs(self, client):
        assert client.post("/api/aventuriers", json={"nom": "  "}).status_code == 400
        assert client.post("/api/aventuriers", json=[1]).status_code == 400
        assert client.put("/api/aventuriers/absent-0001", json=ALDRIC).status_code == 404
        assert client.delete("/api/aventuriers/absent-0001").status_code == 404
        assert client.get("/api/aventuriers/absent-0001/portrait").status_code == 404

    def test_ecriture_reservee_au_mj(self, client):
        assert client.post("/api/aventuriers", json=ALDRIC, environ_base=DISTANT).status_code == 403
        assert client.get("/api/aventuriers", environ_base=DISTANT).status_code == 200  # lecture ouverte

    def test_portrait(self, client, portraits):
        av_id = client.post("/api/aventuriers", json=ALDRIC).get_json()["id"]
        r = client.post(f"/api/aventuriers/{av_id}/portrait", json={"apparence": "Barbe rousse."}).get_json()
        assert r["portrait"] > 0 and "Barbe rousse." in portraits.prompts[-1]
        assert client.get(f"/api/aventuriers/{av_id}/portrait").data == PNG
        assert client.get(f"/api/aventuriers/{av_id}").get_json()["apparence"] == ALDRIC["apparence"]  # pas écrit
        assert client.delete(f"/api/aventuriers/{av_id}/portrait").status_code == 200
        assert client.delete(f"/api/aventuriers/{av_id}/portrait").status_code == 404
        portraits.actif = False
        assert client.post(f"/api/aventuriers/{av_id}/portrait").status_code == 400

    def test_export_zip(self, client):
        av_id = client.post("/api/aventuriers", json=ALDRIC).get_json()["id"]
        noms = zipfile.ZipFile(io.BytesIO(client.get("/api/scenario/export").data)).namelist()
        assert f"{AVENTURIER}{av_id}.json" in noms

    def test_dialogue_avec_aventurier_et_jet(self, client, moteurs):
        history = [{"speaker": None, "content": "Bonjour."},
                   {"speaker": None, "content": "(Jet de Persuasion : bon résultat.)"}]
        r = client.post("/api/npc/talk", json={"npc": {"nom": "Brom", "metier": "forgeron"}, "history": history,
                                               "aventurier": {**MAELYS, "jets": "ignoré"}})
        assert r.status_code == 200
        system, messages = moteurs.appels[-1]
        assert "Qui te parle : la voyageuse." in system and "« Jet de »" in system
        assert messages[0]["content"].startswith("(Une voyageuse s'approche.)")
        assert "Maëlys :" in moteurs.arrets[-1]

    def test_dialogue_sans_aventurier_inchange(self, client, moteurs):
        for aventurier in (None, "Aldric", {"nom": ""}):
            client.post("/api/npc/talk", json={"npc": {"nom": "Brom"}, "aventurier": aventurier,
                                               "history": [{"speaker": None, "content": "Bonjour."}]})
            system, messages = moteurs.appels[-1]
            assert "Qui te parle" not in system and "Jet de" not in system
            assert messages[0]["content"].startswith("(Un voyageur s'approche.)")
