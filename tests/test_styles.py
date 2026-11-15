"""Thèmes et styles de portrait créés ou modifiés pour l'univers (pnj/_styles.json, /api/styles)."""
import io
import zipfile

import pytest

from pnj_parlant.banque import COULEURS, Banque, valider_styles
from pnj_parlant.portraits import STYLE, STYLES, prompt_du_style

CLAIR = {c: "#eeeeee" for c in COULEURS} | {"ink": "#111111"}
SOMBRE = {c: "#222222" for c in COULEURS} | {"ink": "#EEEEEE"}
FORGE = {"nom": "Forge", "resume": "Braises et suie", "mode": "auto", "clair": CLAIR, "sombre": SOMBRE}
AQUARELLE = {"nom": "Aquarelle", "resume": "Couleurs douces", "prompt": "watercolor painting, head and shoulders"}
STYLES_UNIVERS = {"themes": {"forge": FORGE}, "portraits": {"aquarelle": AQUARELLE,
                                                            "manga": {**AQUARELLE, "nom": "Manga doux"}}}


# --- Validation ------------------------------------------------------------------------------
def test_valider_styles():
    v = valider_styles(STYLES_UNIVERS)
    assert v["themes"]["forge"]["sombre"]["ink"] == "#eeeeee"  # couleurs en minuscules
    assert v["portraits"]["aquarelle"] == AQUARELLE
    assert valider_styles({}) == {"themes": {}, "portraits": {}}
    nuit = valider_styles({"themes": {"nuit": {"nom": "Nuit", "mode": "sombre", "sombre": SOMBRE}}})["themes"]["nuit"]
    assert "clair" not in nuit and nuit["mode"] == "sombre"  # une seule palette, celle du mode


@pytest.mark.parametrize("donnees, message", [
    ([], "illisibles"),
    ({"themes": {"../x": FORGE}}, "Identifiant de thème"),
    ({"themes": {"forge": {**FORGE, "nom": "  "}}}, "besoin d'un nom"),
    ({"themes": {"forge": {**FORGE, "mode": "gris"}}}, "mode inconnu"),
    ({"themes": {"forge": {**FORGE, "sombre": {**SOMBRE, "bg": "red"}}}}, "couleurs"),
    ({"themes": {"forge": {**FORGE, "clair": {"bg": "#ffffff"}}}}, "couleurs"),
    ({"themes": {"forge": {**FORGE, "clair": {**CLAIR, "bg": "#fff;}x{"}}}}, "couleurs"),  # pas d'injection CSS
    ({"portraits": {"aquarelle": {**AQUARELLE, "prompt": ""}}}, "description"),
    ({"themes": {f"t{i}": FORGE for i in range(31)}}, "Au plus"),
])
def test_valider_styles_refuse(donnees, message):
    with pytest.raises(ValueError, match=message):
        valider_styles(donnees)


def test_prompt_du_style():
    perso = valider_styles(STYLES_UNIVERS)["portraits"]
    assert prompt_du_style("aquarelle", perso) == AQUARELLE["prompt"]
    assert prompt_du_style("manga", perso) == AQUARELLE["prompt"]  # prédéfini modifié par l'univers
    assert prompt_du_style("photo", perso) == STYLES["photo"][2]
    assert prompt_du_style("", perso, "défaut") == "défaut"


# --- Banque ------------------------------------------------------------------------------------
@pytest.fixture
def banque(tmp_path):
    return Banque(tmp_path / "pnj")


def test_banque_styles(banque):
    assert banque.styles() == {"themes": {}, "portraits": {}}
    banque.enregistrer_styles(STYLES_UNIVERS)
    assert banque.styles()["themes"]["forge"]["nom"] == "Forge"
    banque.enregistrer_scenario({"monde": "Valmer.", "style_portrait": "aquarelle"})
    assert banque.scenario()["style_portrait"] == "aquarelle"  # style de l'univers accepté
    (banque.dossier / "_styles.json").write_text("{abîmé", encoding="utf-8")
    assert banque.styles() == {"themes": {}, "portraits": {}}
    assert banque.scenario()["style_portrait"] == ""  # style disparu : style par défaut


def test_styles_exportes_importes_et_vides(banque, tmp_path):
    banque.enregistrer_styles(STYLES_UNIVERS)
    banque.enregistrer_scenario({"monde": "Valmer.", "theme": "forge", "style_portrait": "aquarelle"})
    archive = zipfile.ZipFile(io.BytesIO(banque.exporter_zip()))
    assert "_styles.json" in archive.namelist()

    autre = Banque(tmp_path / "autre")
    autre.importer({n: archive.read(n) for n in archive.namelist()})
    assert autre.styles() == banque.styles()
    assert autre.scenario()["style_portrait"] == "aquarelle"  # styles écrits avant le scénario

    r = autre.importer({"_scenario.json": b'{"monde": "Brume"}', "_styles.json": b'{"themes": {"x": 1}}'})
    assert r["ignores"] == ["_styles.json"] and autre.styles() == {"themes": {}, "portraits": {}}  # remplacés
    banque.vider()
    assert banque.styles() == {"themes": {}, "portraits": {}}


# --- Routes ------------------------------------------------------------------------------------
def test_routes_styles(client, portraits):
    vide = client.get("/api/styles").get_json()
    assert vide["themes"] == {} and [s["origine"] for s in vide["portraits"]] == ["predefini"] * len(STYLES)
    r = client.put("/api/styles", json=STYLES_UNIVERS)
    assert r.status_code == 200
    st = r.get_json()
    assert list(st["themes"]) == ["forge"]
    origines = {s["id"]: s["origine"] for s in st["portraits"]}
    assert origines["manga"] == "modifie" and origines["aquarelle"] == "perso" and origines["photo"] == "predefini"
    assert client.put("/api/styles", json={"themes": {"x": {"nom": ""}}}).status_code == 400
    assert client.get("/api/styles").get_json() == st  # rien changé après un refus

    npc_id = client.post("/api/bank", json={"nom": "Brom", "salutation": "Salut."}).get_json()["id"]
    client.put("/api/scenario", json={"monde": "Valmer.", "style_portrait": "aquarelle"})
    client.post(f"/api/bank/{npc_id}/portrait")
    assert portraits.prompts[-1].startswith(AQUARELLE["prompt"])
    client.put("/api/styles", json={})  # style supprimé : style par défaut
    client.post(f"/api/bank/{npc_id}/portrait")
    assert portraits.prompts[-1].startswith(STYLE)
    assert "styles_portrait" not in client.get("/api/config").get_json()
