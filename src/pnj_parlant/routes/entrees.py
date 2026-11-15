"""
Ce que chaque route reçoit et renvoie : contexte de l'application, corps JSON vérifié, erreurs en JSON et tailles
maximales des requêtes.
"""
from urllib.parse import unquote

from flask import current_app, jsonify, request

# Tailles maximales des requêtes (413 au-delà) : l'import (fichiers et zip, IMPORT_MAX_OCTETS au total, plus
# l'enveloppe multipart) fixe le plafond global ; /api/stt et les corps JSON ont le leur (serveur.plafond).
MARGE_MULTIPART = 1_000_000
STT_MAX_OCTETS = 5_000_000   # quelques minutes d'audio webm/opus : une question dure moins d'une minute
CORPS_MAX = 2_000_000        # JSON : scénario (20 000 caractères), 60 lieux, fiches, historique de la scène


def contexte():
    """Le `serveur.Contexte` de l'application en cours (moteurs, banque, réglages)."""
    return current_app.extensions["pnj"]


def erreur(message, code, **autres):
    """Réponse d'erreur en JSON : {error: message, ...autres}, avec le code HTTP `code`."""
    return jsonify({"error": message, **autres}), code


class EntreeInvalide(Exception):
    """Le corps de la requête n'a pas la forme attendue : réponse 400 (voir `corps`)."""


def corps(type_attendu=dict):
    """Corps JSON de la requête, du type attendu (objet ou liste) ; un corps absent ou illisible donne un objet
    ou une liste vide. Lève EntreeInvalide (réponse 400) si le JSON est d'un autre type : texte, nombre, liste…"""
    data = request.get_json(silent=True)
    if data is None:
        return type_attendu()
    if not isinstance(data, type_attendu):
        raise EntreeInvalide("Requête invalide : " + ("un objet JSON" if type_attendu is dict else "une liste JSON")
                             + " est attendu.")
    return data


def chaine(valeur):
    """Texte d'un champ reçu du navigateur : une chaîne, un nombre converti, sinon vide (null, liste, objet)."""
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return str(valeur)
    return ""


def fiche_recue(npc):
    """Fiche d'un PNJ reçue pour le dialogue, aux champs de texte garantis (une liste de chaînes pour les
    connaissances) : le navigateur est la source, pas un fichier sûr."""
    propre = dict(npc)
    for cle in ("nom", "metier", "apparence", "personnalite", "humeur", "secret"):
        propre[cle] = chaine(npc.get(cle))
    connaissances = npc.get("connaissances")
    propre["connaissances"] = [chaine(c) for c in connaissances if chaine(c)] if isinstance(connaissances, list) else []
    return propre


def masquer(donnee, *champs):
    """Copie sans les champs réservés au MJ (secret d'un PNJ, notes_mj du scénario et des lieux), pour un appareil
    sans mot de passe du MJ (décision D1). Le champ est retiré, pas vidé : renvoyé tel quel, il ne change rien."""
    return {k: v for k, v in donnee.items() if k not in champs}


def mot_de_passe_recu(valeur):
    """Mot de passe de l'en-tête X-Mot-De-Passe-MJ (encodé par le navigateur : un en-tête n'admet pas d'accents)."""
    return unquote(valeur) if valeur else valeur
