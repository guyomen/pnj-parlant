"""
Serveur Flask : page de jeu, page de préparation et API.

Lancement :  pnj-parlant            (ou python -m pnj_parlant)   puis ouvrir http://localhost:5000
Réglages :   config.toml du dossier courant (à créer à partir de config.toml.example), ou --config

Routes :
    GET  /api/config                  moteurs utilisés, voix, reconnaissance locale, modèles Ollama
    GET  /api/etat                    carte graphique et Ollama
    GET  /api/sante                   ce qui ne marche pas alors que le serveur tourne (bandeau des pages)
    GET|PUT /api/reglages             réglages du serveur de la page Options (écrits dans config.toml, à chaud)
    POST /api/reglages/verifier       vérifie le mot de passe du MJ
    GET  /api/acces                   droits de cet appareil sur l'univers {mj, protege, local}

Hors du PC du serveur, les écritures de l'univers (@mj) demandent le mot de passe du MJ (en-tête
X-Mot-De-Passe-MJ), et les secrets des PNJ et les notes du MJ sont retirés des réponses (décision D1).
    POST /api/npc/generate            crée une fiche de PNJ {role, nom, genre, consignes, lieu}
    POST /api/npc/talk                réplique d'un PNJ {npc, presents, history, lieu} (NDJSON, phrase par phrase)
    GET|PUT /api/lieux                lieux du scénario
    GET|PUT /api/scenario             univers et notes du MJ
    GET|PUT /api/styles               thèmes et styles de portrait créés ou modifiés pour l'univers
    GET  /api/scenario/export         scénario complet (scénario, lieux, PNJ) en zip
    DELETE /api/univers               nouvelle table : supprime scénario, lieux et PNJ
    POST /api/scenario/import         copie un scénario dans la banque (zip ou fichiers JSON d'un dossier)
    GET  /api/exemples, POST /api/exemples/<id>   univers d'exemple fournis : liste, chargement dans la banque
    GET|POST /api/bank, GET|PUT|DELETE /api/bank/<id>   banque de PNJ
    GET|POST|DELETE /api/bank/<id>/portrait   portrait du PNJ : image, génération (moteur de [portraits]), retrait
    POST /api/voice                   autre voix pour un PNJ ; GET /api/voices : voix du moteur
    GET|PUT /api/voice-engine         moteur de synthèse (jusqu'au redémarrage)
    POST /api/tts                     synthèse vocale {text, voice, narrateur, eviter}
    POST /api/stt                     reconnaissance vocale (audio webm/opus + indice)
"""
import argparse
import copy
import functools
import importlib.util
import io
import json
import logging
import math
import mimetypes
import os
import secrets
import signal
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from flask import Flask, Response, jsonify, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from . import config as configuration
from . import dialogue, fiches, reglages, systeme, texte, voix
from .banque import IMPORT_MAX_FICHIERS, IMPORT_MAX_OCTETS, NPC_ID, Banque, lire_zip, nom_de_fichier, normaliser_fiche
from .moteurs import MoteurIndisponible, Moteurs
from .portraits import STYLE, PortraitIndisponible, prompt_du_style, prompt_portrait, styles
from .portraits import charger as charger_portraits
from .stt import Reconnaissance

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
EXEMPLES = Path(__file__).parent / "exemples"  # un dossier par univers d'exemple, au format de la banque
INFOS = "_infos.json"                          # {nom, resume} : présentation de l'exemple, jamais importée
EN_TETE_MDP = "X-Mot-De-Passe-MJ"              # mot de passe du MJ, encodé par encodeURIComponent (js/api.js)
# Tailles maximales des requêtes (413 au-delà) : l'import (fichiers et zip, IMPORT_MAX_OCTETS au total, plus
# l'enveloppe multipart) fixe le plafond global ; /api/stt et les corps JSON ont le leur.
MARGE_MULTIPART = 1_000_000
STT_MAX_OCTETS = 5_000_000   # quelques minutes d'audio webm/opus : une question dure moins d'une minute
CORPS_MAX = 2_000_000        # JSON : scénario (20 000 caractères), 60 lieux, fiches, historique de la scène


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

# Sous Windows, le registre associe parfois .js à text/plain : le navigateur refuse alors les modules JS.
mimetypes.add_type("text/javascript", ".js")


def paquet_installe(module):
    """Vrai si le module Python peut être importé (sans l'importer : certains chargent PyTorch)."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


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


def entier_borne(valeur, defaut, minimum, maximum=None):
    """`valeur` convertie en entier et bornée ; `defaut` si elle n'est pas un nombre (config.toml édité à la main)."""
    try:
        n = int(valeur)
    except (TypeError, ValueError, OverflowError):
        n = defaut
    return max(minimum, n if maximum is None else min(maximum, n))


class Contexte:
    """Tout ce dont les routes ont besoin. Les moteurs peuvent être remplacés (tests)."""

    def __init__(self, cfg, moteurs=None, tts=None, reconnaissance=None, portraits=None):
        self.cfg = cfg
        # moteurs fournis (tests) : jamais remplacés quand les réglages changent
        self.injectes = {"moteurs": moteurs, "tts": tts, "reconnaissance": reconnaissance, "portraits": portraits}
        self.moteurs = moteurs or Moteurs(cfg.reglages)  # Claude, Ollama ou LM Studio, d'après [moteurs]
        self.tts = tts or voix.charger(cfg.reglages, cfg.racine)  # Piper, Pocket TTS ou Edge, d'après [voix]
        self.tts_charges = {self.tts.nom: self.tts}  # on ne recharge pas Pocket TTS à chaque bascule
        self.reconnaissance = reconnaissance or Reconnaissance(cfg.section("reconnaissance"), cfg.racine)
        self.portraits = portraits or charger_portraits(cfg.section("portraits"))  # aucun, local ou en_ligne
        self.banque = Banque(cfg.chemin(cfg.section("banque").get("dossier", "pnj")))
        self.verrou_reglages = threading.RLock()  # un seul changement de réglages ou de moteur de voix à la fois
        self.frein = reglages.Frein()  # essais de mot de passe du MJ, par adresse
        self.parametres()

    def parametres(self):
        """Réglages simples lus à chaque usage (dialogue, style des portraits par défaut)."""
        cfg = self.cfg
        self.style_defaut = cfg.section("portraits").get("style", STYLE)  # si le scénario n'a pas choisi de style
        section = cfg.section("dialogue")
        self.historique = entier_borne(section.get("historique", 12), 12, 2)  # messages gardés pour le contexte
        self.intervention = section.get("intervention", 0.3)
        self.phrases_max = entier_borne(section.get("phrases_max", dialogue.PHRASES_MAX), dialogue.PHRASES_MAX, 1)
        self.pnj_max = entier_borne(section.get("pnj_max", dialogue.PNJ_MAX), dialogue.PNJ_MAX, 1, 6)  # PNJ en scène

    def appliquer_reglages(self, changements):
        """Applique des réglages déjà vérifiés (reglages.valider) : écrits dans config.toml, puis pris en compte sans
        redémarrer. Ce qui peut échouer (moteur de voix inutilisable…) est essayé avant d'écrire : en cas d'erreur
        (ValueError), rien ne change. Renvoie les libellés des réglages qui attendent un redémarrage."""
        with self.verrou_reglages:  # deux PUT simultanés : fichier et mémoire reçoivent les deux, l'un après l'autre
            return self._appliquer_reglages(changements)

    def _appliquer_reglages(self, changements):
        avant, nouveaux = self.cfg.reglages, copy.deepcopy(self.cfg.reglages)
        for cle, valeur in changements.items():
            reglages.poser(nouveaux, cle, valeur)
        def change(*prefixes):
            return any(c.startswith(prefixes) and reglages.lire(avant, c) != v for c, v in changements.items())

        tts = None
        nom_tts = reglages.lire(nouveaux, "voix.moteur")
        if change("voix.") and not self.injectes["tts"] and nom_tts != self.tts.nom:
            tts = self.tts_charges.get(nom_tts) or voix.charger(nouveaux, self.cfg.racine, nom_tts)
            if not tts.catalogue():
                raise ValueError(
                    f"Le moteur de voix « {nom_tts} » n'est pas utilisable ici (paquet ou voix manquants).")
        moteurs = None
        if change("moteurs.", "claude.", "local.", "lmstudio.") and not self.injectes["moteurs"]:
            moteurs = Moteurs(nouveaux)
        if self.cfg.fichier:
            reglages.ecrire(self.cfg.fichier, changements)
        self.cfg.reglages = nouveaux
        if moteurs:
            self.moteurs = moteurs
        if tts:
            if tts.nom not in self.tts_charges:
                self.tts_charges[tts.nom] = tts
                threading.Thread(target=tts.prechauffer, daemon=True).start()
            self.tts = tts
        if change("reconnaissance.") and not self.injectes["reconnaissance"]:
            self.reconnaissance = Reconnaissance(self.cfg.section("reconnaissance"), self.cfg.racine)
            if self.reconnaissance.disponible():
                threading.Thread(target=self.reconnaissance.charger, daemon=True).start()
        if change("portraits.") and not self.injectes["portraits"]:
            self.portraits = charger_portraits(self.cfg.section("portraits"))
        self.parametres()
        return reglages.a_redemarrer(changements, avant)

    def style_portrait(self):
        """Suite du prompt des portraits : le style choisi par le scénario, sinon celui de config.toml."""
        return prompt_du_style(self.banque.scenario()["style_portrait"], self.banque.styles()["portraits"],
                               self.style_defaut)

    def problemes(self):
        """Ce qui ne marche pas alors que le serveur tourne (dépendance absente, moteur injoignable, clé manquante),
        pour le bandeau des pages : [{cle, niveau ("erreur" | "avertissement"), message}]. Un avertissement a un
        repli (voix ou reconnaissance du navigateur) ; une erreur bloque une fonction."""
        liste = []

        def signaler(cle, niveau, message):
            liste.append({"cle": cle, "niveau": niveau, "message": message})

        maj = "mettez l'environnement à jour : uv sync --extra tout"
        if not paquet_installe("tomlkit"):
            signaler("tomlkit", "erreur", f"Paquet tomlkit absent : les réglages de la page Options ne peuvent pas "
                                          f"être enregistrés ({maj}).")
        if not self.tts.catalogue():
            module = {"pocket": "pocket_tts", "piper": "piper", "edge": "edge_tts"}.get(self.tts.nom)
            cause = (f"paquet absent ({maj})" if module and not paquet_installe(module)
                     else "aucune voix utilisable (voix Piper à télécharger, ou réseau coupé pour Edge)")
            signaler("voix", "avertissement", f"Synthèse vocale « {self.tts.nom} » : {cause}. "
                                              "La voix du navigateur la remplace.")
        if self.reconnaissance.choisie and not self.reconnaissance.disponible():
            cause = (f"paquet faster-whisper absent ({maj})" if not paquet_installe("faster_whisper")
                     else f"modèle Whisper absent de {self.reconnaissance.dossier} (voir README)")
            signaler("reconnaissance", "avertissement", f"Reconnaissance vocale locale : {cause}. Celle du "
                                                        "navigateur (en ligne) la remplace.")
        if self.cfg.section("portraits").get("moteur") == "local" and not self.portraits.disponible():
            signaler("portraits", "erreur", "Portraits locaux : option portraits non installée "
                                            "(uv sync --extra tout --extra portraits).")
        choix = set(self.moteurs.choix.values())
        if "claude" in choix and not (reglages.lire(self.cfg.reglages, "claude.cle_api")
                                      or os.environ.get("ANTHROPIC_API_KEY")):
            signaler("claude", "erreur", "Clé API Claude absente : ajoutez-la dans les options (rubrique Claude) ou "
                                         "dans config.toml, ou choisissez un moteur local.")
        if "local" in choix:
            url = self.moteurs.local_cfg.get("url", "http://localhost:11434")
            if not systeme.etat_ollama(url)["ok"]:
                signaler("ollama", "erreur", f"Ollama ne répond pas ({url}) : démarrez-le (lancer.bat le fait sous "
                                             "Windows ; sous Linux : docker compose up -d).")
            else:
                modele = self.moteurs.local_cfg.get("modele", "")
                installes = self.moteurs.modeles_locaux()
                noms = [m["nom"] for m in installes]
                if modele and installes and self.moteurs.modele_local_installe(installes) not in noms:
                    signaler("ollama-modele", "erreur",
                             f"Modèle « {modele} » absent d'Ollama : téléchargez-le "
                             f"(ollama pull {modele}) ou choisissez-en un autre dans les options.")
        if "lmstudio" in choix:
            etat = self.moteurs.etat_lmstudio()
            if not etat["ok"]:
                signaler("lmstudio", "erreur", etat["message"])
        return liste

    def styles(self):
        """Pour la page : thèmes de l'univers ({id: thème}) et liste complète des styles de portrait."""
        perso = self.banque.styles()
        return {"themes": perso["themes"], "portraits": styles(perso["portraits"])}

    def changer_tts(self, nom):
        """Change de moteur de synthèse pour tout le serveur. Lève ValueError s'il est inutilisable."""
        with self.verrou_reglages:
            moteur = self.tts_charges.get(nom) or voix.charger(self.cfg.reglages, self.cfg.racine, nom)
            if not moteur.catalogue():
                raise ValueError(f"Le moteur « {nom} » n'est pas utilisable ici (paquet ou voix manquants).")
            if nom not in self.tts_charges:
                self.tts_charges[nom] = moteur
                threading.Thread(target=moteur.prechauffer, daemon=True).start()
            self.tts = moteur

    def creer_pnj(self, role="", nom="", genre="", consignes="", lieu=""):
        """Fiche d'un nouveau PNJ, avec sa voix, rattaché au lieu `lieu` (identifiant) s'il existe.
        Lève ValueError ou MoteurIndisponible."""
        npc = fiches.creer(self.moteurs, self.banque.scenario(), role, nom, genre, consignes,
                           lieu=self.banque.lieu(lieu), lieux=self.banque.lieux())
        npc["voix"] = voix.attribuer(self.tts, npc)
        return npc

    def enregistrer_pnj(self, npc, npc_id=None):
        """Ajoute le PNJ à la banque (ou le met à jour si `npc_id`) et renvoie son identifiant."""
        npc = voix.verifier(self.tts, normaliser_fiche(npc))
        npc["salutation"] = texte.nettoyer(npc.get("salutation", ""))
        if npc_id:
            self.banque.ecrire(npc_id, npc)
            return npc_id
        return self.banque.ajouter(npc)


def create_app(cfg, **moteurs):
    """Application Flask. `moteurs` : moteurs=, tts=, reconnaissance=, portraits= pour remplacer ceux de
    config.toml."""
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = IMPORT_MAX_OCTETS + MARGE_MULTIPART  # plafond global : celui de l'import
    ctx = Contexte(cfg, **moteurs)
    app.extensions["pnj"] = ctx

    def erreur(message, code, **autres):
        return jsonify({"error": message, **autres}), code

    @app.errorhandler(EntreeInvalide)
    def entree_invalide(e):
        return erreur(str(e), 400)

    @app.before_request
    def plafond():
        """Taille maximale du corps selon la route (413 au-delà, avant toute lecture en mémoire), et refus des
        écritures envoyées par une autre page web : un import multipart ou un POST sans corps ne demandent pas de
        pré-vérification CORS, et depuis le PC du serveur aucun mot de passe ne les arrêterait."""
        origine = request.headers.get("Origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origine and urlsplit(origine).netloc != request.host:
            return erreur("Requête venue d’une autre page refusée.", 403)
        if request.path == "/api/stt":
            request.max_content_length = STT_MAX_OCTETS
        elif request.path != "/api/scenario/import":
            request.max_content_length = CORPS_MAX

    @app.errorhandler(RequestEntityTooLarge)
    def trop_volumineux(e):
        return erreur("Requête trop volumineuse.", 413)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    # --- Configuration et état ----------------------------------------------------
    @app.get("/api/config")
    def config_get():
        m = ctx.moteurs
        installes = m.modeles_locaux() if "local" in m.choix.values() else []
        return jsonify({"moteurs": m.description(), "tts": ctx.tts.nom if ctx.tts.catalogue() else None,
                        "stt_local": ctx.reconnaissance.disponible(), "modeles_locaux": installes,
                        "intervention": ctx.intervention, "pnj_max": ctx.pnj_max,
                        "modele_local": m.modele_local_installe(installes),
                        "contexte_max": m.contexte_max(),
                        "portraits": ctx.portraits.nom if ctx.portraits.disponible() else None})

    @app.get("/api/etat")
    def etat():
        """État de la machine pour la page Options : GPU, et Ollama ou LM Studio s'ils servent."""
        ollama = lmstudio = None
        if "local" in ctx.moteurs.choix.values():
            ollama = systeme.etat_ollama(ctx.moteurs.local_cfg.get("url", "http://localhost:11434"))
        if "lmstudio" in ctx.moteurs.choix.values():
            lmstudio = ctx.moteurs.etat_lmstudio()
        return jsonify({"gpu": systeme.etat_gpu(), "ollama": ollama, "lmstudio": lmstudio})

    # --- Réglages du serveur (page Options) ---------------------------------------
    def depuis_le_serveur():
        return request.remote_addr in ("127.0.0.1", "::1")

    def reglages_pour_la_page():
        suggestions = {}
        if "local" in ctx.moteurs.choix.values():  # modèles installés dans Ollama (seulement s'il sert)
            suggestions["local.modele"] = [m["nom"] for m in ctx.moteurs.modeles_locaux()]
        return {"groupes": reglages.pour_la_page(ctx.cfg.reglages, suggestions),
                "protege": bool(reglages.lire(ctx.cfg.reglages, "serveur.mot_de_passe_mj")),
                "local": depuis_le_serveur(), "fichier": ctx.cfg.fichier.name if ctx.cfg.fichier else None}

    # --- Mot de passe du MJ : réglages (page Options) et univers (décision D1) ------------
    def protege():
        return bool(reglages.lire(ctx.cfg.reglages, "serveur.mot_de_passe_mj"))

    def mdp_en_tete():
        return mot_de_passe_recu(request.headers.get(EN_TETE_MDP))

    def droits(mdp, univers):
        """(état, attente) : "ok", "verrou" (adresse freinée : `attente` secondes) ou "refus". `univers` : routes
        du scénario, des lieux, des PNJ… où le PC du serveur passe toujours (D1) ; sinon (réglages), le mot de
        passe est exigé même sur le PC s'il existe. Un mauvais mot de passe compte dans le frein (ctx.frein)."""
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

    def garde(mdp, univers):
        """None si la requête est permise, sinon la réponse de refus (403, ou 429 pendant un verrou)."""
        etat, attente = droits(mdp, univers)
        if etat == "ok":
            return None
        if etat == "verrou":
            return trop_d_essais(attente)
        return refus(mdp, univers)

    def trop_d_essais(attente):
        return erreur(f"Trop d’essais de mot de passe : réessayez dans {math.ceil(attente)} s.", 429)

    def refus(mdp, univers=False):
        """Réponse 403 ; un mauvais mot de passe attend aussi une seconde. Pour l'univers, `mot_de_passe` dit à
        la page qu'elle peut le demander (js/api.js)."""
        if mdp:
            time.sleep(1)
        if protege():
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

    @app.get("/api/acces")
    def acces():
        """Droits de cet appareil sur l'univers (mot de passe éventuel dans l'en-tête) : {mj, protege, local}."""
        etat, attente = droits(mdp_en_tete(), True)
        if etat == "verrou":
            return trop_d_essais(attente)
        return jsonify({"mj": etat == "ok", "protege": protege(), "local": depuis_le_serveur()})

    @app.get("/api/sante")
    def sante():
        """Problèmes à afficher dans le bandeau des pages (vide si tout va bien)."""
        return jsonify({"problemes": ctx.problemes()})

    @app.get("/api/reglages")
    def reglages_get():
        """Réglages du serveur pour la page Options (secrets masqués) et droits de cet appareil."""
        return jsonify(reglages_pour_la_page())

    @app.post("/api/reglages/verifier")
    def reglages_verifier():
        mdp = corps().get("mot_de_passe")
        return garde(mdp if isinstance(mdp, str) else None, False) or jsonify({"ok": True})

    @app.put("/api/reglages")
    def reglages_put():
        """{changements: {clé: valeur}} ; mot de passe du MJ dans l'en-tête X-Mot-De-Passe-MJ. Écrit config.toml et
        applique aussitôt ; renvoie les réglages et `redemarrage` (libellés qui attendent un redémarrage)."""
        refuse = garde(mdp_en_tete(), False)
        if refuse:
            return refuse
        try:
            changements = corps().get("changements")
            redemarrage = ctx.appliquer_reglages(reglages.valider(changements))
        except ValueError as e:
            return erreur(str(e), 400)
        except OSError as e:
            return erreur(f"config.toml n'a pas pu être écrit : {e}", 500)
        return jsonify({**reglages_pour_la_page(), "redemarrage": redemarrage})

    # --- Création ---------------------------------------------------------------
    @app.post("/api/npc/generate")
    def generate_npc():
        d = corps()
        try:
            return jsonify(ctx.creer_pnj(chaine(d.get("role")), chaine(d.get("nom")), chaine(d.get("genre")),
                                         chaine(d.get("consignes")), chaine(d.get("lieu"))))
        except ValueError:
            return erreur("Le modèle n'a pas renvoyé de JSON valide. Relancez la génération.", 502)
        except MoteurIndisponible as e:
            return erreur(f"{e} Choisissez un PNJ dans la banque.", 503)

    # --- Scénario et banque de PNJ ------------------------------------------------
    @app.get("/api/scenario")
    def scenario_get():
        scenario = ctx.banque.scenario()
        return jsonify(scenario if est_mj() else masquer(scenario, "notes_mj"))

    @app.put("/api/scenario")
    @mj
    def scenario_put():
        """Remplace le scénario ; `notes_mj` absent (page chargée sans mot de passe) = notes gardées."""
        data = corps()
        if "notes_mj" not in data:
            data = {**data, "notes_mj": ctx.banque.scenario()["notes_mj"]}
        return jsonify(ctx.banque.enregistrer_scenario(data))

    @app.get("/api/styles")
    def styles_get():
        return jsonify(ctx.styles())

    @app.put("/api/styles")
    @mj
    def styles_put():
        """Remplace les thèmes et styles de l'univers : {themes: {id: ...}, portraits: {id: ...}}."""
        try:
            ctx.banque.enregistrer_styles(request.get_json(silent=True))
        except ValueError as e:
            return erreur(str(e), 400)
        return jsonify(ctx.styles())

    @app.get("/api/scenario/export")
    @mj
    def scenario_export():
        nom = time.strftime("scenario-%Y-%m-%d-%Hh%M.zip")
        return send_file(io.BytesIO(ctx.banque.exporter_zip()), mimetype="application/zip",
                         as_attachment=True, download_name=nom)

    @app.post("/api/scenario/import")
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
            return jsonify(ctx.banque.importer(fichiers, remplacer=request.form.get("remplacer", "1") != "0"))
        except ValueError as e:
            return erreur(str(e), 400)

    @app.delete("/api/univers")
    @mj
    def univers_vider():
        """Nouvelle table : supprime le scénario, les lieux et tous les PNJ de la banque."""
        return jsonify({"pnj": ctx.banque.vider()})

    @app.get("/api/exemples")
    def exemples_liste():
        return jsonify(exemples())

    @app.post("/api/exemples/<exemple_id>")
    @mj
    def exemple_charger(exemple_id):
        """Copie l'univers d'exemple dans la banque ; {remplacer: false} garde les PNJ actuels."""
        dossier = EXEMPLES / exemple_id
        if not NPC_ID.fullmatch(exemple_id) or not dossier.is_dir():
            return erreur("Exemple introuvable.", 404)
        fichiers = {f.name: f.read_bytes() for f in dossier.glob("*.json") if f.name != INFOS}
        remplacer = corps().get("remplacer", True)
        return jsonify(ctx.banque.importer(fichiers, remplacer=remplacer))

    @app.get("/api/lieux")
    def lieux_get():
        lieux = ctx.banque.lieux()
        return jsonify(lieux if est_mj() else [masquer(lieu, "notes_mj") for lieu in lieux])

    @app.put("/api/lieux")
    @mj
    def lieux_put():
        """Remplace la liste des lieux : [{id (absent pour un nouveau lieu), nom, description, notes_mj}] ;
        `notes_mj` absent d'un lieu existant (page chargée sans mot de passe) = ses notes gardées."""
        notes = {lieu["id"]: lieu.get("notes_mj", "") for lieu in ctx.banque.lieux()}
        liste = [{**lieu, "notes_mj": notes.get(lieu.get("id"), "") if isinstance(lieu.get("id"), str) else ""}
                 if isinstance(lieu, dict) and "notes_mj" not in lieu else lieu for lieu in corps(list)]
        return jsonify(ctx.banque.enregistrer_lieux(liste))

    def fiche_complete(npc):
        return all(isinstance(npc.get(c), str) and npc[c].strip() for c in ("nom", "salutation"))

    @app.get("/api/bank")
    def bank_list():
        return jsonify(ctx.banque.liste())

    @app.get("/api/bank/<npc_id>")
    def bank_get(npc_id):
        npc = ctx.banque.lire(npc_id)
        if npc is None:
            return erreur("PNJ introuvable.", 404)
        npc = voix.verifier(ctx.tts, npc)
        return jsonify(npc if est_mj() else masquer(npc, "secret"))

    @app.post("/api/bank")
    @mj
    def bank_save():
        npc = corps()
        if not fiche_complete(npc):
            return erreur("Fiche de PNJ incomplète.", 400)
        return jsonify({"id": ctx.enregistrer_pnj(npc)})

    @app.put("/api/bank/<npc_id>")
    @mj
    def bank_update(npc_id):
        """Remplace la fiche ; `secret` absent (fiche lue sans mot de passe) = secret de la banque gardé."""
        npc = corps()
        enregistree = ctx.banque.lire(npc_id)
        if enregistree is None:
            return erreur("PNJ introuvable.", 404)
        if not fiche_complete(npc):
            return erreur("Fiche de PNJ incomplète.", 400)
        if "secret" not in npc:
            npc = {**npc, "secret": enregistree.get("secret", "")}
        return jsonify({"id": ctx.enregistrer_pnj(npc, npc_id)})

    @app.delete("/api/bank/<npc_id>")
    @mj
    def bank_delete(npc_id):
        if not ctx.banque.supprimer(npc_id):
            return erreur("PNJ introuvable.", 404)
        return jsonify({"ok": True})

    # --- Portraits -----------------------------------------------------------------
    @app.get("/api/bank/<npc_id>/portrait")
    def portrait_get(npc_id):
        chemin = ctx.banque.portrait(npc_id)
        if chemin is None:
            return erreur("Pas de portrait.", 404)
        # lu en mémoire : sous Windows, un fichier encore ouvert ne pourrait être ni refait ni supprimé.
        # Adresse avec ?v=<version> (champ « portrait » de la fiche) : gardée en cache, elle change avec l'image.
        return send_file(io.BytesIO(chemin.read_bytes()), mimetype=mimetypes.guess_type(chemin.name)[0],
                         max_age=86400 if request.args.get("v") else 0)

    @app.post("/api/bank/<npc_id>/portrait")
    @mj
    def portrait_generer(npc_id):
        """Génère et enregistre le portrait d'un PNJ de la banque. Corps facultatif : la fiche en cours
        d'édition (apparence modifiée mais pas encore enregistrée). Renvoie {portrait: version, prompt}."""
        npc = ctx.banque.lire(npc_id)
        if npc is None:
            return erreur("PNJ introuvable.", 404)
        if not ctx.portraits.disponible():
            return erreur("Portraits désactivés : choisissez un moteur dans [portraits] de config.toml.", 400)
        npc.update(corps())
        prompt = prompt_portrait(ctx.moteurs, npc, ctx.style_portrait())
        try:
            octets, ext = ctx.portraits.generer(prompt, secrets.randbelow(2**31))
        except PortraitIndisponible as e:
            return erreur(str(e), 503)
        if not ctx.banque.enregistrer_portrait(npc_id, octets, ext):  # supprimé pendant la génération
            return erreur("PNJ introuvable.", 404)
        return jsonify({"portrait": ctx.banque.version_portrait(npc_id), "prompt": prompt})

    @app.delete("/api/bank/<npc_id>/portrait")
    @mj
    def portrait_supprimer(npc_id):
        if not ctx.banque.supprimer_portrait(npc_id):
            return erreur("Pas de portrait.", 404)
        return jsonify({"ok": True})

    # --- Voix ---------------------------------------------------------------------
    @app.post("/api/voice")
    def new_voice():
        """Tire une autre voix pour le PNJ (changement de genre ou de moteur), en évitant celles des
        autres PNJ de la scène (`eviter`), ou applique celle demandée dans `choix` (nom de GET /api/voices)."""
        npc = corps()
        eviter = npc.get("eviter") if isinstance(npc.get("eviter"), list) else []
        voice = voix.attribuer(ctx.tts, npc, eviter=[v for v in eviter if isinstance(v, dict)])
        choix = npc.get("choix")
        if choix:
            trouvee = next((v for v, _ in ctx.tts.catalogue() if v["name"] == choix), None)
            if not trouvee:
                return erreur("Voix inconnue.", 404)
            voice.update(trouvee)
        return jsonify(voice)

    @app.get("/api/voices")
    def voices_list():
        """Voix du moteur de synthèse, avec leur genre, pour la liste de choix de la page de création."""
        return jsonify([{**v, "genre": g} for v, g in ctx.tts.catalogue()])

    @app.get("/api/voice-engine")
    def voice_engine_get():
        return jsonify({"actuel": ctx.tts.nom, "moteurs": list(voix.MOTEURS)})

    @app.put("/api/voice-engine")
    @mj
    def voice_engine_set():
        """Change de moteur de synthèse pour tout le serveur, sans toucher à config.toml."""
        try:
            ctx.changer_tts(chaine(corps().get("moteur")))
        except ValueError as e:
            return erreur(str(e), 400)
        return jsonify({"actuel": ctx.tts.nom})

    @app.post("/api/tts")
    def synthese():
        data = corps()
        text = texte.chiffres_en_lettres(texte.nettoyer(chaine(data.get("text"))))[:600]
        if not text:
            return erreur("Rien à lire.", 400)
        voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
        if data.get("narrateur"):  # description entre parenthèses : voix neutre, autre que celles des PNJ
            autres = data.get("eviter") if isinstance(data.get("eviter"), list) else []
            eviter = [voice] + [v for v in autres if isinstance(v, dict)]
            voice = voix.voix_narrateur(ctx.tts, eviter)
            if voice is None:
                return erreur("Synthèse vocale indisponible.", 503)
        try:
            audio, mimetype = ctx.tts.synthese(text, voice)
        except voix.VoixIndisponible as e:
            log.warning("Synthèse vocale : %s", e)
            return erreur("Synthèse vocale indisponible.", 503)
        return send_file(io.BytesIO(audio), mimetype=mimetype)

    # --- Dialogue -----------------------------------------------------------------
    @app.post("/api/npc/talk")
    def talk():
        """Réplique de `npc` dans la scène `history` (voir le module dialogue), en NDJSON :
        une ligne {"phrase": ...} par phrase prête à être lue, ou {"error": ...}."""
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

    @app.post("/api/stt")
    def stt():
        """Transcrit l'enregistrement du micro (webm/opus envoyé par le navigateur)."""
        audio = request.files.get("audio")
        if not ctx.reconnaissance.disponible():
            return erreur("Reconnaissance vocale locale indisponible.", 404)
        if not audio:
            return erreur("Aucun enregistrement reçu.", 400)
        indice = request.form.get("indice", "").strip()[:200] or None
        octets = audio.read(STT_MAX_OCTETS + 1)
        if len(octets) > STT_MAX_OCTETS:
            return erreur("Enregistrement trop long.", 413)
        return jsonify({"text": ctx.reconnaissance.transcrire(octets, indice)})

    return app


# --- Lancement ----------------------------------------------------------------------
def arreter(signum=None, frame=None):
    """Ctrl+C : quitte aussitôt, sans pile d'erreurs. os._exit n'attend pas les fils en cours
    (préchargement des voix et de Whisper, réponses en streaming), que l'arrêt normal de Python
    interromprait en plein travail, d'où des erreurs en cascade."""
    print("\nArrêt des PNJ parlants.", flush=True)
    os._exit(0)


def certificat(cfg):
    """HTTPS auto-signé, nécessaire pour le micro quand on accède au serveur depuis une autre machine
    (ex. le téléphone d'un joueur). Le certificat est créé une seule fois dans certs/ puis réutilisé :
    le navigateur garde ainsi l'exception de sécurité et l'autorisation du micro d'un lancement à l'autre."""
    from werkzeug.serving import make_ssl_devcert
    cert, key = cfg.chemin("certs/devcert.crt"), cfg.chemin("certs/devcert.key")
    if not (cert.exists() and key.exists()):
        cert.parent.mkdir(exist_ok=True)
        make_ssl_devcert(str(cert.with_suffix("")), host="pnj-parlants")
    return str(cert), str(key)


def main(argv=None):
    # Avant de charger les modèles (PyTorch…) : Ctrl+C marche dès le lancement
    signal.signal(signal.SIGINT, arreter)
    signal.signal(signal.SIGTERM, arreter)
    if hasattr(signal, "SIGBREAK"):  # Ctrl+Pause sous Windows
        signal.signal(signal.SIGBREAK, arreter)

    parser = argparse.ArgumentParser(description="Serveur des PNJ parlants.")
    parser.add_argument("--config", help="chemin de config.toml (par défaut : celui du dossier courant)")
    args = parser.parse_args(argv)
    sortie = logging.StreamHandler()  # messages du paquet seulement : Flask garde son propre affichage
    sortie.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logging.getLogger("pnj_parlant").addHandler(sortie)
    logging.getLogger("pnj_parlant").setLevel(logging.INFO)
    try:
        cfg = configuration.charger(args.config)
        app = create_app(cfg)
    except (configuration.ConfigIntrouvable, ValueError) as e:
        raise SystemExit(str(e)) from e
    ctx = app.extensions["pnj"]

    threading.Thread(target=ctx.tts.prechauffer, daemon=True).start()  # voix prêtes avant la 1re réplique
    if ctx.reconnaissance.disponible():
        threading.Thread(target=ctx.reconnaissance.charger, daemon=True).start()  # prêt avant la 1re question
    for p in ctx.problemes():  # les mêmes messages s'affichent dans le bandeau des pages
        print(f"[{'ERREUR' if p['niveau'] == 'erreur' else 'attention'}] {p['message']}")
    srv = cfg.section("serveur")
    ssl = certificat(cfg) if srv.get("https") else None
    app.run(host=srv.get("hote", "0.0.0.0"), port=srv.get("port", 5000), ssl_context=ssl)


if __name__ == "__main__":
    main()
