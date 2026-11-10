"""
Reconnaissance vocale locale : faster-whisper, sans réseau (optionnelle).

Section [reconnaissance] de config.toml : moteur = "local" ou "navigateur", modele, dossier, appareil.
Sans modèle Whisper sur la machine, le navigateur utilise sa propre reconnaissance (Web Speech API).
"""
import ctypes
import io
import site
import threading
from pathlib import Path


class Reconnaissance:
    def __init__(self, cfg, racine):
        self.cfg = cfg
        self.dossier = racine / cfg.get("dossier", "modeles-stt") / cfg.get("modele", "small")
        self._modele = None
        self._verrou = threading.Lock()

    @property
    def choisie(self):
        return self.cfg.get("moteur", "navigateur") == "local"

    def disponible(self):
        """Vrai si la reconnaissance locale est choisie, installée, et que le modèle est sur la machine."""
        if not self.choisie or not (self.dossier / "model.bin").exists():
            return False
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def charger(self):
        with self._verrou:  # deux requêtes simultanées ne chargent pas le modèle deux fois
            if self._modele is None:
                from faster_whisper import WhisperModel
                appareil = self.cfg.get("appareil", "cpu")
                if appareil == "cuda":
                    precharger_cuda12()
                precision = self.cfg.get("precision", "float16" if appareil == "cuda" else "int8")
                self._modele = WhisperModel(str(self.dossier), device=appareil, compute_type=precision)
        return self._modele

    def transcrire(self, audio, indice=None):
        """Texte de l'enregistrement (octets webm/opus du navigateur). `indice` (nom et métier des PNJ)
        aide Whisper à écrire les noms propres et le vocabulaire du jeu."""
        try:
            segments, _ = self.charger().transcribe(io.BytesIO(audio), language="fr",
                                                    beam_size=self.cfg.get("beam_size", 5),
                                                    vad_filter=True, initial_prompt=indice)
            return " ".join(s.text.strip() for s in segments).strip()
        except ValueError:
            return ""  # enregistrement vide ou illisible


def precharger_cuda12():
    """CTranslate2 veut CUDA 12 et cuDNN 9 : on charge ceux du paquet pip (nvidia-cublas-cu12,
    nvidia-cudnn-cu12) si le système n'a pas les siens. Sans effet s'ils sont absents."""
    for racine in site.getsitepackages():
        for motif in ("nvidia/cublas/lib/libcublas.so.12", "nvidia/cudnn/lib/libcudnn.so.9"):
            for lib in Path(racine).glob(motif):
                ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
