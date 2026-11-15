"""
Banque de PNJ. Écritures réservées au MJ hors du PC du serveur (@mj) ; lue sans mot de passe, une fiche n'a pas
de `secret`, et une fiche renvoyée sans `secret` garde celui de la banque.

    GET|POST /api/bank, GET|PUT|DELETE /api/bank/<id>   banque de PNJ
"""
from flask import Blueprint, jsonify

from .. import voix
from .acces import est_mj, mj
from .entrees import contexte, corps, erreur, masquer

bp = Blueprint("pnj", __name__)


def fiche_complete(npc):
    return all(isinstance(npc.get(c), str) and npc[c].strip() for c in ("nom", "salutation"))


@bp.get("/api/bank")
def bank_list():
    return jsonify(contexte().banque.liste())


@bp.get("/api/bank/<npc_id>")
def bank_get(npc_id):
    ctx = contexte()
    npc = ctx.banque.lire(npc_id)
    if npc is None:
        return erreur("PNJ introuvable.", 404)
    npc = voix.verifier(ctx.tts, npc)
    return jsonify(npc if est_mj() else masquer(npc, "secret"))


@bp.post("/api/bank")
@mj
def bank_save():
    npc = corps()
    if not fiche_complete(npc):
        return erreur("Fiche de PNJ incomplète.", 400)
    return jsonify({"id": contexte().enregistrer_pnj(npc)})


@bp.put("/api/bank/<npc_id>")
@mj
def bank_update(npc_id):
    """Remplace la fiche ; `secret` absent (fiche lue sans mot de passe) = secret de la banque gardé."""
    ctx = contexte()
    npc = corps()
    enregistree = ctx.banque.lire(npc_id)
    if enregistree is None:
        return erreur("PNJ introuvable.", 404)
    if not fiche_complete(npc):
        return erreur("Fiche de PNJ incomplète.", 400)
    if "secret" not in npc:
        npc = {**npc, "secret": enregistree.get("secret", "")}
    return jsonify({"id": ctx.enregistrer_pnj(npc, npc_id)})


@bp.delete("/api/bank/<npc_id>")
@mj
def bank_delete(npc_id):
    if not contexte().banque.supprimer(npc_id):
        return erreur("PNJ introuvable.", 404)
    return jsonify({"ok": True})
