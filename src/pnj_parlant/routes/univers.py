"""
L'univers de la table : scénario, apparence, lieux, export et import, exemples fournis, « Nouvelle table ».
Écritures réservées au MJ hors du PC du serveur (@mj) ; lues sans mot de passe, les notes du MJ sont retirées.

    GET|PUT /api/scenario             univers et notes du MJ
    GET|PUT /api/styles               thèmes et styles de portrait créés ou modifiés pour l'univers
    GET|PUT /api/lieux                lieux du scénario
    GET  /api/scenario/export         scénario complet (scénario, lieux, PNJ) en zip
    POST /api/scenario/import         copie un scénario dans la banque (zip ou fichiers JSON d'un dossier)
    DELETE /api/univers               nouvelle table : supprime scénario, lieux et PNJ
    GET  /api/exemples, POST /api/exemples/<id>   univers d'exemple fournis : liste, chargement dans la banque
"""
import io
import json
import time
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from ..banque import IMPORT_MAX_FICHIERS, IMPORT_MAX_OCTETS, NPC_ID, lire_zip, nom_de_fichier
from .acces import est_mj, mj
from .entrees import contexte, corps, erreur, masquer

EXEMPLES = Path(__file__).parent.parent / "exemples"  # un dossier par univers d'exemple, au format de la banque
INFOS = "_infos.json"                                 # {nom, resume} : présentation de l'exemple, jamais importée

bp = Blueprint("univers", __name__)


def exemples(dossier=EXEMPLES):
    """[{id, nom, resume}] des univers d'exemple fournis avec l'application."""
    liste = []
    for d in sorted(p for p in dossier.iterdir() if p.is_dir()) if dossier.is_dir() else []:
        try:
            infos = json.loads((d / INFOS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            infos = {}
        liste.append({"id": d.name, "nom": infos.get("nom", d.name), "resume": infos.get("resume", "")})
    return liste


@bp.get("/api/scenario")
def scenario_get():
    scenario = contexte().banque.scenario()
    return jsonify(scenario if est_mj() else masquer(scenario, "notes_mj"))


@bp.put("/api/scenario")
@mj
def scenario_put():
    """Remplace le scénario ; `notes_mj` absent (page chargée sans mot de passe) = notes gardées."""
    banque = contexte().banque
    data = corps()
    if "notes_mj" not in data:
        data = {**data, "notes_mj": banque.scenario()["notes_mj"]}
    return jsonify(banque.enregistrer_scenario(data))


@bp.get("/api/styles")
def styles_get():
    return jsonify(contexte().styles())


@bp.put("/api/styles")
@mj
def styles_put():
    """Remplace les thèmes et styles de l'univers : {themes: {id: ...}, portraits: {id: ...}}."""
    ctx = contexte()
    try:
        ctx.banque.enregistrer_styles(request.get_json(silent=True))
    except ValueError as e:
        return erreur(str(e), 400)
    return jsonify(ctx.styles())


@bp.get("/api/scenario/export")
@mj
def scenario_export():
    nom = time.strftime("scenario-%Y-%m-%d-%Hh%M.zip")
    return send_file(io.BytesIO(contexte().banque.exporter_zip()), mimetype="application/zip",
                     as_attachment=True, download_name=nom)


@bp.post("/api/scenario/import")
@mj
def scenario_import():
    """Champ « fichiers » : une archive zip, ou les fichiers .json d'un dossier ; « remplacer » : "0" pour
    garder les PNJ actuels (voir Banque.importer)."""
    fichiers = {}
    envoyes = request.files.getlist("fichiers")
    if len(envoyes) > IMPORT_MAX_FICHIERS:
        return erreur(f"Trop de fichiers pour un scénario ({IMPORT_MAX_FICHIERS} au plus).", 413)
    try:
        for f in envoyes:
            octets = f.read(IMPORT_MAX_OCTETS + 1)
            if len(octets) > IMPORT_MAX_OCTETS:
                return erreur(f"« {f.filename} » est trop volumineux pour un scénario.", 413)
            if (f.filename or "").lower().endswith(".zip"):
                fichiers.update(lire_zip(octets))
            else:
                fichiers[nom_de_fichier(f.filename)] = octets
            # cumul (zip décompressés compris) et nombre, sur tous les fichiers envoyés
            if len(fichiers) > IMPORT_MAX_FICHIERS or sum(map(len, fichiers.values())) > IMPORT_MAX_OCTETS:
                return erreur("Scénario trop volumineux : trop de fichiers ou de données au total.", 413)
        return jsonify(contexte().banque.importer(fichiers, remplacer=request.form.get("remplacer", "1") != "0"))
    except ValueError as e:
        return erreur(str(e), 400)


@bp.delete("/api/univers")
@mj
def univers_vider():
    """Nouvelle table : supprime le scénario, les lieux et tous les PNJ de la banque."""
    return jsonify({"pnj": contexte().banque.vider()})


@bp.get("/api/exemples")
def exemples_liste():
    return jsonify(exemples())


@bp.post("/api/exemples/<exemple_id>")
@mj
def exemple_charger(exemple_id):
    """Copie l'univers d'exemple dans la banque ; {remplacer: false} garde les PNJ actuels."""
    dossier = EXEMPLES / exemple_id
    if not NPC_ID.fullmatch(exemple_id) or not dossier.is_dir():
        return erreur("Exemple introuvable.", 404)
    fichiers = {f.name: f.read_bytes() for f in dossier.glob("*.json") if f.name != INFOS}
    remplacer = corps().get("remplacer", True)
    return jsonify(contexte().banque.importer(fichiers, remplacer=remplacer))


@bp.get("/api/lieux")
def lieux_get():
    lieux = contexte().banque.lieux()
    return jsonify(lieux if est_mj() else [masquer(lieu, "notes_mj") for lieu in lieux])


@bp.put("/api/lieux")
@mj
def lieux_put():
    """Remplace la liste des lieux : [{id (absent pour un nouveau lieu), nom, description, notes_mj}] ;
    `notes_mj` absent d'un lieu existant (page chargée sans mot de passe) = ses notes gardées."""
    banque = contexte().banque
    notes = {lieu["id"]: lieu.get("notes_mj", "") for lieu in banque.lieux()}
    liste = [{**lieu, "notes_mj": notes.get(lieu.get("id"), "") if isinstance(lieu.get("id"), str) else ""}
             if isinstance(lieu, dict) and "notes_mj" not in lieu else lieu for lieu in corps(list)]
    return jsonify(banque.enregistrer_lieux(liste))
