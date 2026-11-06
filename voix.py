"""
Moteurs de synthèse vocale : lisent à voix haute les répliques des PNJ.

Le choix se fait dans la section [voix] de config.toml :
    moteur = "piper"    # local, très léger (convient à un petit processeur), voix un peu mécaniques
    moteur = "pocket"   # local, Pocket TTS de Kyutai : bien plus naturel, demande le processeur d'un PC
    moteur = "edge"     # voix neuronales de Microsoft Edge : les plus naturelles, mais réseau nécessaire
Sans moteur disponible, le navigateur lit le texte lui-même (speechSynthesis).

Chaque moteur expose :
    catalogue()            -> [(voix, genre)], voix = {"name": ..., "label": ...} (+ "speaker" pour Piper)
    synthese(texte, voix)  -> (octets audio, type MIME) ; lève VoixIndisponible
    prechauffer()          -> charge le modèle à l'avance (au démarrage, dans un fil séparé)
"""
import io
import json
import threading
import wave


class VoixIndisponible(Exception):
    """La synthèse a échoué (voix absente, réseau coupé…) : le navigateur prend le relais."""


MOTEURS = ("piper", "pocket", "edge")


def charger(config, base_dir, moteur=None):
    """Le moteur demandé, ou celui de config.toml. Seul celui-là est importé (Pocket TTS charge PyTorch)."""
    cfg = config.get("voix", {})
    moteur = moteur or cfg.get("moteur", "piper")
    classes = {"piper": Piper, "pocket": Pocket, "edge": Edge}
    if moteur not in classes:
        raise ValueError(f"Moteur de voix « {moteur} » inconnu : choisissez piper, pocket ou edge.")
    return classes[moteur](cfg.get(moteur, {}), base_dir)


def _wav(samples_int16, sample_rate):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples_int16)
    return buf.getvalue()


# --- Piper : local, léger ---------------------------------------------------
class Piper:
    nom = "piper"

    def __init__(self, cfg, base_dir):
        self.dossier = base_dir / cfg.get("dossier", "voices")  # un chemin absolu reste absolu
        self.genres = cfg.get("genres", {})
        self._cache = {}
        try:
            from piper import PiperVoice, SynthesisConfig
            self._piper = (PiperVoice, SynthesisConfig)
        except ImportError:
            self._piper = None

    def _voix_installees(self):
        """{nom de la voix: nombre de locuteurs} pour chaque .onnx du dossier."""
        if not self._piper or not self.dossier.exists():
            return {}
        voix = {}
        for onnx in sorted(self.dossier.glob("*.onnx")):
            cfg = onnx.with_suffix(".onnx.json")
            speakers = 1
            if cfg.exists():
                speakers = json.loads(cfg.read_text(encoding="utf-8")).get("num_speakers", 1)
            voix[onnx.stem] = max(1, speakers)
        return voix

    def _genre(self, name, speaker):
        """Genre d'un locuteur d'après la section [voix.piper.genres] de config.toml."""
        g = self.genres.get(name)
        if isinstance(g, str):  # voix à un seul genre : tous ses locuteurs
            return g
        if isinstance(g, dict):  # voix multi-locuteurs : { feminin = [0], masculin = [1] }
            return next((genre for genre, ids in g.items() if speaker in ids), None)
        return None  # genre inconnu

    def catalogue(self):
        court = lambda n: n.removeprefix("fr_FR-").removesuffix("-medium")
        return [({"name": name, "speaker": i, "label": f"{court(name)} · locuteur {i}"}, self._genre(name, i))
                for name, speakers in self._voix_installees().items() for i in range(speakers)]

    def prechauffer(self):
        pass  # chaque voix se charge en une fraction de seconde à sa première réplique

    def synthese(self, texte, voix):
        installees = self._voix_installees()
        name = voix.get("name")
        if name not in installees:  # protège aussi contre les chemins arbitraires
            raise VoixIndisponible(f"Voix Piper « {name} » absente.")
        PiperVoice, SynthesisConfig = self._piper
        if name not in self._cache:
            self._cache[name] = PiperVoice.load(self.dossier / f"{name}.onnx")
        cfg = SynthesisConfig(speaker_id=voix.get("speaker") if installees[name] > 1 else None,
                              length_scale=float(voix.get("length_scale", 1.0)))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            self._cache[name].synthesize_wav(texte, wav_file, syn_config=cfg)
        return buf.getvalue(), "audio/wav"


# --- Pocket TTS (Kyutai) : local, naturel, tourne sur processeur -------------
# Voix intégrées au modèle français. Genres déduits des locuteurs d'origine : écoutez-les avec le
# menu des voix de la page de création, et corrigez au besoin dans [voix.pocket.genres] de config.toml.
POCKET_GENRES = {
    "estelle": "feminin", "cosette": "feminin", "fantine": "feminin", "eponine": "feminin",
    "azelma": "feminin", "alba": "feminin", "anna": "feminin", "vera": "feminin", "mary": "feminin",
    "jane": "feminin", "eve": "feminin", "caro_davy": "feminin",
    "marius": "masculin", "javert": "masculin", "jean": "masculin", "charles": "masculin",
    "paul": "masculin", "george": "masculin", "michael": "masculin", "bill_boerst": "masculin",
    "peter_yearsley": "masculin", "stuart_bell": "masculin",
}


class Pocket:
    nom = "pocket"

    def __init__(self, cfg, base_dir):
        self.genres = cfg.get("genres") or POCKET_GENRES
        self._modele = None
        self._etats = {}  # voix -> état du modèle conditionné par cette voix
        self._absentes = set()  # voix qui n'ont pas pu être chargées (pas encore téléchargées, sans réseau)
        self._verrou = threading.Lock()  # le modèle ne sait pas générer deux répliques à la fois
        try:
            import pocket_tts  # noqa: F401  (importé pour de bon au chargement du modèle)
            self._ok = True
        except ImportError:
            self._ok = False

    def catalogue(self):
        if not self._ok:
            return []
        return [({"name": name, "label": name.replace("_", " ").title()}, genre)
                for name, genre in self.genres.items() if name not in self._absentes]

    def _etat(self, name):
        """Charge le modèle et la voix si besoin (appelé avec le verrou). Le premier appel télécharge
        le modèle et les voix (réseau nécessaire) ; ils restent ensuite en cache sur la machine."""
        if self._modele is None:
            from pocket_tts import TTSModel
            self._modele = TTSModel.load_model(language="french")
        if name not in self._etats:
            self._etats[name] = self._modele.get_state_for_audio_prompt(name)
        return self._etats[name]

    def prechauffer(self):
        """Charge le modèle et toutes les voix : lancé avec le réseau, cela les met en cache pour jouer sans."""
        for name in self.genres:
            try:
                with self._verrou:
                    self._etat(name)
            except Exception as e:  # réseau absent, voix inconnue… : la voix ne sera plus attribuée
                self._absentes.add(name)
                print(f"[voix] Pocket TTS : voix « {name} » indisponible ({type(e).__name__}). "
                      "Lancez l'application une fois avec le réseau pour la télécharger.")

    def synthese(self, texte, voix):
        name = voix.get("name")
        if not self._ok or name not in self.genres:
            raise VoixIndisponible(f"Voix Pocket TTS « {name} » absente.")
        try:
            with self._verrou:
                etat = self._etat(name)  # charge aussi le modèle au premier appel
                audio = self._modele.generate_audio(etat, texte)  # flottants entre -1 et 1
        except Exception as e:  # modèle ou voix pas encore téléchargés et pas de réseau, etc.
            raise VoixIndisponible(f"Pocket TTS : {type(e).__name__}") from e
        samples = (audio.clamp(-1, 1) * 32767).short().numpy().tobytes()
        return _wav(samples, self._modele.sample_rate), "audio/wav"


# --- Edge : voix neuronales de Microsoft, en ligne ---------------------------
# fr-FR-EloiseNeural (voix d'enfant) et les voix canadiennes sont laissées de côté ; ajoutez-les
# dans [voix.edge.genres] de config.toml si vous voulez les utiliser.
EDGE_GENRES = {
    "fr-FR-DeniseNeural": "feminin", "fr-FR-VivienneMultilingualNeural": "feminin",
    "fr-BE-CharlineNeural": "feminin", "fr-CH-ArianeNeural": "feminin",
    "fr-FR-HenriNeural": "masculin", "fr-FR-RemyMultilingualNeural": "masculin",
    "fr-BE-GerardNeural": "masculin", "fr-CH-FabriceNeural": "masculin",
}


class Edge:
    nom = "edge"

    def __init__(self, cfg, base_dir):
        self.genres = cfg.get("genres") or EDGE_GENRES
        try:
            import edge_tts
            self._edge = edge_tts
        except ImportError:
            self._edge = None

    def catalogue(self):
        if not self._edge:
            return []
        court = lambda n: n.split("-")[2].removesuffix("Neural").removesuffix("Multilingual")
        return [({"name": name, "label": f"{court(name)} ({name[3:5]})"}, genre)
                for name, genre in self.genres.items()]

    def prechauffer(self):
        pass  # rien à charger : tout se passe sur les serveurs de Microsoft

    def synthese(self, texte, voix):
        name = voix.get("name")
        if not self._edge or name not in self.genres:
            raise VoixIndisponible(f"Voix Edge « {name} » absente.")
        # Débit et hauteur d'après la fiche du PNJ (Piper règle le débit avec length_scale)
        rate = round((1 / float(voix.get("length_scale", 1.0)) - 1) * 100)
        pitch = {"grave": -8, "aigu": 8}.get(voix.get("timbre"), 0)
        try:
            com = self._edge.Communicate(texte, name, rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz")
            audio = b"".join(c["data"] for c in com.stream_sync() if c["type"] == "audio")
        except Exception as e:  # réseau coupé, service refusé… : les erreurs possibles sont nombreuses
            raise VoixIndisponible(f"Edge : {type(e).__name__}") from e
        if not audio:
            raise VoixIndisponible("Edge n'a renvoyé aucun son.")
        return audio, "audio/mpeg"
