"""
Voix des PNJ, synthèse et reconnaissance vocales.

    POST /api/voice                   autre voix pour un PNJ ; GET /api/voices : voix du moteur
    GET|PUT /api/voice-engine         moteur de synthèse (jusqu'au redémarrage)
    POST /api/tts                     synthèse vocale {text, voice, narrateur, eviter}
    POST /api/stt                     reconnaissance vocale (audio webm/opus + indice)
"""
import io
import logging

from flask import Blueprint, jsonify, request, send_file

from .. import texte, voix
from . import entrees
from .acces import mj
from .entrees import chaine, contexte, corps, erreur

log = logging.getLogger("pnj_parlant.serveur")  # même nom qu'avant le découpage en Blueprints
bp = Blueprint("voix", __name__)


@bp.post("/api/voice")
def new_voice():
    """Tire une autre voix pour le PNJ (changement de genre ou de moteur), en évitant celles des
    autres PNJ de la scène (`eviter`), ou applique celle demandée dans `choix` (nom de GET /api/voices)."""
    tts = contexte().tts
    npc = corps()
    eviter = npc.get("eviter") if isinstance(npc.get("eviter"), list) else []
    voice = voix.attribuer(tts, npc, eviter=[v for v in eviter if isinstance(v, dict)])
    choix = npc.get("choix")
    if choix:
        trouvee = next((v for v, _ in tts.catalogue() if v["name"] == choix), None)
        if not trouvee:
            return erreur("Voix inconnue.", 404)
        voice.update(trouvee)
    return jsonify(voice)


@bp.get("/api/voices")
def voices_list():
    """Voix du moteur de synthèse, avec leur genre, pour la liste de choix de la page de création."""
    return jsonify([{**v, "genre": g} for v, g in contexte().tts.catalogue()])


@bp.get("/api/voice-engine")
def voice_engine_get():
    return jsonify({"actuel": contexte().tts.nom, "moteurs": list(voix.MOTEURS)})


@bp.put("/api/voice-engine")
@mj
def voice_engine_set():
    """Change de moteur de synthèse pour tout le serveur, sans toucher à config.toml."""
    ctx = contexte()
    try:
        ctx.changer_tts(chaine(corps().get("moteur")))
    except ValueError as e:
        return erreur(str(e), 400)
    return jsonify({"actuel": ctx.tts.nom})


@bp.post("/api/tts")
def synthese():
    tts = contexte().tts
    data = corps()
    text = texte.chiffres_en_lettres(texte.nettoyer(chaine(data.get("text"))))[:600]
    if not text:
        return erreur("Rien à lire.", 400)
    voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
    if data.get("narrateur"):  # description entre parenthèses : voix neutre, autre que celles des PNJ
        autres = data.get("eviter") if isinstance(data.get("eviter"), list) else []
        eviter = [voice] + [v for v in autres if isinstance(v, dict)]
        voice = voix.voix_narrateur(tts, eviter)
        if voice is None:
            return erreur("Synthèse vocale indisponible.", 503)
    try:
        audio, mimetype = tts.synthese(text, voice)
    except voix.VoixIndisponible as e:
        log.warning("Synthèse vocale : %s", e)
        return erreur("Synthèse vocale indisponible.", 503)
    return send_file(io.BytesIO(audio), mimetype=mimetype)


@bp.post("/api/stt")
def stt():
    """Transcrit l'enregistrement du micro (webm/opus envoyé par le navigateur)."""
    reconnaissance = contexte().reconnaissance
    audio = request.files.get("audio")
    if not reconnaissance.disponible():
        return erreur("Reconnaissance vocale locale indisponible.", 404)
    if not audio:
        return erreur("Aucun enregistrement reçu.", 400)
    indice = request.form.get("indice", "").strip()[:200] or None
    octets = audio.read(entrees.STT_MAX_OCTETS + 1)
    if len(octets) > entrees.STT_MAX_OCTETS:
        return erreur("Enregistrement trop long.", 413)
    return jsonify({"text": reconnaissance.transcrire(octets, indice)})
