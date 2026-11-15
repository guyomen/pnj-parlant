"""
Routes de l'API, un Blueprint par domaine. Chaque route lit le `serveur.Contexte` par `entrees.contexte()` ;
les écritures de l'univers passent par le décorateur `acces.mj` (mot de passe du MJ hors du PC du serveur).

    options     /api/config, /api/etat, /api/sante, /api/reglages (+ verifier), /api/acces
    univers     /api/scenario (+ export, import), /api/styles, /api/lieux, /api/univers, /api/exemples
    pnj         /api/bank, /api/bank/<id>
    portraits   /api/bank/<id>/portrait
    voix        /api/voice, /api/voices, /api/voice-engine, /api/tts, /api/stt
    dialogue    /api/npc/generate, /api/npc/talk
"""
from . import dialogue, options, pnj, portraits, univers, voix

BLUEPRINTS = [m.bp for m in (options, univers, pnj, portraits, voix, dialogue)]


def enregistrer(app):
    """Ajoute toutes les routes de l'API à l'application."""
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
