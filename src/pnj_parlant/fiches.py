"""
Création des fiches de PNJ par le modèle de langage (Claude ou local), dans le contexte du scénario.

L'humeur, le trait dominant et l'initiale du nom sont tirés au sort ici, en Python : sans cela,
les modèles inventent des PNJ qui se ressemblent tous.
"""
import json
import logging
import random
import re

from . import texte

log = logging.getLogger(__name__)

# --- Aléatoire injecté côté code (pour éviter les PNJ tous pareils) ----------
HUMEURS = ["jovial", "méfiant", "fatigué", "pressé", "mélancolique", "rusé",
           "nerveux", "bavard", "bougon", "rêveur", "obséquieux", "distrait"]
TRAITS = ["avare", "superstitieux", "vantard", "généreux", "curieux", "rancunier",
          "pieux", "joueur", "érudit", "paranoïaque", "sentimental", "philosophe"]
INITIALES = "ABCDEFGHIJKLMNOPRSTVZ"
METIERS = ["marchand de potions", "forgeron", "aubergiste", "garde de la porte nord",
           "herboriste", "cartographe", "passeur", "colporteur", "fossoyeur", "barde"]

GEN_SYSTEM = """Tu crées des personnages non-joueurs (PNJ) pour un jeu de rôle médiéval-fantastique.
Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour ni balises markdown, avec ces clés :
"nom" (prénom + surnom ou nom), "metier", "apparence" (une phrase), "personnalite" (une phrase),
"humeur",
"connaissances" (liste de 3 rumeurs ou informations utiles qu'il peut révéler),
"secret" (une chose qu'il cache), "salutation" (première réplique, 1 ou 2 phrases, à l'oral),
"genre" ("feminin", "masculin" ou "neutre" : le genre grammatical utilisé pour parler du personnage),
"timbre" ("grave", "moyen" ou "aigu"), "debit" ("lent", "normal" ou "rapide").
Évite les noms et clichés trop courants. Tout est en français.

Si un contexte de scénario est fourni, le PNJ s'y inscrit :
- ses connaissances, son secret et sa salutation ne citent que des lieux, personnages, factions,
  objets et événements présents dans le contexte ou dans les consignes du MJ ;
- n'invente aucun autre nom propre, à part le nom du PNJ lui-même ; reste vague plutôt que d'inventer ;
- les consignes du MJ priment sur tout le reste, y compris sur les suggestions d'humeur et de trait."""

# Schéma imposé à la réponse (sorties structurées) : garantit un JSON valide et complet.
_TEXTE = {"type": "string"}
NPC_SCHEMA = {
    "type": "object",
    "properties": {
        "nom": _TEXTE, "metier": _TEXTE, "apparence": _TEXTE, "personnalite": _TEXTE,
        "humeur": _TEXTE,
        "connaissances": {"type": "array", "items": _TEXTE},
        "secret": _TEXTE, "salutation": _TEXTE,
        "genre": {"type": "string", "enum": ["feminin", "masculin", "neutre"]},
        "timbre": {"type": "string", "enum": ["grave", "moyen", "aigu"]},
        "debit": {"type": "string", "enum": ["lent", "normal", "rapide"]},
    },
    "required": ["nom", "metier", "apparence", "personnalite", "humeur",
                 "connaissances", "secret", "salutation", "genre", "timbre", "debit"],
    "additionalProperties": False,
}


def parse_json(text):
    """L'objet JSON contenu dans la réponse du modèle, même entouré de texte ou de balises markdown."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def liste_des_lieux(lieux):
    """« - Forge de Brom : Une forge enfumée… », une ligne par lieu (description publique seulement)."""
    return "\n".join(f"- {l['nom']}" + (f" : {l['description']}" if l.get("description") else "") for l in lieux)


def demande(scenario, role="", nom="", genre="", consignes="", rng=random, lieu=None, lieux=()):
    """Message envoyé au modèle pour créer la fiche : univers, lieux, notes du MJ, consignes, tirages au sort.
    `lieu` : lieu habituel du PNJ (avec ses notes du MJ) ; `lieux` : tous les lieux du scénario."""
    parts = []
    if scenario.get("monde"):
        parts.append(f"<univers>\n{scenario['monde']}\n</univers>")
    if lieux:
        parts.append(f"<lieux>\n{liste_des_lieux(lieux)}\n</lieux>")
    if scenario.get("notes_mj"):
        parts.append(f"<notes_du_mj>\n{scenario['notes_mj']}\n</notes_du_mj>")
    if lieu:
        details = [lieu["nom"]]
        if lieu.get("description"):
            details.append(lieu["description"])
        if lieu.get("notes_mj"):
            details.append(f"Notes du MJ sur ce lieu : {lieu['notes_mj']}")
        parts.append("<lieu_du_pnj>\n" + "\n".join(details) + "\n</lieu_du_pnj>\n"
                     "Le PNJ vit ou travaille habituellement dans ce lieu.")
    if consignes.strip():
        parts.append(f"<consignes_pour_ce_pnj>\n{consignes.strip()[:4000]}\n</consignes_pour_ce_pnj>")
    if role.strip():
        lignes = [f"Métier : {role.strip()[:80]}."]
    elif consignes.strip():  # ex. PNJ qui entre en cours de discussion : métier déjà évoqué dans la scène
        lignes = [f"Métier : celui qu'indiquent les consignes, sinon {rng.choice(METIERS)}."]
    else:
        lignes = [f"Métier : {rng.choice(METIERS)}."]
    lettre = rng.choice(INITIALES)
    if nom.strip():
        lignes.append(f"Nom imposé : {nom.strip()[:80]}.")
    elif consignes.strip():
        lignes.append(f"Si les consignes donnent son nom, garde-le ; sinon, le nom commence par la lettre {lettre}.")
    else:
        lignes.append(f"Le nom commence par la lettre {lettre}.")
    if genre in ("feminin", "masculin", "neutre"):
        lignes.append(f"Genre : {genre}.")
    lignes.append(f"Suggestions : humeur {rng.choice(HUMEURS)}, trait dominant {rng.choice(TRAITS)}.")
    parts.append(" ".join(lignes))
    return "\n\n".join(parts)


def creer(moteurs, scenario, role="", nom="", genre="", consignes="", lieu=None, lieux=()):
    """Fait inventer un PNJ par le moteur de création. Renvoie la fiche, sans voix (voir voix.attribuer),
    rattachée à `lieu` s'il est donné. Lève ValueError si la fiche reçue est invalide,
    MoteurIndisponible si le moteur ne répond pas."""
    texte_demande = demande(scenario, role, nom, genre, consignes, lieu=lieu, lieux=lieux)
    reponse = moteurs.fiche(GEN_SYSTEM, texte_demande, NPC_SCHEMA)
    try:
        npc = parse_json(reponse)
    except (ValueError, IndexError) as e:
        log.warning("JSON PNJ invalide : %r", reponse[:500])
        raise ValueError("fiche invalide") from e
    npc["salutation"] = texte.nettoyer(npc.get("salutation") or "Bonjour, voyageur.")
    if lieu:
        npc["lieu"] = lieu["id"]
    return npc
