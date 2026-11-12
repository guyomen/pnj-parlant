"""
Lecture de config.toml.

Le fichier est cherché, dans l'ordre : chemin donné en argument (--config), variable d'environnement
PNJ_CONFIG, puis config.toml dans le dossier courant. Les dossiers relatifs qu'il cite (banque de PNJ,
voix Piper, modèles Whisper, certificats) sont pris par rapport au dossier de config.toml.
"""
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigIntrouvable(Exception):
    pass


@dataclass
class Config:
    reglages: dict  # contenu de config.toml
    racine: Path    # dossier de config.toml : base des chemins relatifs

    def section(self, nom):
        return self.reglages.get(nom, {})

    def chemin(self, valeur):
        """Chemin relatif au dossier de config.toml (un chemin absolu reste absolu)."""
        return self.racine / valeur


def trouver(chemin=None):
    chemin = Path(chemin or os.environ.get("PNJ_CONFIG") or "config.toml")
    if not chemin.exists():
        raise ConfigIntrouvable(
            f"{chemin} introuvable : copiez config.toml.example en config.toml (dans le dossier "
            "depuis lequel vous lancez l'application) et renseignez votre clé API.")
    return chemin.resolve()


def charger(chemin=None):
    chemin = trouver(chemin)
    with open(chemin, "rb") as f:
        return Config(tomllib.load(f), chemin.parent)


def ollama_sur_ce_pc(cfg):
    """True si un moteur de langage est « local » et qu'Ollama est attendu sur ce PC (localhost) : les lanceurs
    Windows ne démarrent Docker ou ne vérifient Ollama que dans ce cas. En tout-Claude, rien à démarrer."""
    moteurs = cfg.section("moteurs") or {"creation": "claude", "dialogue": "claude"}
    if "local" not in (moteurs.get("creation"), moteurs.get("dialogue")):
        return False
    hote = urlsplit(cfg.section("local").get("url", "http://localhost:11434")).hostname
    return hote in ("localhost", "127.0.0.1", "::1")


if __name__ == "__main__":
    # python -m pnj_parlant.config : code de sortie 0 si Ollama doit tourner sur ce PC, 1 sinon,
    # 2 si config.toml manque (l'application affichera alors l'erreur). Utilisé par lancer.bat et lancerAMD.bat.
    try:
        sys.exit(0 if ollama_sur_ce_pc(charger()) else 1)
    except ConfigIntrouvable:
        sys.exit(2)
