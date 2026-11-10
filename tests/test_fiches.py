import random

import pytest

from pnj_parlant import fiches
from pnj_parlant.moteurs import MoteurIndisponible


def test_parse_json_supporte_le_texte_et_les_balises_autour():
    assert fiches.parse_json('Voici :\n```json\n{"nom": "Brom"}\n```') == {"nom": "Brom"}


class TestDemande:
    def test_tirages_au_sort_sans_consignes(self):
        texte = fiches.demande({}, rng=random.Random(1))
        assert "Métier : " in texte and "Le nom commence par la lettre" in texte
        assert "Suggestions : humeur" in texte

    def test_role_nom_et_genre_imposes(self):
        texte = fiches.demande({}, role="forgeron", nom="Brom", genre="masculin")
        assert "Métier : forgeron." in texte
        assert "Nom imposé : Brom." in texte
        assert "Genre : masculin." in texte

    def test_genre_inconnu_ignore(self):
        assert "Genre" not in fiches.demande({}, genre="dragon")

    def test_avec_consignes_le_metier_et_le_nom_viennent_des_consignes(self):
        texte = fiches.demande({}, consignes="Le cousin forgeron de Brom.")
        assert "<consignes_pour_ce_pnj>\nLe cousin forgeron de Brom.\n</consignes_pour_ce_pnj>" in texte
        assert "Métier : celui qu'indiquent les consignes" in texte
        assert "Si les consignes donnent son nom, garde-le" in texte

    def test_scenario(self):
        texte = fiches.demande({"monde": "Valmer.", "notes_mj": "Le roi est mort."})
        assert "<univers>\nValmer.\n</univers>" in texte
        assert "<notes_du_mj>\nLe roi est mort.\n</notes_du_mj>" in texte


class TestCreer:
    def test_fiche_avec_salutation_nettoyee(self, moteurs):
        npc = fiches.creer(moteurs, {}, role="aubergiste")
        assert npc["nom"] == "Ysolde la Rousse"
        assert npc["salutation"] == "Bienvenue, voyageur !"
        assert "Métier : aubergiste." in moteurs.derniere_demande

    def test_json_invalide(self, moteurs):
        moteurs.fiche_json = "Désolé, je ne peux pas."
        with pytest.raises(ValueError):
            fiches.creer(moteurs, {})

    def test_moteur_indisponible(self, moteurs):
        moteurs.fiche_json = MoteurIndisponible("Docker arrêté.")
        with pytest.raises(MoteurIndisponible):
            fiches.creer(moteurs, {})
