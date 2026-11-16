"""
Serveur Flask : page de jeu, page de préparation et API.

Lancement :  pnj-parlant            (ou python -m pnj_parlant)   puis ouvrir http://localhost:5000
Réglages :   config.toml du dossier courant (à créer à partir de config.toml.example), ou --config

Ce module : `Contexte` (moteurs, banque, réglages à chaud, diagnostic), `create_app` (plafonds de taille,
erreurs en JSON, pages) et le lancement. Les routes de l'API sont dans `routes/`, un Blueprint par domaine
(liste dans routes/__init__.py). Hors du PC du serveur, les écritures de l'univers (@mj) demandent le mot de
passe du MJ (en-tête X-Mot-De-Passe-MJ), et les secrets des PNJ et les notes du MJ sont retirés des réponses
(décision D1, routes/acces.py).
"""
import argparse
import copy
import importlib.util
import logging
import mimetypes
import os
import signal
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, request
from werkzeug.exceptions import RequestEntityTooLarge

from . import config as configuration
from . import dialogue, fiches, reglages, routes, systeme, texte, voix
from .banque import IMPORT_MAX_OCTETS, Banque, normaliser_fiche
from .moteurs import Moteurs
from .portraits import STYLE, prompt_du_style, styles
from .portraits import charger as charger_portraits
from .routes import entrees
from .routes.entrees import EntreeInvalide, erreur
from .stt import Reconnaissance

STATIC = Path(__file__).parent / "static"
SANTE_DUREE = 15             # secondes : durée de vie du diagnostic de /api/sante (Contexte.problemes_recents)

# Sous Windows, le registre associe parfois .js à text/plain : le navigateur refuse alors les modules JS.
mimetypes.add_type("text/javascript", ".js")


def paquet_installe(module):
    """Vrai si le module Python peut être importé (sans l'importer : certains chargent PyTorch)."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


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
        self._sante = None  # (échéance, problèmes) : le diagnostic coûte jusqu'à 10 s avec un moteur injoignable
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
            try:
                return self._appliquer_reglages(changements)
            finally:
                self._sante = None  # le diagnostic dépend des réglages : refait à la prochaine page

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

    def problemes_recents(self):
        """`problemes()` gardé SANTE_DUREE secondes : chaque ouverture de page le demande, et il interroge Ollama et
        LM Studio à la suite. Vidé par `appliquer_reglages` et `changer_tts`."""
        vu = self._sante
        if vu and vu[0] > time.monotonic():
            return copy.deepcopy(vu[1])
        liste = self.problemes()
        self._sante = (time.monotonic() + SANTE_DUREE, liste)
        return copy.deepcopy(liste)

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
            self._sante = None

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
    app.config["MAX_CONTENT_LENGTH"] = IMPORT_MAX_OCTETS + entrees.MARGE_MULTIPART  # plafond global : celui de l'import
    ctx = Contexte(cfg, **moteurs)
    app.extensions["pnj"] = ctx

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
            request.max_content_length = entrees.STT_MAX_OCTETS
        elif request.path != "/api/scenario/import":
            request.max_content_length = entrees.CORPS_MAX

    @app.errorhandler(RequestEntityTooLarge)
    def trop_volumineux(e):
        return erreur("Requête trop volumineuse.", 413)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    routes.enregistrer(app)  # API : un Blueprint par domaine (routes/)
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
