"""Caches de latence (lot 6) : chacun est testé avec son invalidation (délai, date du fichier, réglages)."""
import json
import os
import threading
import time

import pytest

from pnj_parlant import banque as banque_module
from pnj_parlant import moteurs as moteurs_module
from pnj_parlant import serveur, voix
from pnj_parlant.banque import Banque
from pnj_parlant.moteurs import MoteurIndisponible, Moteurs


class Horloge:
    """Remplace time.monotonic dans un module : `avancer(s)` fait passer le temps sans attendre."""

    def __init__(self, monkeypatch, module):
        self.t = 1000.0
        monkeypatch.setattr(module.time, "monotonic", lambda: self.t)

    def avancer(self, secondes):
        self.t += secondes


class Reponse:
    def __init__(self, corps):
        self.corps = corps

    def read(self):
        return json.dumps(self.corps).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def __iter__(self):
        return iter([b'data: {"choices": [{"delta": {"content": "Salut."}}]}\n', b"data: [DONE]\n"])


@pytest.fixture
def reseau(monkeypatch):
    """Faux Ollama et LM Studio : compte les appels par adresse."""
    etat = {"appels": [], "en_panne": False, "lm": [{"id": "qwen", "type": "llm", "state": "loaded"}],
            "ollama": [{"name": "qwen3:4b", "size": 5}]}

    def urlopen(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        etat["appels"].append(url)
        if etat["en_panne"]:
            raise OSError("injoignable")
        if url.endswith("/api/v0/models"):
            return Reponse({"data": etat["lm"]})
        if url.endswith("/api/tags"):
            return Reponse({"models": etat["ollama"]})
        return Reponse({})

    monkeypatch.setattr(moteurs_module.urllib.request, "urlopen", urlopen)
    etat["horloge"] = Horloge(monkeypatch, moteurs_module)
    etat["combien"] = lambda fin: sum(1 for u in etat["appels"] if u.endswith(fin))
    return etat


def moteurs(modele=""):
    return Moteurs({"moteurs": {"creation": "lmstudio", "dialogue": "lmstudio"},
                    "local": {"url": "http://ollama:11434"},
                    "lmstudio": {"url": "http://lm:1234", "modele": modele}})


class TestModeleLMStudio:
    def test_modele_configure_aucun_aller_retour_avant_la_replique(self, reseau):
        m = moteurs("mon-modele")
        assert "".join(m.replique("s", [{"role": "user", "content": "a"}])) == "Salut."
        assert reseau["combien"]("/api/v0/models") == 0

    def test_modele_charge_liste_gardee_puis_relue(self, reseau):
        m = moteurs()
        for _ in range(3):
            list(m.replique("s", [{"role": "user", "content": "a"}]))
        assert reseau["combien"]("/api/v0/models") == 1
        reseau["horloge"].avancer(moteurs_module.DUREE_CACHE + 1)
        reseau["lm"] = [{"id": "gemma", "type": "llm", "state": "loaded"}]
        assert m._lmstudio_modele()["id"] == "gemma"
        assert reseau["combien"]("/api/v0/models") == 2

    def test_serveur_injoignable_n_est_pas_garde(self, reseau):
        m = moteurs()
        reseau["en_panne"] = True
        for _ in range(2):
            with pytest.raises(MoteurIndisponible):
                m._lmstudio_modele()
        reseau["en_panne"] = False
        assert m._lmstudio_modele()["id"] == "qwen"  # LM Studio démarré : pris en compte tout de suite
        assert reseau["combien"]("/api/v0/models") == 3

    def test_nouveaux_moteurs_nouveau_cache(self, reseau):
        moteurs()._lmstudio_modele()
        moteurs()._lmstudio_modele()
        assert reseau["combien"]("/api/v0/models") == 2

    def test_oublier(self, reseau):
        m = moteurs()
        m._lmstudio_modele()
        m.oublier()
        m._lmstudio_modele()
        assert reseau["combien"]("/api/v0/models") == 2


class TestModelesOllama:
    def test_liste_gardee_puis_relue(self, reseau):
        m = moteurs()
        assert m.modeles_locaux() == [{"nom": "qwen3:4b", "taille": 5}]
        m.modeles_locaux()
        assert reseau["combien"]("/api/tags") == 1
        reseau["horloge"].avancer(moteurs_module.DUREE_CACHE + 1)
        reseau["ollama"] = []
        assert m.modeles_locaux() == []
        assert reseau["combien"]("/api/tags") == 2

    def test_ollama_injoignable_est_garde_aussi(self, reseau):
        """C'est le délai de connexion qu'on évite de payer à chaque page."""
        m = moteurs()
        reseau["en_panne"] = True
        assert m.modeles_locaux() == [] and m.modeles_locaux() == []
        assert reseau["combien"]("/api/tags") == 1

    def test_la_copie_rendue_peut_etre_modifiee(self, reseau):
        m = moteurs()
        m.modeles_locaux().clear()
        assert len(m.modeles_locaux()) == 1


class TestSante:
    @pytest.fixture
    def compte(self, ctx, monkeypatch):
        appels = []
        monkeypatch.setattr(ctx, "problemes", lambda: appels.append(1) or [{"cle": "x", "niveau": "erreur",
                                                                              "message": "m"}])
        return appels

    def test_gardee_puis_refaite(self, ctx, client, compte, monkeypatch):
        horloge = Horloge(monkeypatch, serveur)
        for _ in range(3):
            assert client.get("/api/sante").get_json()["problemes"][0]["cle"] == "x"
        assert len(compte) == 1
        horloge.avancer(serveur.SANTE_DUREE + 1)
        client.get("/api/sante")
        assert len(compte) == 2

    def test_invalidee_par_appliquer_reglages(self, ctx, client, compte):
        client.get("/api/sante")
        ctx.appliquer_reglages({"dialogue.historique": 20})
        client.get("/api/sante")
        assert len(compte) == 2

    def test_invalidee_meme_si_les_reglages_echouent(self, ctx, client, compte, monkeypatch):
        client.get("/api/sante")

        def echec(changements):
            raise ValueError("non")
        monkeypatch.setattr(ctx, "_appliquer_reglages", echec)
        with pytest.raises(ValueError):
            ctx.appliquer_reglages({"dialogue.historique": 20})
        client.get("/api/sante")
        assert len(compte) == 2

    def test_invalidee_par_le_changement_de_voix(self, ctx, client, compte):
        client.get("/api/sante")
        ctx.changer_tts(ctx.tts.nom)
        client.get("/api/sante")
        assert len(compte) == 2

    def test_la_reponse_n_est_pas_partagee(self, ctx, compte):
        ctx.problemes_recents().clear()
        assert len(ctx.problemes_recents()) == 1


class TestPiper:
    @pytest.fixture
    def piper(self, tmp_path):
        dossier = tmp_path / "voices"
        dossier.mkdir()
        (dossier / "a.onnx").write_bytes(b"")
        p = voix.Piper({"dossier": "voices"}, tmp_path)
        p._piper = (object, object)  # le paquet piper n'est pas nécessaire pour lister
        return p

    def test_catalogue_relu_quand_le_dossier_change(self, piper):
        assert list(piper._voix_installees()) == ["a"]
        avant = piper.dossier.stat().st_mtime_ns
        (piper.dossier / "b.onnx").write_bytes(b"")
        os.utime(piper.dossier, ns=(avant, avant))  # même date : le cache sert encore
        assert list(piper._voix_installees()) == ["a"]
        os.utime(piper.dossier, ns=(avant + 10_000_000, avant + 10_000_000))  # date changée : relu
        assert list(piper._voix_installees()) == ["a", "b"]

    def test_pas_de_relecture_a_chaque_phrase(self, piper, monkeypatch):
        piper._voix_installees()
        monkeypatch.setattr(type(piper.dossier), "glob", lambda *a: pytest.fail("dossier relu"))
        piper._voix_installees()
        piper.catalogue()

    def test_json_de_voix_illisible_ou_multilocuteur(self, piper):
        (piper.dossier / "a.onnx.json").write_text("{pas du json", encoding="utf-8")
        (piper.dossier / "b.onnx").write_bytes(b"")
        (piper.dossier / "b.onnx.json").write_text('{"num_speakers": 3}', encoding="utf-8")
        assert piper._voix_installees() == {"a": 1, "b": 3}
        assert len(piper.catalogue()) == 4  # pas d'erreur 500 sur /api/config

    def test_dossier_absent(self, piper):
        piper.dossier = piper.dossier / "ailleurs"
        assert piper._voix_installees() == {}

    def test_une_voix_se_charge_une_seule_fois_entre_fils(self, piper):
        charges = []

        class FausseVoix:
            @staticmethod
            def load(chemin):
                charges.append(chemin)
                time.sleep(0.05)
                return FausseVoix()

            def synthesize_wav(self, texte, wav, syn_config=None):
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)

        class Reglage:
            def __init__(self, **kw):
                pass
        piper._piper = (FausseVoix, Reglage)
        fils = [threading.Thread(target=piper.synthese, args=("Bonjour.", {"name": "a"})) for _ in range(4)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        assert len(charges) == 1


class TestBanque:
    @pytest.fixture
    def banque(self, tmp_path):
        return Banque(tmp_path / "pnj")

    @pytest.fixture
    def lectures(self, monkeypatch):
        lues = []
        original = banque_module._lire
        monkeypatch.setattr(banque_module, "_lire", lambda chemin: lues.append(chemin.name) or original(chemin))
        return lues

    def test_scenario_lu_une_fois(self, banque, lectures):
        banque.enregistrer_scenario({"monde": "Un port.", "theme": "x"})
        lectures.clear()
        for _ in range(3):
            assert banque.scenario()["monde"] == "Un port."
        assert lectures.count("_scenario.json") == 1 and lectures.count("_styles.json") == 1

    def test_ecriture_par_la_banque_invalide(self, banque):
        banque.enregistrer_scenario({"monde": "Un"})
        assert banque.scenario()["monde"] == "Un"
        banque.enregistrer_scenario({"monde": "Deux"})  # même taille de fichier : l'écriture invalide
        assert banque.scenario()["monde"] == "Deux"

    def test_modification_a_la_main_invalide(self, banque):
        banque.enregistrer_scenario({"monde": "Un"})
        assert banque.scenario()["monde"] == "Un"
        banque.scenario_path.write_text(json.dumps({"monde": "Édité à la main"}), encoding="utf-8")
        assert banque.scenario()["monde"] == "Édité à la main"
        banque.scenario_path.unlink()
        assert banque.scenario()["monde"] == ""

    def test_scenario_depend_des_styles(self, banque):
        banque.enregistrer_styles({"portraits": {"mien": {"nom": "Mien", "prompt": "style mien"}}})
        banque.enregistrer_scenario({"style_portrait": "mien"})
        assert banque.scenario()["style_portrait"] == "mien"
        (banque.dossier / "_styles.json").write_text("{}", encoding="utf-8")  # style retiré à la main
        assert banque.scenario()["style_portrait"] == ""

    def test_lieux_et_styles_gardes_et_invalides(self, banque, lectures):
        banque.enregistrer_lieux([{"nom": "Forge"}])
        banque.enregistrer_styles({})
        lectures.clear()
        for _ in range(3):
            assert [lieu["nom"] for lieu in banque.lieux()] == ["Forge"] and banque.styles()["themes"] == {}
        assert lectures.count("_lieux.json") == 1 and lectures.count("_styles.json") == 1
        banque.enregistrer_lieux([{"nom": "Forge"}, {"nom": "Port"}])
        assert len(banque.lieux()) == 2

    def test_fichier_abime_puis_repare(self, banque):
        banque.dossier.mkdir()
        banque.lieux_path.write_text("{pas du json", encoding="utf-8")
        assert banque.lieux() == []
        banque.lieux_path.write_text('[{"id": "a", "nom": "A"}]', encoding="utf-8")
        assert len(banque.lieux()) == 1

    def test_copies_independantes(self, banque):
        banque.enregistrer_lieux([{"nom": "Forge"}])
        banque.lieux()[0]["nom"] = "Piraté"
        banque.lieux().clear()
        assert banque.lieux()[0]["nom"] == "Forge"
        banque.scenario()["monde"] = "x"
        assert banque.scenario()["monde"] == ""

    def test_vider_invalide(self, banque):
        banque.enregistrer_scenario({"monde": "Un"})
        banque.enregistrer_lieux([{"nom": "Forge"}])
        banque.vider()
        assert banque.scenario()["monde"] == "" and banque.lieux() == []
