import io
import json
import zipfile

import pytest

from pnj_parlant import banque as module_banque
from pnj_parlant.banque import Banque, lire_zip, nom_de_fichier


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


class TestLieux:
    def test_identifiants_tires_du_nom_et_uniques(self, banque):
        lieux = banque.enregistrer_lieux([{"nom": "Forge"}, {"nom": "Forge"}, {"nom": "  "}, "pas un lieu",
                                          {"nom": "Porte nord", "description": "x" * 3000}])
        assert [l["id"] for l in lieux] == ["forge", "forge-2", "porte-nord"]
        assert len(lieux[2]["description"]) == 2000

    def test_un_lieu_renomme_garde_son_identifiant(self, banque):
        [forge] = banque.enregistrer_lieux([{"nom": "Forge"}])
        [renomme] = banque.enregistrer_lieux([{**forge, "nom": "Forge de Brom"}])
        assert renomme["id"] == "forge" and banque.lieu("forge")["nom"] == "Forge de Brom"

    def test_identifiant_dangereux_remplace(self, banque):
        assert banque.enregistrer_lieux([{"id": "../x", "nom": "Égouts"}])[0]["id"] == "egouts"

    def test_sans_lieux(self, banque):
        assert banque.lieux() == [] and banque.lieu("forge") is None and banque.lieu("") is None

    def test_lieux_ignores_par_la_liste_des_pnj(self, banque):
        banque.enregistrer_lieux([{"nom": "Forge"}])
        banque.ajouter({"nom": "Brom", "lieu": "forge"})
        assert [(n["nom"], n["lieu"]) for n in banque.liste()] == [("Brom", "forge")]


def test_banque_absente(banque):
    assert banque.liste() == []


# --- Export et import d'un scénario complet ----------------------------------------

def _zip(fichiers):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as archive:
        for nom, contenu in fichiers.items():
            archive.writestr(nom, contenu if isinstance(contenu, (str, bytes)) else json.dumps(contenu))
    return tampon.getvalue()


def _remplir(banque):
    banque.enregistrer_scenario({"monde": "Valmer.", "notes_mj": "Le maire ment."})
    banque.enregistrer_lieux([{"id": "forge", "nom": "Forge"}])
    banque.ecrire("brom-0001", {"nom": "Brom", "lieu": "forge"})


def test_export_puis_import_dans_une_autre_banque(banque, tmp_path):
    _remplir(banque)
    archive = banque.exporter_zip()
    assert sorted(zipfile.ZipFile(io.BytesIO(archive)).namelist()) == ["_lieux.json", "_scenario.json", "brom-0001.json"]
    autre = Banque(tmp_path / "autre")
    r = autre.importer(lire_zip(archive))
    assert r == {"scenario": True, "lieux": 1, "pnj": 1, "ignores": []}
    assert autre.scenario() == banque.scenario() and autre.lieux() == banque.lieux()
    assert autre.lire("brom-0001")["nom"] == "Brom"


def test_import_remplace_ou_garde_les_pnj(banque):
    _remplir(banque)
    banque.importer({"ysolde-0002.json": b'{"nom": "Ysolde"}'})
    assert [n["nom"] for n in banque.liste()] == ["Ysolde"]
    assert banque.scenario() == {"monde": "", "notes_mj": ""} and banque.lieux() == []  # absents : vidés
    _remplir(banque)
    banque.importer({"ysolde-0002.json": b'{"nom": "Ysolde"}'}, remplacer=False)
    assert [n["nom"] for n in banque.liste()] == ["Brom", "Ysolde"]
    assert banque.scenario()["monde"] == "Valmer." and len(banque.lieux()) == 1  # absents : gardés


def test_import_fichiers_douteux(banque):
    r = banque.importer({"Mon PNJ.json": '{"nom": "Gaspard"}'.encode(),  # renommé à la main : nouvel identifiant
                         "abime.json": b"{pas du json", "sans-nom.json": b'{"metier": "x"}',
                         "_autre.json": b"{}", "_scenario.json": "\ufeff{\"monde\": \"Brumecôte\"}".encode()})
    assert r["ignores"] == ["_autre.json", "abime.json", "sans-nom.json"]
    assert [n["id"].startswith("gaspard-") for n in banque.liste()] == [True]
    assert banque.scenario()["monde"] == "Brumecôte"  # BOM du Bloc-notes accepté
    with pytest.raises(ValueError):
        banque.importer({"lisez-moi.json": b"[]"})


def test_lire_zip_aplatit_et_protege(monkeypatch):
    assert set(lire_zip(_zip({"pre-novice/_lieux.json": [], "pre-novice/a-1.json": {"nom": "A"},
                              "__MACOSX/._a-1.json": "x", "lisez-moi.txt": "x"}))) == {"_lieux.json", "a-1.json"}
    with pytest.raises(ValueError, match="Deux fichiers"):
        lire_zip(_zip({"un/a-1.json": {}, "deux/a-1.json": {}}))
    with pytest.raises(ValueError, match="zip valide"):
        lire_zip(b"pas un zip")
    monkeypatch.setattr(module_banque, "IMPORT_MAX_OCTETS", 10)
    with pytest.raises(ValueError, match="volumineuse"):
        lire_zip(_zip({"a-1.json": {"nom": "A" * 50}}))


def test_nom_de_fichier_sans_chemin():
    assert nom_de_fichier("../../etc/a-1.json") == "a-1.json"
    assert nom_de_fichier(r"C:\univers\a-1.json") == "a-1.json"
