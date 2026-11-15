"""
Mot de passe du MJ : réglages du serveur (page Options) et univers (décision D1).

Depuis le PC du serveur, l'univers se modifie librement ; ailleurs, toute écriture (@mj) demande le mot de passe
du MJ dans l'en-tête X-Mot-De-Passe-MJ, et les lectures retirent les secrets des PNJ et les notes du MJ (`est_mj`).
Les réglages exigent le mot de passe même sur le PC s'il existe. Un mauvais mot de passe compte dans le frein
(`Contexte.frein`) et attend une seconde.
"""
import functools
import math
import time

from flask import request

from .. import reglages
from .entrees import contexte, erreur, mot_de_passe_recu

EN_TETE_MDP = "X-Mot-De-Passe-MJ"  # mot de passe du MJ, encodé par encodeURIComponent (js/api.js)


def depuis_le_serveur():
    return request.remote_addr in ("127.0.0.1", "::1")


def protege():
    return bool(reglages.lire(contexte().cfg.reglages, "serveur.mot_de_passe_mj"))


def mdp_en_tete():
    return mot_de_passe_recu(request.headers.get(EN_TETE_MDP))


def droits(mdp, univers):
    """(état, attente) : "ok", "verrou" (adresse freinée : `attente` secondes) ou "refus". `univers` : routes
    du scénario, des lieux, des PNJ… où le PC du serveur passe toujours (D1) ; sinon (réglages), le mot de
    passe est exigé même sur le PC s'il existe. Un mauvais mot de passe compte dans le frein (ctx.frein)."""
    ctx = contexte()
    local = depuis_le_serveur()
    if univers and local:
        return "ok", 0
    adresse = request.remote_addr or ""
    attente = ctx.frein.attente(adresse)
    if attente:
        return "verrou", attente
    if reglages.autorise(ctx.cfg.reglages, mdp, local):
        if protege():
            ctx.frein.succes(adresse)
        return "ok", 0
    if protege() and mdp:
        ctx.frein.echec(adresse)
    return "refus", 0


def est_mj():
    """Cet appareil voit les secrets des PNJ et les notes du MJ (PC du serveur, ou bon mot de passe)."""
    return droits(mdp_en_tete(), True)[0] == "ok"


def garde(mdp, univers, demander=False):
    """None si la requête est permise, sinon la réponse de refus (403, ou 429 pendant un verrou).
    `demander` : voir refus."""
    etat, attente = droits(mdp, univers)
    if etat == "ok":
        return None
    if etat == "verrou":
        return trop_d_essais(attente)
    return refus(mdp, univers, demander)


def trop_d_essais(attente):
    return erreur(f"Trop d’essais de mot de passe : réessayez dans {math.ceil(attente)} s.", 429)


def refus(mdp, univers=False, demander=False):
    """Réponse 403 ; un mauvais mot de passe attend aussi une seconde. Pour l'univers (et les réglages avec
    `demander` : PUT /api/reglages, utilisé par la vue Partie), `mot_de_passe` dit à la page qu'elle peut le
    demander (js/api.js). La page Options vérifie le mot de passe par son propre formulaire : sans `demander`."""
    if mdp:
        time.sleep(1)
    if protege():
        if not univers and demander:
            message = ("Mot de passe du MJ incorrect." if mdp else
                       "Mot de passe du MJ demandé pour modifier les réglages du serveur.")
            return erreur(message, 403, mot_de_passe=True)
        if not univers:
            return erreur("Mot de passe du MJ incorrect.", 403)
        message = ("Mot de passe du MJ incorrect." if mdp else
                   "Mot de passe du MJ demandé : depuis cet appareil, l’univers ne se modifie qu’avec lui.")
        return erreur(message, 403, mot_de_passe=True)
    if univers:
        return erreur("L’univers ne se modifie que depuis le PC du serveur (ou définissez un mot de passe du MJ "
                      "dans les options, sur ce PC, pour le modifier depuis un autre appareil).", 403)
    return erreur("Ces réglages ne se modifient que depuis le PC du serveur (ou définissez un mot de passe "
                  "du MJ pour les modifier depuis un autre appareil).", 403)


def mj(vue):
    """Route d'écriture de l'univers : libre depuis le PC du serveur, mot de passe du MJ ailleurs (D1)."""
    @functools.wraps(vue)
    def gardee(*args, **kwargs):
        return garde(mdp_en_tete(), True) or vue(*args, **kwargs)
    return gardee
