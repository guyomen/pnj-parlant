"""Portraits des PNJ : description pour le générateur, moteurs, stockage dans la banque, routes."""
import io
import json
import urllib.request
import zipfile

import pytest

from conftest import PNG
from pnj_parlant import portraits
from pnj_parlant.banque import Banque
from pnj_parlant.moteurs import MoteurIndisponible
from pnj_parlant.portraits import STYLE, EnLigne, PortraitIndisponible, prompt_portrait, type_image

BROM = {"nom": "Brom", "metier": "forgeron", "genre": "masculin", "apparence": "Un colosse au tablier brûlé.",
        "salutation": "Salut."}


class Langage:
    """Moteur de langage minimal : renvoie `reponse` (texte) ou lève l'exception donnée."""

    def __init__(self, reponse):
        self.reponse, self.demandes = reponse, []

    def fiche(self, system, demande, schema):
        self.demandes.append(demande)
        if isinstance(self.reponse, Exception):
            raise self.reponse
        return self.reponse


# --- Description du portrait -----------------------------------------------------------------
def test_prompt_traduit_par_le_modele_de_langage():
    langage = Langage('{"prompt": "a burly  blacksmith with a burnt apron"}')
    assert prompt_portrait(langage, BROM, "oil painting") == "a burly blacksmith with a burnt apron, oil painting"
    assert "Apparence : Un colosse au tablier brûlé." in langage.demandes[0] and "Brom" not in langage.demandes[0]


@pytest.mark.parametrize("reponse", [MoteurIndisponible("Ollama arrêté"), "pas du JSON", '{"autre": 1}', "[1]"])
def test_prompt_sans_modele_de_langage_tire_de_la_fiche(reponse):
    assert prompt_portrait(Langage(reponse), BROM, "") == "man, forgeron, Un colosse au tablier brûlé."
    assert prompt_portrait(Langage(reponse), {"genre": "?"}).startswith("person, head and shoulders portrait")


def test_type_image():
    assert type_image(PNG) == "png"
    assert type_image(b"\xff\xd8\xff\xe0...") == "jpg"
    assert type_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert type_image(b"<html>") is None


# --- Moteurs -----------------------------------------------------------------------------------
def test_charger():
    assert isinstance(portraits.charger({}), portraits.Aucun)
    assert isinstance(portraits.charger({"moteur": "en_ligne"}), EnLigne)
    assert isinstance(portraits.charger({"moteur": "local"}), portraits.Local)
    assert isinstance(portraits.charger({"moteur": "dessin"}), portraits.Aucun)
    with pytest.raises(PortraitIndisponible):
        portraits.Aucun().generer("x", 1)


def test_local_sans_paquets(monkeypatch):
    local = portraits.Local({})
    monkeypatch.setattr(local, "disponible", lambda: False)
    with pytest.raises(PortraitIndisponible, match="option portraits"):
        local.generer("x", 1)


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_en_ligne(monkeypatch):
    moteur = EnLigne({"taille": 256})
    adresse = moteur.adresse("a dwarf, oil painting", 7)
    assert adresse.startswith("https://image.pollinations.ai/prompt/a%20dwarf%2C%20oil%20painting?")
    assert "width=256" in adresse and "seed=7" in adresse and "nologo=true" in adresse
    demandes = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout: demandes.append(r) or Reponse(PNG))
    assert moteur.generer("a dwarf", 7) == (PNG, "png")
    assert demandes[0].get_header("User-agent") == "pnj-parlant"

    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout: Reponse(b"<html>quota</html>"))
    with pytest.raises(PortraitIndisponible, match="autre chose"):
        moteur.generer("a dwarf", 7)

    def coupe(r, timeout):
        raise OSError("réseau")
    monkeypatch.setattr(urllib.request, "urlopen", coupe)
    with pytest.raises(PortraitIndisponible, match="réseau"):
        moteur.generer("a dwarf", 7)


# --- Banque : stockage, export, import -------------------------------------------------------
@pytest.fixture
def banque(tmp_path):
    return Banque(tmp_path / "pnj")


def test_portrait_suit_la_fiche(banque):
    npc_id = banque.ajouter(BROM)
    assert banque.portrait(npc_id) is None and banque.lire(npc_id)["portrait"] == 0
    banque.enregistrer_portrait(npc_id, b"\xff\xd8\xff jpeg", "jpg")
    banque.enregistrer_portrait(npc_id, PNG, "png")  # remplace le précédent, quel que soit son format
    assert [p.name for p in banque.dossier.iterdir() if p.suffix != ".json"] == [f"{npc_id}.png"]
    version = banque.version_portrait(npc_id)
    assert version > 0 and banque.lire(npc_id)["portrait"] == banque.liste()[0]["portrait"] == version
    banque.ecrire(npc_id, banque.lire(npc_id))  # « portrait » n'est pas écrit dans la fiche
    assert "portrait" not in json.loads(banque.chemin(npc_id).read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        banque.enregistrer_portrait("../x", PNG, "png")
    assert banque.supprimer(npc_id) and banque.portrait(npc_id) is None  # supprimé avec le PNJ
    assert banque.portrait("../x") is None


def test_export_et_import_avec_portraits(banque, tmp_path):
    npc_id = banque.ajouter(BROM)
    banque.enregistrer_portrait(npc_id, PNG, "png")
    archive = zipfile.ZipFile(io.BytesIO(banque.exporter_zip()))
    assert f"{npc_id}.png" in archive.namelist()

    autre = Banque(tmp_path / "autre")
    fichiers = {n: archive.read(n) for n in archive.namelist()}
    fichiers.update({"inconnu-0001.png": PNG, "faux-0002.jpg": b"<html>", "Brom (copie).json": json.dumps(BROM).encode(),
                     "Brom (copie).jpeg": b"\xff\xd8\xff jpeg"})
    r = autre.importer(fichiers)
    assert sorted(r["ignores"]) == ["faux-0002.jpg", "inconnu-0001.png"]  # sans fiche, ou pas une image
    assert autre.portrait(npc_id).read_bytes() == PNG
    copie = next(n for n in autre.liste() if n["id"] != npc_id)
    assert copie["portrait"] and autre.portrait(copie["id"]).suffix == ".jpg"  # suit la fiche renommée
    assert autre.vider() == 2
    assert [p for p in autre.dossier.iterdir() if p.suffix != ".json"] == []  # portraits supprimés avec les PNJ


def test_import_remplace_l_ancien_portrait(banque):
    npc_id = banque.ajouter(BROM)
    banque.enregistrer_portrait(npc_id, PNG, "png")
    banque.importer({f"{npc_id}.json": json.dumps(BROM).encode()}, remplacer=False)
    assert banque.portrait(npc_id) is None


# --- Routes ------------------------------------------------------------------------------------
def test_routes_du_portrait(client, portraits, ctx):
    npc_id = client.post("/api/bank", json=BROM).get_json()["id"]
    assert client.get("/api/config").get_json()["portraits"] == "faux"
    assert client.get(f"/api/bank/{npc_id}/portrait").status_code == 404

    r = client.post(f"/api/bank/{npc_id}/portrait", json={**BROM, "apparence": "Un nain chauve."})
    assert r.status_code == 200 and "Un nain chauve." in r.get_json()["prompt"]  # fiche en cours d'édition
    assert portraits.prompts[0] == r.get_json()["prompt"] and portraits.prompts[0].endswith(STYLE)
    version = r.get_json()["portrait"]
    assert version == client.get("/api/bank").get_json()[0]["portrait"] == client.get(f"/api/bank/{npc_id}").get_json()["portrait"]
    image = client.get(f"/api/bank/{npc_id}/portrait?v={version}")
    assert image.status_code == 200 and image.data == PNG and image.mimetype == "image/png"
    assert image.cache_control.max_age == 86400  # adresse versionnée : gardée en cache
    assert client.get(f"/api/bank/{npc_id}/portrait").cache_control.max_age == 0

    assert client.delete(f"/api/bank/{npc_id}/portrait").status_code == 200
    assert client.delete(f"/api/bank/{npc_id}/portrait").status_code == 404
    assert client.post("/api/bank/inconnu-0000/portrait").status_code == 404


def test_portrait_erreurs(client, portraits):
    npc_id = client.post("/api/bank", json=BROM).get_json()["id"]
    portraits.erreur = PortraitIndisponible("Réseau coupé.")
    r = client.post(f"/api/bank/{npc_id}/portrait")
    assert r.status_code == 503 and r.get_json()["error"] == "Réseau coupé."
    portraits.actif = False
    assert client.post(f"/api/bank/{npc_id}/portrait").status_code == 400
    assert client.get("/api/config").get_json()["portraits"] is None
