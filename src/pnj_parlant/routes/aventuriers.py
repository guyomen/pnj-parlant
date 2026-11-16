"""
Aventuriers : les personnages des joueurs (facultatifs, voir aventuriers.py). Écritures réservées au MJ hors du
PC du serveur (@mj), comme le reste de l'univers ; lus sans mot de passe (rien de secret).

    GET /api/systemes                                    systèmes de jeu (caractéristiques, compétences)
    GET|POST /api/aventuriers, GET|PUT|DELETE /api/aventuriers/<id>
    GET|POST|DELETE /api/aventuriers/<id>/portrait
"""
import io
import mimetypes
import secrets

from flask import Blueprint, jsonify, request, send_file

from ..aventuriers import jets, normaliser, systemes_pour_la_page
from ..banque import AVENTURIER
from ..portraits import PortraitIndisponible, prompt_portrait
from .acces import mj
from .entrees import contexte, corps, erreur

bp = Blueprint("aventuriers", __name__)


def avec_jets(av):
    """Fiche lue, avec les jets qu'il peut tenter (bonus calculés ici : le navigateur ne fait que lancer le dé)."""
    return {**av, "jets": jets(av)}


def fiche_recue():
    av = normaliser(corps())
    if not av["nom"]:
        raise ValueError("Il faut au moins un nom à l'aventurier.")
    return av


@bp.get("/api/systemes")
def systemes():
    return jsonify(systemes_pour_la_page())


@bp.get("/api/aventuriers")
def aventuriers_liste():
    return jsonify([avec_jets(a) for a in contexte().banque.aventuriers()])


@bp.get("/api/aventuriers/<av_id>")
def aventurier_lire(av_id):
    av = contexte().banque.lire_aventurier(av_id)
    return jsonify(avec_jets(av)) if av else erreur("Aventurier introuvable.", 404)


@bp.post("/api/aventuriers")
@mj
def aventurier_ajouter():
    try:
        return jsonify({"id": contexte().banque.ajouter_aventurier(fiche_recue())})
    except ValueError as e:
        return erreur(str(e), 400)


@bp.put("/api/aventuriers/<av_id>")
@mj
def aventurier_modifier(av_id):
    banque = contexte().banque
    if banque.lire_aventurier(av_id) is None:
        return erreur("Aventurier introuvable.", 404)
    try:
        return jsonify({"id": banque.ecrire_aventurier(av_id, fiche_recue())})
    except ValueError as e:
        return erreur(str(e), 400)


@bp.delete("/api/aventuriers/<av_id>")
@mj
def aventurier_supprimer(av_id):
    if not contexte().banque.supprimer_aventurier(av_id):
        return erreur("Aventurier introuvable.", 404)
    return jsonify({"ok": True})


# --- Portrait : comme celui d'un PNJ (routes/portraits.py) ------------------------------
@bp.get("/api/aventuriers/<av_id>/portrait")
def aventurier_portrait(av_id):
    chemin = contexte().banque.portrait(av_id, AVENTURIER)
    if chemin is None:
        return erreur("Pas de portrait.", 404)
    return send_file(io.BytesIO(chemin.read_bytes()), mimetype=mimetypes.guess_type(chemin.name)[0],
                     max_age=86400 if request.args.get("v") else 0)


@bp.post("/api/aventuriers/<av_id>/portrait")
@mj
def aventurier_portrait_generer(av_id):
    """Génère le portrait d'après la fiche (corps facultatif : la fiche à l'écran). Renvoie {portrait, prompt}."""
    ctx = contexte()
    av = ctx.banque.lire_aventurier(av_id)
    if av is None:
        return erreur("Aventurier introuvable.", 404)
    if not ctx.portraits.disponible():
        return erreur("Portraits désactivés : choisissez un moteur dans la page Options.", 400)
    recu = corps()
    if recu:
        av.update(normaliser({**av, **recu}))
    sujet = {"genre": av.get("genre"), "apparence": av["apparence"],
             "metier": av["classe"] or "aventurier"}  # le portrait d'un PNJ part de son métier
    prompt = prompt_portrait(ctx.moteurs, sujet, ctx.style_portrait())
    try:
        octets, ext = ctx.portraits.generer(prompt, secrets.randbelow(2**31))
    except PortraitIndisponible as e:
        return erreur(str(e), 503)
    if not ctx.banque.enregistrer_portrait(av_id, octets, ext, AVENTURIER):
        return erreur("Aventurier introuvable.", 404)
    return jsonify({"portrait": ctx.banque.version_portrait(av_id, AVENTURIER), "prompt": prompt})


@bp.delete("/api/aventuriers/<av_id>/portrait")
@mj
def aventurier_portrait_supprimer(av_id):
    if not contexte().banque.supprimer_portrait(av_id, AVENTURIER):
        return erreur("Pas de portrait.", 404)
    return jsonify({"ok": True})
