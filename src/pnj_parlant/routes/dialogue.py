"""
Création d'un PNJ et répliques des PNJ (ouvertes à tous les appareils : c'est la partie).

    POST /api/npc/generate            crée une fiche de PNJ {role, nom, genre, consignes, lieu}
    POST /api/npc/talk                réplique d'un PNJ {npc, presents, history, lieu} (NDJSON, phrase par phrase)
"""
import json
import logging

from flask import Blueprint, Response, jsonify

from .. import dialogue
from ..moteurs import MoteurIndisponible
from .entrees import chaine, contexte, corps, erreur, fiche_recue

log = logging.getLogger("pnj_parlant.serveur")  # même nom qu'avant le découpage en Blueprints
bp = Blueprint("dialogue", __name__)


@bp.post("/api/npc/generate")
def generate_npc():
    d = corps()
    try:
        return jsonify(contexte().creer_pnj(chaine(d.get("role")), chaine(d.get("nom")), chaine(d.get("genre")),
                                            chaine(d.get("consignes")), chaine(d.get("lieu"))))
    except ValueError:
        return erreur("Le modèle n'a pas renvoyé de JSON valide. Relancez la génération.", 502)
    except MoteurIndisponible as e:
        return erreur(f"{e} Choisissez un PNJ dans la banque.", 503)


@bp.post("/api/npc/talk")
def talk():
    """Réplique de `npc` dans la scène `history` (voir le module dialogue), en NDJSON :
    une ligne {"phrase": ...} par phrase prête à être lue, ou {"error": ...}."""
    ctx = contexte()
    data = corps()
    npc = data.get("npc") or {}
    if not isinstance(npc, dict):
        return erreur("Requête invalide : « npc » doit être une fiche de PNJ.", 400)
    npc = fiche_recue(npc)
    enregistree = ctx.banque.lire(npc.get("id"))  # PNJ de la banque : son secret, que le navigateur n'a pas
    if enregistree is not None:
        npc["secret"] = chaine(enregistree.get("secret"))
    autres = data.get("presents") if isinstance(data.get("presents"), list) else []
    presents = [fiche_recue(p) for p in autres if isinstance(p, dict)]
    presents = [p for p in presents if p["nom"]][:ctx.pnj_max - 1]  # le PNJ qui parle compte dans la scène
    history = dialogue.nettoyer_historique(data.get("history"), ctx.historique)
    longueur = data.get("longueur", "normal")
    if not npc.get("nom") or not history:
        return erreur("Il manque le PNJ ou la question.", 400)
    if longueur not in ("short", "normal", "long"):
        return erreur("Longueur de réponse inconnue.", 400)
    phrases_max = {"short": 1, "normal": ctx.phrases_max,
                   "long": max(ctx.phrases_max * 2, 6)}[longueur]
    lieux = ctx.banque.lieux()
    lieu = next((x for x in lieux if x["id"] == data.get("lieu")), None)  # lieu de la scène
    system = dialogue.consignes(npc, ctx.banque.scenario()["monde"], presents, phrases_max, lieu, lieux)
    try:
        usage = {}
        morceaux = ctx.moteurs.replique(system, dialogue.messages(npc["nom"], history, presents),
                                        dialogue.arrets(npc["nom"], presents), on_usage=usage.update,
                                        longueur=longueur)
    except MoteurIndisponible as e:
        return erreur(str(e), 503)

    def lignes():
        try:
            for phrase in dialogue.repliques(morceaux, npc["nom"], presents, phrases_max):
                yield json.dumps({"phrase": phrase}, ensure_ascii=False) + "\n"
        except MoteurIndisponible as e:
            yield json.dumps({"error": str(e)}, ensure_ascii=False) + "\n"
        except Exception:  # pylint: disable=broad-exception-caught
            log.exception("Erreur inattendue pendant la réplique")  # le flux est lancé : pas d'erreur 500 possible
            yield json.dumps({"error": "La réplique a échoué de façon inattendue."}, ensure_ascii=False) + "\n"
        if usage:
            yield json.dumps({"usage": usage}, ensure_ascii=False) + "\n"
    return Response(lignes(), mimetype="application/x-ndjson")
