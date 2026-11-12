"""
PNJ parlants : générateur de personnages non-joueurs qui répondent à voix haute.

- Claude Haiku ou un modèle local (Ollama) invente le PNJ (fiche JSON) puis joue son rôle.
- Piper, Pocket TTS ou Edge lit les répliques à voix haute (sinon, repli sur la voix du navigateur).
- La voix du joueur est reconnue sur le serveur par faster-whisper (sans réseau),
  ou à défaut par le navigateur (Web Speech API, qui envoie l'audio à Google ou Microsoft).

Modules :
    config     lecture de config.toml
    texte      nettoyage du texte avant la synthèse, découpage en phrases
    fiches     création des fiches de PNJ
    dialogue   consignes du PNJ et mise en scène de la conversation
    moteurs    modèles de langage : Claude ou Ollama
    voix       synthèse vocale : Piper, Pocket TTS ou Edge, et attribution des voix
    stt        reconnaissance vocale : faster-whisper
    portraits  portraits des PNJ (facultatif) : Stable Diffusion Turbo ou Pollinations
    banque     banque de PNJ et scénario (fichiers JSON)
    systeme    état de la machine : carte graphique, Ollama
    serveur    application Flask (routes)
    generer    remplissage de la banque en lot
"""

__version__ = "1.0.0"  # même valeur que dans pyproject.toml (vérifié par les tests)
