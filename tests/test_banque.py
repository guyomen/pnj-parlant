import pytest

from pnj_parlant.banque import Banque


@pytest.fixture
def banque(tmp_path):
    return Banque(tmp_path / "pnj")


def test_scenario_vide_puis_enregistre(banque):
    assert banque.scenario() == {"monde": "", "notes_mj": ""}
    banque.enregistrer_scenario({"monde": "  Valmer.  ", "notes_mj": "x" * 30000, "autre": "ignoré"})
    scenario = banque.scenario()
    assert scenario["monde"] == "Valmer."
    assert len(scenario["notes_mj"]) == 20000


def test_ajouter_lire_lister_supprimer(banque):
    npc_id = banque.ajouter({"nom": "Ysolde la Rousse", "metier": "aubergiste"})
    assert npc_id.startswith("ysolde-la-rousse-")
    banque.ajouter({"nom": "Ébène", "metier": "barde"})
    assert banque.lire(npc_id) == {"nom": "Ysolde la Rousse", "metier": "aubergiste", "id": npc_id}
    assert [n["nom"] for n in banque.liste()] == ["Ébène", "Ysolde la Rousse"]  # tri sans tenir compte des accents
    assert banque.supprimer(npc_id) and not banque.existe(npc_id)
    assert not banque.supprimer(npc_id)


def test_l_identifiant_n_est_pas_enregistre_dans_le_fichier(banque):
    banque.ecrire("brom-0001", {"nom": "Brom", "id": "brom-0001"})
    assert "id" not in (banque.dossier / "brom-0001.json").read_text(encoding="utf-8")


def test_identifiants_dangereux_refuses(banque):
    for npc_id in ["../config", "a/b", "", "MAJ", None]:
        assert banque.chemin(npc_id) is None
        assert banque.lire(npc_id) is None


def test_liste_ignore_le_scenario_et_les_fichiers_abimes(banque):
    banque.enregistrer_scenario({"monde": "Valmer."})
    (banque.dossier / "casse-0001.json").write_text("{pas du json", encoding="utf-8")
    banque.ajouter({"nom": "Brom"})
    assert [n["nom"] for n in banque.liste()] == ["Brom"]


def test_banque_absente(banque):
    assert banque.liste() == []
