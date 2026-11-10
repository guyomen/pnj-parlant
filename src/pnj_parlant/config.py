"""
Lecture de config.toml.

Le fichier est cherché, dans l'ordre : chemin donné en argument (--config), variable d'environnement
PNJ_CONFIG, puis config.toml dans le dossier courant. Les dossiers relatifs qu'il cite (banque de PNJ,
voix Piper, modèles Whisper, certificats) sont pris par rapport au dossier de config.toml.
"""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


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
