"""
Réglages du serveur modifiables depuis la page Options, sans ouvrir config.toml.

CATALOGUE décrit les réglages utiles (moteurs, Claude, Ollama, LM Studio, dialogue, voix, reconnaissance,
portraits, serveur) : clé de config.toml, type, choix ou bornes, valeur par défaut, aide. Les autres réglages
(genres des voix Piper, dossiers, max_tokens…) restent dans le fichier.

Une modification est vérifiée (`valider`), écrite dans config.toml en gardant ses commentaires et sa mise en forme
(`ecrire`, avec tomlkit), puis appliquée au serveur sans redémarrage, sauf pour les réglages marqués
`redemarrage` (port, HTTPS). Elle demande le mot de passe du MJ ([serveur] mot_de_passe_mj) ; sans mot de passe,
seulement depuis le PC du serveur. Les secrets (clé API, mot de passe) ne sont jamais renvoyés au navigateur.
"""
import copy
import hmac
import math
import os
import tempfile
import threading
import time
from pathlib import Path

MOTEURS = [["claude", "Claude (API Anthropic, réseau)"], ["local", "Ollama (local)"],
           ["lmstudio", "LM Studio (local)"]]
EFFORTS = [[e, e] for e in ("low", "medium", "high", "xhigh", "max")]


def R(cle, libelle, type_, defaut, aide="", **options):
    """Un réglage du catalogue. type_ : choix, texte, url, entier, nombre, booleen, secret."""
    return {"cle": cle, "libelle": libelle, "type": type_, "defaut": defaut, "aide": aide, **options}


# si : le groupe ne sert que si l'un des moteurs de langage vaut cette valeur (affiché en retrait sinon)
CATALOGUE = [
    {"id": "moteurs", "titre": "Moteurs de langage",
     "aide": "Qui invente les PNJ et qui les fait parler. Création avec le réseau, dialogue local pour jouer sans.",
     "reglages": [
         R("moteurs.creation", "Création des PNJ", "choix", "local", choix=MOTEURS),
         R("moteurs.dialogue", "Dialogues", "choix", "local", choix=MOTEURS),
     ]},
    {"id": "claude", "titre": "Claude", "si": "claude",
     "aide": "API Anthropic : la clé se crée sur console.anthropic.com.",
     "reglages": [
         R("claude.cle_api", "Clé API", "secret", "",
           "Vide : la variable d'environnement ANTHROPIC_API_KEY est utilisée."),
         R("claude.modele", "Modèle", "texte", "claude-haiku-5-5", "Haiku : rapide et économique.",
           suggestions=["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]),
         R("claude.generation.effort", "Effort à la création", "choix", "low", choix=EFFORTS),
         R("claude.dialogue.effort", "Effort au dialogue", "choix", "low", choix=EFFORTS,
           aide="« low » garde les répliques rapides."),
     ]},
    {"id": "local", "titre": "Ollama", "si": "local",
     "aide": "Modèle local servi par Ollama (Docker ou application Windows).",
     "reglages": [
         R("local.url", "Adresse", "url", "http://localhost:11434"),
         R("local.modele", "Modèle", "texte", "qwen3:8b",
           "Téléchargé avec « ollama pull » ; la liste propose ceux déjà installés."),
         R("local.reflexion", "Mode réflexion", "booleen", False,
           "Désactivé : bien plus rapide (Qwen 3 lirait sinon son raisonnement)."),
         R("local.contexte", "Contexte (tokens)", "entier", 8192, "2048 suffit sur une carte de 4 Go.",
           min=1024, max=131072, pas=1024),
         R("local.temperature", "Température", "nombre", 0.8, "Plus haut : plus d'imprévu.", min=0, max=2, pas=0.1),
     ]},
    {"id": "lmstudio", "titre": "LM Studio", "si": "lmstudio",
     "aide": "Modèle local servi par LM Studio (onglet Developer, Start Server).",
     "reglages": [
         R("lmstudio.url", "Adresse", "url", "http://localhost:1234"),
         R("lmstudio.modele", "Modèle", "texte", "", "Vide : le modèle chargé dans LM Studio."),
         R("lmstudio.reflexion", "Mode réflexion", "booleen", False, "Désactivé : bien plus rapide."),
         R("lmstudio.temperature", "Température", "nombre", 0.8, min=0, max=2, pas=0.1),
     ]},
    {"id": "dialogue", "titre": "Dialogue",
     "reglages": [
         R("dialogue.historique", "Messages gardés", "entier", 12,
           "Ce que le PNJ se rappelle de la conversation ; plus = plus lent.", min=2, max=60),
         R("dialogue.phrases_max", "Phrases par réplique", "entier", 3, "Longueur « Normale ».", min=1, max=10),
         R("dialogue.pnj_max", "PNJ en scène au plus", "entier", 3,
           "Le PNJ qui parle compris. Au-delà de 3, les petits modèles locaux suivent mal une scène chargée : "
           "réponses plus lentes, PNJ qui se confondent.", min=1, max=6),
         R("dialogue.intervention", "Interventions spontanées", "nombre", 0.3,
           "À plusieurs PNJ : chance qu'un autre réagisse de lui-même (0 à 1).", min=0, max=1, pas=0.05),
     ]},
    {"id": "voix", "titre": "Voix",
     "reglages": [
         R("voix.moteur", "Synthèse vocale", "choix", "piper",
           "Changer de moteur donne une autre voix aux PNJ.",
           choix=[["pocket", "Pocket TTS (local, naturel)"], ["piper", "Piper (local, léger)"],
                  ["edge", "Edge (réseau, le plus naturel)"]]),
     ]},
    {"id": "reconnaissance", "titre": "Reconnaissance vocale",
     "reglages": [
         R("reconnaissance.moteur", "Reconnaissance", "choix", "navigateur",
           choix=[["local", "Sur ce PC (faster-whisper, sans réseau)"],
                  ["navigateur", "Navigateur (Chrome / Edge, réseau)"]]),
         R("reconnaissance.modele", "Modèle Whisper", "choix", "small",
           "Doit être téléchargé dans modeles-stt (voir README).",
           choix=[[m, m] for m in ("tiny", "base", "small", "medium", "large-v3-turbo")]),
         R("reconnaissance.appareil", "Calcul", "choix", "cpu",
           choix=[["cpu", "Processeur"], ["cuda", "Carte NVIDIA (CUDA 12)"]]),
     ]},
    {"id": "portraits", "titre": "Portraits",
     "reglages": [
         R("portraits.moteur", "Portraits des PNJ", "choix", "aucun",
           choix=[["aucun", "Aucun"], ["local", "Sur ce PC (Stable Diffusion Turbo)"],
                  ["en_ligne", "En ligne (Pollinations)"]]),
         R("portraits.local.appareil", "Calcul (local)", "choix", "auto",
           choix=[["auto", "Automatique"], ["cuda", "Carte NVIDIA"], ["cpu", "Processeur"]]),
         R("portraits.local.etapes", "Étapes (local)", "entier", 2, "Plus = un peu plus détaillé, plus lent.",
           min=1, max=4),
     ]},
    {"id": "serveur", "titre": "Serveur",
     "reglages": [
         R("serveur.https", "HTTPS", "booleen", False,
           "Nécessaire pour le micro depuis un téléphone (certificat auto-signé à accepter).", redemarrage=True),
         R("serveur.port", "Port", "entier", 5000, min=1024, max=65535, redemarrage=True),
         R("serveur.mot_de_passe_mj", "Mot de passe du MJ", "secret", "",
           "Protège ces réglages, et l’univers (scénario, lieux, PNJ, import) depuis un autre appareil ; sans lui, "
           "ils ne se modifient que depuis le PC du serveur."),
     ]},
]
REGLAGES = {r["cle"]: r for g in CATALOGUE for r in g["reglages"]}


def lire(reglages, cle):
    """Valeur de `cle` (« claude.dialogue.effort ») dans les réglages, sinon la valeur par défaut du catalogue."""
    valeur = reglages
    for partie in cle.split("."):
        if not isinstance(valeur, dict) or partie not in valeur:
            return REGLAGES[cle]["defaut"]
        valeur = valeur[partie]
    return valeur


def poser(reglages, cle, valeur):
    """Pose `valeur` à `cle` dans un dictionnaire de réglages (sections créées au besoin)."""
    *sections, nom = cle.split(".")
    for partie in sections:
        reglages = reglages.setdefault(partie, {})
    reglages[nom] = valeur


def pour_la_page(reglages, suggestions=None):
    """Catalogue avec les valeurs actuelles, pour la page Options. Secrets : seulement « defini »."""
    groupes = copy.deepcopy(CATALOGUE)
    for g in groupes:
        for r in g["reglages"]:
            valeur = lire(reglages, r["cle"])
            if r["type"] == "secret":
                r["valeur"], r["defini"] = "", bool(valeur)
            else:
                r["valeur"] = valeur
            if suggestions and r["cle"] in suggestions:
                r["suggestions"] = list(dict.fromkeys([*suggestions[r["cle"]], *r.get("suggestions", [])]))
    return groupes


def valider(changements):
    """{clé: valeur} vérifiés et convertis ; lève ValueError (message pour l'utilisateur).
    Secret : une chaîne non vide le remplace, None l'efface ; une chaîne vide est ignorée (inchangé)."""
    if not isinstance(changements, dict) or not changements:
        raise ValueError("Aucun réglage à enregistrer.")
    propres = {}
    for cle, valeur in changements.items():
        r = REGLAGES.get(cle)
        if r is None:
            raise ValueError(f"Réglage inconnu : {cle}.")
        nom, t = r["libelle"], r["type"]
        if t == "secret":
            if valeur is None:
                propres[cle] = ""
            elif isinstance(valeur, str) and valeur.strip():
                propres[cle] = valeur.strip()[:300]
            continue
        if t == "booleen":
            if not isinstance(valeur, bool):
                raise ValueError(f"{nom} : oui ou non.")
        elif t == "choix":
            if valeur not in [c[0] for c in r["choix"]]:
                raise ValueError(f"{nom} : valeur inconnue.")
        elif t in ("entier", "nombre"):
            if isinstance(valeur, bool):
                raise ValueError(f"{nom} : un nombre est attendu.")
            try:
                if isinstance(valeur, str) and not valeur.strip():
                    raise ValueError("vide")
                if not math.isfinite(float(valeur)):
                    raise ValueError("NaN ou infini")
                valeur = int(valeur) if t == "entier" and float(valeur) == int(float(valeur)) else float(valeur)
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f"{nom} : un nombre est attendu.") from None
            if t == "entier" and not isinstance(valeur, int):
                raise ValueError(f"{nom} : un nombre entier est attendu.")
            if valeur < r.get("min", float("-inf")) or valeur > r.get("max", float("inf")):
                raise ValueError(f"{nom} : entre {r['min']} et {r['max']}.")
        else:  # texte, url
            if valeur is not None and not isinstance(valeur, str):
                raise ValueError(f"{nom} : un texte est attendu.")
            valeur = " ".join((valeur or "").split())[:200]
            if t == "url" and not valeur.startswith(("http://", "https://")):
                raise ValueError(f"{nom} : une adresse commençant par http:// ou https:// est attendue.")
        propres[cle] = valeur
    return propres


def ecrire(fichier, changements):
    """Écrit les changements dans config.toml en gardant commentaires et mise en forme (remplacement atomique)."""
    try:
        import tomlkit  # pylint: disable=import-outside-toplevel
    except ImportError as e:
        raise ValueError("Paquet tomlkit absent : mettez l'environnement à jour (uv sync --extra tout).") from e
    fichier = Path(fichier)
    doc = tomlkit.parse(fichier.read_text(encoding="utf-8"))
    for cle, valeur in changements.items():
        *sections, nom = cle.split(".")
        table = doc
        for partie in sections:
            if partie not in table:
                table[partie] = tomlkit.table()
            table = table[partie]
        table[nom] = valeur
    fd, tmp = tempfile.mkstemp(dir=fichier.parent, prefix=".config-", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(tomlkit.dumps(doc))
        os.replace(tmp, fichier)
    finally:  # échec (config.toml ouvert dans un éditeur) : la copie, qui contient la clé API, ne reste pas
        if os.path.exists(tmp):
            os.unlink(tmp)


def autorise(reglages, mot_de_passe, local):
    """Modification permise : avec le bon mot de passe du MJ s'il y en a un, sinon depuis le PC du serveur."""
    attendu = str(lire(reglages, "serveur.mot_de_passe_mj") or "")
    if attendu:
        return hmac.compare_digest(str(mot_de_passe or "").encode(), attendu.encode())
    return local


class Frein:
    """Frein aux essais de mot de passe, par adresse : le serveur répond à plusieurs requêtes à la fois, une pause
    par requête ne suffit donc pas. Après SEUIL échecs, chaque nouvel échec verrouille l'adresse pendant un délai
    qui double (5 s, 10 s, 20 s… jusqu'à 5 min) ; pendant le verrou, aucun mot de passe n'est même comparé.
    Un succès efface le compte ; une adresse oubliée depuis une heure aussi."""
    SEUIL, DELAI, DELAI_MAX, OUBLI = 5, 5, 300, 3600

    def __init__(self, horloge=time.monotonic):
        self.horloge = horloge
        self.essais = {}  # adresse → {echecs, jusqua (fin du verrou), dernier (dernier échec)}
        self.verrou = threading.Lock()

    def attente(self, adresse):
        """Secondes de verrou restantes pour cette adresse (0 si elle peut essayer)."""
        with self.verrou:
            e = self.essais.get(adresse)
            return max(0.0, e["jusqua"] - self.horloge()) if e else 0.0

    def echec(self, adresse):
        with self.verrou:
            maintenant = self.horloge()
            self.essais = {a: e for a, e in self.essais.items() if maintenant - e["dernier"] < self.OUBLI}
            e = self.essais.setdefault(adresse, {"echecs": 0, "jusqua": 0.0, "dernier": maintenant})
            e["echecs"] += 1
            e["dernier"] = maintenant
            if e["echecs"] >= self.SEUIL:
                rang = min(e["echecs"] - self.SEUIL, 10)
                e["jusqua"] = maintenant + min(self.DELAI_MAX, self.DELAI * 2 ** rang)

    def succes(self, adresse):
        with self.verrou:
            self.essais.pop(adresse, None)


def a_redemarrer(changements, avant):
    """Libellés des réglages changés qui ne prennent effet qu'au redémarrage du serveur."""
    return [REGLAGES[c]["libelle"] for c, v in changements.items()
            if REGLAGES[c].get("redemarrage") and lire(avant, c) != v]
