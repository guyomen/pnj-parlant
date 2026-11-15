"""
Portraits des PNJ de la banque (facultatifs : moteur de [portraits] dans config.toml).

    GET|POST|DELETE /api/bank/<id>/portrait   portrait du PNJ : image, génération, retrait
"""
import io
import mimetypes
import secrets

from flask import Blueprint, jsonify, request, send_file

from ..portraits import PortraitIndisponible, prompt_portrait
from .acces import mj
from .entrees import contexte, corps, erreur

bp = Blueprint("portraits", __name__)


@bp.get("/api/bank/<npc_id>/portrait")
def portrait_get(npc_id):
    chemin = contexte().banque.portrait(npc_id)
    if chemin is None:
        return erreur("Pas de portrait.", 404)
    # lu en mémoire : sous Windows, un fichier encore ouvert ne pourrait être ni refait ni supprimé.
    # Adresse avec ?v=<version> (champ « portrait » de la fiche) : gardée en cache, elle change avec l'image.
    return send_file(io.BytesIO(chemin.read_bytes()), mimetype=mimetypes.guess_type(chemin.name)[0],
                     max_age=86400 if request.args.get("v") else 0)


@bp.post("/api/bank/<npc_id>/portrait")
@mj
def portrait_generer(npc_id):
    """Génère et enregistre le portrait d'un PNJ de la banque. Corps facultatif : la fiche en cours
    d'édition (apparence modifiée mais pas encore enregistrée). Renvoie {portrait: version, prompt}."""
    ctx = contexte()
    npc = ctx.banque.lire(npc_id)
    if npc is None:
        return erreur("PNJ introuvable.", 404)
    if not ctx.portraits.disponible():
        return erreur("Portraits désactivés : choisissez un moteur dans la page Options.", 400)
    npc.update(corps())
    prompt = prompt_portrait(ctx.moteurs, npc, ctx.style_portrait())
    try:
        octets, ext = ctx.portraits.generer(prompt, secrets.randbelow(2**31))
    except PortraitIndisponible as e:
        return erreur(str(e), 503)
    if not ctx.banque.enregistrer_portrait(npc_id, octets, ext):  # supprimé pendant la génération
        return erreur("PNJ introuvable.", 404)
    return jsonify({"portrait": ctx.banque.version_portrait(npc_id), "prompt": prompt})


@bp.delete("/api/bank/<npc_id>/portrait")
@mj
def portrait_supprimer(npc_id):
    if not contexte().banque.supprimer_portrait(npc_id):
        return erreur("Pas de portrait.", 404)
    return jsonify({"ok": True})
