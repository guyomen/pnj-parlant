import random

import pytest

from pnj_parlant import voix
from conftest import FauxTTS

FEMMES = {"alice", "bea", "nora"}


class TestAttribuer:
    def test_voix_du_genre_du_pnj_et_reglages(self, tts):
        v = voix.attribuer(tts, {"genre": "feminin", "debit": "lent", "timbre": "grave"}, random.Random(0))
        assert v["name"] in FEMMES
        assert v["genre"] == "feminin" and v["moteur"] == "faux" and v["timbre"] == "grave"
        assert 1.14 <= v["length_scale"] <= 1.26  # débit lent, à 5 % près
        assert v["browser_rate"] == round(1 / 1.2, 2)

    def test_pnj_neutre_prend_n_importe_quelle_voix(self, tts):
        assert voix.attribuer(tts, {"genre": "neutre"})["name"] in {v["name"] for v, _ in tts.catalogue()}

    def test_evite_les_voix_des_autres_pnj(self, tts):
        eviter = [{"name": "alice"}, {"name": "bea"}]
        for graine in range(20):
            assert voix.attribuer(tts, {"genre": "feminin"}, random.Random(graine), eviter)["name"] == "nora"

    def test_si_toutes_les_voix_sont_prises_on_en_prend_une_quand_meme(self, tts):
        eviter = [v for v, _ in tts.catalogue()]
        assert voix.attribuer(tts, {"genre": "masculin"}, eviter=eviter)["name"] in {"bob", "carl"}

    def test_sans_voix_seulement_les_reglages(self):
        v = voix.attribuer(FauxTTS(voix=[]), {"genre": "masculin"})
        assert "name" not in v and v["browser_pitch"] == 0.85


class TestVerifier:
    def test_garde_une_voix_valide(self, tts):
        npc = {"nom": "Brom", "genre": "masculin", "voix": {"name": "carl", "moteur": "faux", "genre": "masculin"}}
        assert voix.verifier(tts, npc)["voix"]["name"] == "carl"

    def test_reattribue_si_autre_moteur_voix_absente_ou_genre_change(self, tts):
        for v in [{"name": "carl", "moteur": "piper", "genre": "masculin"},
                  {"name": "zorg", "moteur": "faux", "genre": "masculin"},
                  {"name": "carl", "moteur": "faux", "genre": "feminin"}]:
            npc = voix.verifier(tts, {"nom": "Brom", "genre": "masculin", "voix": dict(v)})
            assert npc["voix"]["name"] in {"bob", "carl"} and npc["voix"]["moteur"] == "faux"

    def test_meme_voix_a_chaque_chargement(self, tts):
        tirages = {voix.verifier(tts, {"nom": "Brom", "genre": "masculin"})["voix"]["name"] for _ in range(5)}
        assert len(tirages) == 1


class TestNarrateur:
    def test_voix_configuree_avec_reglages_neutres(self, tts):
        v = voix.voix_narrateur(tts)
        assert v["name"] == "nora" and v["length_scale"] == 1.0 and v["timbre"] == "moyen"

    def test_jamais_la_voix_d_un_pnj_de_la_scene(self, tts):
        # nora est prise : une autre voix du même genre (féminin)
        assert voix.voix_narrateur(tts, [{"name": "nora"}])["name"] in {"alice", "bea"}
        assert voix.voix_narrateur(tts, [{"name": "nora"}, {"name": "alice"}, {"name": "bea"}])["name"] in {
            "bob", "carl"}

    def test_aucune_voix_libre(self, tts):
        assert voix.voix_narrateur(tts, [v for v, _ in tts.catalogue()]) is None


class TestCharger:
    def test_moteur_inconnu(self, tmp_path):
        with pytest.raises(ValueError):
            voix.charger({"voix": {"moteur": "gramophone"}}, tmp_path)

    def test_narrateur_par_defaut_ou_configure(self, tmp_path):
        assert voix.charger({"voix": {"moteur": "edge"}}, tmp_path).narrateur == voix.NARRATEUR["edge"]
        cfg = {"voix": {"moteur": "piper", "piper": {"narrateur": "fr_FR-upmc-medium", "narrateur_locuteur": 1}}}
        moteur = voix.charger(cfg, tmp_path)
        assert (moteur.narrateur, moteur.narrateur_locuteur) == ("fr_FR-upmc-medium", 1)
