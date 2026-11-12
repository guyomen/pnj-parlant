"""
Serveur Flask : page de jeu, page de préparation et API.

Lancement :  pnj-parlant            (ou python -m pnj_parlant)   puis ouvrir http://localhost:5000
Réglages :   config.toml du dossier courant (à créer à partir de config.toml.example), ou --config

Routes :
    GET  /api/config                  moteurs utilisés, voix, reconnaissance locale, modèles Ollama
    GET  /api/etat                    carte graphique et Ollama
    POST /api/model                   change de modèle local (jusqu'au redémarrage)
    POST /api/npc/generate            crée une fiche de PNJ {role, nom, genre, consignes, lieu}
    POST /api/npc/talk                réplique d'un PNJ {npc, presents, history, lieu} (NDJSON, phrase par phrase)
    GET|PUT /api/lieux                lieux du scénario
    GET|PUT /api/scenario             univers et notes du MJ
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
import io
import json
import logging
import mimetypes
import os
import secrets
import signal
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

from . import config as configuration
from . import dialogue, fiches, systeme, texte, voix
from .banque import IMPORT_MAX_OCTETS, NPC_ID, Banque, lire_zip, nom_de_fichier
from .moteurs import MoteurIndisponible, Moteurs
from .portraits import STYLE, PortraitIndisponible, prompt_portrait
from .portraits import charger as charger_portraits
from .stt import Reconnaissance

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
EXEMPLES = Path(__file__).parent / "exemples"  # un dossier par univers d'exemple, au format de la banque
INFOS = "_infos.json"                          # {nom, resume} : présentation de l'exemple, jamais importée


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


class Contexte:
    """Tout ce dont les routes ont besoin. Les moteurs peuvent être remplacés (tests)."""

    def __init__(self, cfg, moteurs=None, tts=None, reconnaissance=None, portraits=None):
        self.cfg = cfg
        self.moteurs = moteurs or Moteurs(cfg.reglages)  # Claude ou modèle local, d'après [moteurs]
        self.tts = tts or voix.charger(cfg.reglages, cfg.racine)  # Piper, Pocket TTS ou Edge, d'après [voix]
        self.tts_charges = {self.tts.nom: self.tts}  # on ne recharge pas Pocket TTS à chaque bascule
        self.reconnaissance = reconnaissance or Reconnaissance(cfg.section("reconnaissance"), cfg.racine)
        self.portraits = portraits or charger_portraits(cfg.section("portraits"))  # aucun, local ou en_ligne
        self.style_portrait = cfg.section("portraits").get("style", STYLE)
        self.banque = Banque(cfg.chemin(cfg.section("banque").get("dossier", "pnj")))
        self.historique = cfg.section("dialogue").get("historique", 12)  # messages gardés pour le contexte
        self.intervention = cfg.section("dialogue").get("intervention", 0.3)
        self.phrases_max = max(1, int(cfg.section("dialogue").get("phrases_max", dialogue.PHRASES_MAX)))

    def changer_tts(self, nom):
        """Change de moteur de synthèse pour tout le serveur. Lève ValueError s'il est inutilisable."""
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
        npc = voix.verifier(self.tts, dict(npc))
        npc["salutation"] = texte.nettoyer(npc.get("salutation", ""))
        if npc_id:
            self.banque.ecrire(npc_id, npc)
            return npc_id
        return self.banque.ajouter(npc)


def create_app(cfg, **moteurs):
    """Application Flask. `moteurs` : moteurs=, tts=, reconnaissance=, portraits= pour remplacer ceux de
    config.toml."""
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="")
    ctx = Contexte(cfg, **moteurs)
    app.extensions["pnj"] = ctx

    def erreur(message, code):
        return jsonify({"error": message}), code

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
                        "intervention": ctx.intervention, "modele_local": m.modele_local_installe(installes),
                        "contexte_max": m.contexte_max(),
                        "portraits": ctx.portraits.nom if ctx.portraits.disponible() else None})

    @app.get("/api/etat")
    def etat():
        """État de la machine pour la page de jeu : Ollama (si un moteur local est choisi) et GPU."""
        ollama = None
        if "local" in ctx.moteurs.choix.values():
            ollama = systeme.etat_ollama(ctx.moteurs.local_cfg.get("url", "http://localhost:11434"))
        return jsonify({"gpu": systeme.etat_gpu(), "ollama": ollama})

    @app.post("/api/model")
    def choisir_modele():
        """Change le modèle local pour tout le serveur, sans toucher à config.toml."""
        try:
            ctx.moteurs.choisir_modele_local((request.json or {}).get("modele", ""))
        except MoteurIndisponible as e:
            return erreur(str(e), 400)
        return jsonify({"modele_local": ctx.moteurs.local_cfg["modele"]})

    # --- Création ---------------------------------------------------------------
    @app.post("/api/npc/generate")
    def generate_npc():
        d = request.json or {}
        try:
            return jsonify(ctx.creer_pnj(d.get("role", ""), d.get("nom", ""), d.get("genre", ""),
                                         d.get("consignes", ""), d.get("lieu", "")))
        except ValueError:
            return erreur("Le modèle n'a pas renvoyé de JSON valide. Relancez la génération.", 502)
        except MoteurIndisponible as e:
            return erreur(f"{e} Choisissez un PNJ dans la banque.", 503)

    # --- Scénario et banque de PNJ ------------------------------------------------
    @app.get("/api/scenario")
    def scenario_get():
        return jsonify(ctx.banque.scenario())

    @app.put("/api/scenario")
    def scenario_put():
        return jsonify(ctx.banque.enregistrer_scenario(request.json or {}))

    @app.get("/api/scenario/export")
    def scenario_export():
        nom = time.strftime("scenario-%Y-%m-%d-%Hh%M.zip")
        return send_file(io.BytesIO(ctx.banque.exporter_zip()), mimetype="application/zip",
                         as_attachment=True, download_name=nom)

    @app.post("/api/scenario/import")
    def scenario_import():
        """Champ « fichiers » : une archive zip, ou les fichiers .json d'un dossier ; « remplacer » : "0" pour
        garder les PNJ actuels (voir Banque.importer)."""
        fichiers = {}
        try:
            for f in request.files.getlist("fichiers"):
                octets = f.read(IMPORT_MAX_OCTETS + 1)
                if len(octets) > IMPORT_MAX_OCTETS:
                    return erreur(f"« {f.filename} » est trop volumineux pour un scénario.", 413)
                if (f.filename or "").lower().endswith(".zip"):
                    fichiers.update(lire_zip(octets))
                else:
                    fichiers[nom_de_fichier(f.filename)] = octets
            return jsonify(ctx.banque.importer(fichiers, remplacer=request.form.get("remplacer", "1") != "0"))
        except ValueError as e:
            return erreur(str(e), 400)

    @app.delete("/api/univers")
    def univers_vider():
        """Nouvelle table : supprime le scénario, les lieux et tous les PNJ de la banque."""
        return jsonify({"pnj": ctx.banque.vider()})

    @app.get("/api/exemples")
    def exemples_liste():
        return jsonify(exemples())

    @app.post("/api/exemples/<exemple_id>")
    def exemple_charger(exemple_id):
        """Copie l'univers d'exemple dans la banque ; {remplacer: false} garde les PNJ actuels."""
        dossier = EXEMPLES / exemple_id
        if not NPC_ID.match(exemple_id) or not dossier.is_dir():
            return erreur("Exemple introuvable.", 404)
        fichiers = {f.name: f.read_bytes() for f in dossier.glob("*.json") if f.name != INFOS}
        return jsonify(ctx.banque.importer(fichiers, remplacer=(request.get_json(silent=True) or {}).get("remplacer", True)))

    @app.get("/api/lieux")
    def lieux_get():
        return jsonify(ctx.banque.lieux())

    @app.put("/api/lieux")
    def lieux_put():
        """Remplace la liste des lieux : [{id (absent pour un nouveau lieu), nom, description, notes_mj}]."""
        return jsonify(ctx.banque.enregistrer_lieux(request.json or []))

    @app.get("/api/bank")
    def bank_list():
        return jsonify(ctx.banque.liste())

    @app.get("/api/bank/<npc_id>")
    def bank_get(npc_id):
        npc = ctx.banque.lire(npc_id)
        if npc is None:
            return erreur("PNJ introuvable.", 404)
        return jsonify(voix.verifier(ctx.tts, npc))

    @app.post("/api/bank")
    def bank_save():
        npc = request.json or {}
        if not npc.get("nom") or not npc.get("salutation"):
            return erreur("Fiche de PNJ incomplète.", 400)
        return jsonify({"id": ctx.enregistrer_pnj(npc)})

    @app.put("/api/bank/<npc_id>")
    def bank_update(npc_id):
        npc = request.json or {}
        if not ctx.banque.existe(npc_id):
            return erreur("PNJ introuvable.", 404)
        if not npc.get("nom") or not npc.get("salutation"):
            return erreur("Fiche de PNJ incomplète.", 400)
        return jsonify({"id": ctx.enregistrer_pnj(npc, npc_id)})

    @app.delete("/api/bank/<npc_id>")
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
    def portrait_generer(npc_id):
        """Génère et enregistre le portrait d'un PNJ de la banque. Corps facultatif : la fiche en cours
        d'édition (apparence modifiée mais pas encore enregistrée). Renvoie {portrait: version, prompt}."""
        npc = ctx.banque.lire(npc_id)
        if npc is None:
            return erreur("PNJ introuvable.", 404)
        if not ctx.portraits.disponible():
            return erreur("Portraits désactivés : choisissez un moteur dans [portraits] de config.toml.", 400)
        npc.update(request.get_json(silent=True) or {})
        prompt = prompt_portrait(ctx.moteurs, npc, ctx.style_portrait)
        try:
            octets, ext = ctx.portraits.generer(prompt, secrets.randbelow(2**31))
        except PortraitIndisponible as e:
            return erreur(str(e), 503)
        ctx.banque.enregistrer_portrait(npc_id, octets, ext)
        return jsonify({"portrait": ctx.banque.version_portrait(npc_id), "prompt": prompt})

    @app.delete("/api/bank/<npc_id>/portrait")
    def portrait_supprimer(npc_id):
        if not ctx.banque.supprimer_portrait(npc_id):
            return erreur("Pas de portrait.", 404)
        return jsonify({"ok": True})

    # --- Voix ---------------------------------------------------------------------
    @app.post("/api/voice")
    def new_voice():
        """Tire une autre voix pour le PNJ (changement de genre ou de moteur), en évitant celles des
        autres PNJ de la scène (`eviter`), ou applique celle demandée dans `choix` (nom de GET /api/voices)."""
        npc = request.json or {}
        voice = voix.attribuer(ctx.tts, npc, eviter=npc.get("eviter") or [])
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
    def voice_engine_set():
        """Change de moteur de synthèse pour tout le serveur, sans toucher à config.toml."""
        try:
            ctx.changer_tts((request.json or {}).get("moteur", ""))
        except ValueError as e:
            return erreur(str(e), 400)
        return jsonify({"actuel": ctx.tts.nom})

    @app.post("/api/tts")
    def synthese():
        data = request.json or {}
        text = texte.chiffres_en_lettres(texte.nettoyer(data.get("text", "")))[:600]
        if not text:
            return erreur("Rien à lire.", 400)
        voice = data.get("voice") or {}
        if data.get("narrateur"):  # description entre parenthèses : voix neutre, autre que celles des PNJ
            eviter = [voice] + [v for v in data.get("eviter") or [] if isinstance(v, dict)]
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
        data = request.json or {}
        npc = data.get("npc") or {}
        presents = [p for p in data.get("presents") or [] if isinstance(p, dict) and p.get("nom")][:4]
        history = dialogue.nettoyer_historique(data.get("history"), ctx.historique)
        longueur = data.get("longueur", "normal")
        if not npc.get("nom") or not history:
            return erreur("Il manque le PNJ ou la question.", 400)
        if longueur not in ("short", "normal", "long"):
            return erreur("Longueur de réponse inconnue.", 400)
        phrases_max = {"short": 1, "normal": ctx.phrases_max,
                       "long": max(ctx.phrases_max * 2, 6)}[longueur]
        lieux = ctx.banque.lieux()
        lieu = next((l for l in lieux if l["id"] == data.get("lieu")), None)  # lieu de la scène
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
        return jsonify({"text": ctx.reconnaissance.transcrire(audio.read(), indice)})

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
    if ctx.reconnaissance.choisie:
        if ctx.reconnaissance.disponible():
            threading.Thread(target=ctx.reconnaissance.charger, daemon=True).start()  # prêt avant la 1re question
        else:
            print(f"[reconnaissance] modèle Whisper absent de {ctx.reconnaissance.dossier} : la reconnaissance "
                  "du navigateur sera utilisée. Téléchargez-le avec le réseau (voir README).")
    srv = cfg.section("serveur")
    ssl = certificat(cfg) if srv.get("https") else None
    app.run(host=srv.get("hote", "0.0.0.0"), port=srv.get("port", 5000), ssl_context=ssl)


if __name__ == "__main__":
    main()
