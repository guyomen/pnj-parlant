"""Portraits des PNJ : description pour le générateur, moteurs, stockage dans la banque, routes."""
import io
import json
import urllib.error
import urllib.request
import zipfile

import pytest

from conftest import PNG
from pnj_parlant import portraits
from pnj_parlant.banque import Banque
from pnj_parlant.moteurs import MoteurIndisponible
from pnj_parlant.portraits import STYLE, STYLES, EnLigne, PortraitIndisponible, prompt_portrait, style_valide, type_image

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
    assert prompt_portrait(langage, BROM, "oil painting") == "oil painting, a burly blacksmith with a burnt apron"
    assert "Apparence : Un colosse au tablier brûlé." in langage.demandes[0] and "Brom" not in langage.demandes[0]


@pytest.mark.parametrize("reponse", [MoteurIndisponible("Ollama arrêté"), "pas du JSON", '{"autre": 1}', "[1]"])
def test_prompt_sans_modele_de_langage_tire_de_la_fiche(reponse):
    assert prompt_portrait(Langage(reponse), BROM, "") == "man, forgeron, Un colosse au tablier brûlé."
    assert prompt_portrait(Langage(reponse), {"genre": "?"}) == f"{STYLE}, person"


def test_styles_de_dessin():
    assert list(STYLES) == ["peinture", "manga", "jdr80", "photo", "crayon"]
    assert all(nom and resume and "head and shoulders" in prompt for nom, resume, prompt in STYLES.values())
    assert [style_valide(s) for s in ("manga", " Photo ", "aquarelle", None)] == ["manga", "photo", "", ""]
    assert portraits.styles()[1] == {"id": "manga", "nom": "Manga", "resume": STYLES["manga"][1]}


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


def erreur_http(code, retry_after=None):
    import email.message
    entetes = email.message.Message()
    if retry_after is not None:
        entetes["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://image.pollinations.ai/", code, "limite", entetes, io.BytesIO(b"{}"))


def test_en_ligne_limite_gratuite(monkeypatch):
    attentes = []
    moteur = EnLigne({}, dormir=attentes.append)
    reponses = [erreur_http(402, 18), Reponse(PNG)]

    def urlopen(r, timeout):
        rep = reponses.pop(0)
        if isinstance(rep, Exception):
            raise rep
        return rep
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert moteur.generer("a dwarf", 1) == (PNG, "png") and attentes == [18.0]  # attendu puis réessayé

    reponses[:] = [erreur_http(429, 300)]  # attente trop longue : message clair, sans attendre
    with pytest.raises(PortraitIndisponible, match="réessayez dans 300 s"):
        moteur.generer("a dwarf", 1)
    reponses[:] = [erreur_http(402, 10), erreur_http(402, 40)]  # encore limité après l'attente
    with pytest.raises(PortraitIndisponible, match="réessayez dans 40 s"):
        moteur.generer("a dwarf", 1)
    reponses[:] = [erreur_http(500)]
    with pytest.raises(PortraitIndisponible, match="erreur 500"):
        moteur.generer("a dwarf", 1)
    assert attentes == [18.0, 10.0]


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
    assert portraits.prompts[0] == r.get_json()["prompt"] and portraits.prompts[0].startswith(STYLE)
    version = r.get_json()["portrait"]
    assert version == client.get("/api/bank").get_json()[0]["portrait"] == client.get(f"/api/bank/{npc_id}").get_json()["portrait"]
    image = client.get(f"/api/bank/{npc_id}/portrait?v={version}")
    assert image.status_code == 200 and image.data == PNG and image.mimetype == "image/png"
    assert image.cache_control.max_age == 86400  # adresse versionnée : gardée en cache
    assert client.get(f"/api/bank/{npc_id}/portrait").cache_control.max_age == 0

    assert client.delete(f"/api/bank/{npc_id}/portrait").status_code == 200
    assert client.delete(f"/api/bank/{npc_id}/portrait").status_code == 404
    assert client.post("/api/bank/inconnu-0000/portrait").status_code == 404


def test_portrait_au_style_du_scenario(client, portraits, cfg):
    npc_id = client.post("/api/bank", json=BROM).get_json()["id"]
    assert [s["id"] for s in client.get("/api/config").get_json()["styles_portrait"]] == list(STYLES)
    client.put("/api/scenario", json={"monde": "Valmer.", "style_portrait": "crayon"})
    client.post(f"/api/bank/{npc_id}/portrait")
    assert portraits.prompts[-1].startswith(STYLES["crayon"][2])
    client.put("/api/scenario", json={"monde": "Valmer.", "style_portrait": "inconnu"})  # → style par défaut
    client.post(f"/api/bank/{npc_id}/portrait")
    assert portraits.prompts[-1].startswith(STYLE)


def test_style_par_defaut_de_config(tmp_path, moteurs, tts, portraits):
    from conftest import FausseReconnaissance
    from pnj_parlant.config import Config
    from pnj_parlant.serveur import create_app
    app = create_app(Config({"portraits": {"style": "watercolor"}, "banque": {"dossier": "pnj"}}, tmp_path),
                     moteurs=moteurs, tts=tts, reconnaissance=FausseReconnaissance(), portraits=portraits)
    client = app.test_client()
    npc_id = client.post("/api/bank", json=BROM).get_json()["id"]
    client.post(f"/api/bank/{npc_id}/portrait")
    assert portraits.prompts[-1].startswith("watercolor, ")


def test_portrait_erreurs(client, portraits):
    npc_id = client.post("/api/bank", json=BROM).get_json()["id"]
    portraits.erreur = PortraitIndisponible("Réseau coupé.")
    r = client.post(f"/api/bank/{npc_id}/portrait")
    assert r.status_code == 503 and r.get_json()["error"] == "Réseau coupé."
    portraits.actif = False
    assert client.post(f"/api/bank/{npc_id}/portrait").status_code == 400
    assert client.get("/api/config").get_json()["portraits"] is None
