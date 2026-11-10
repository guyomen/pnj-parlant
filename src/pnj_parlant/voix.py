"""
Moteurs de synthèse vocale : lisent à voix haute les répliques des PNJ.

Le choix se fait dans la section [voix] de config.toml :
    moteur = "piper"    # local, très léger (convient à un petit processeur), voix un peu mécaniques
    moteur = "pocket"   # local, Pocket TTS de Kyutai : bien plus naturel, demande le processeur d'un PC
    moteur = "edge"     # voix neuronales de Microsoft Edge : les plus naturelles, mais réseau nécessaire
Sans moteur disponible, le navigateur lit le texte lui-même (speechSynthesis).

Chaque moteur expose :
    nom                    -> "piper", "pocket" ou "edge"
    catalogue()            -> [(voix, genre)], voix = {"name": ..., "label": ...} (+ "speaker" pour Piper)
    synthese(texte, voix)  -> (octets audio, type MIME) ; lève VoixIndisponible
    prechauffer()          -> charge le modèle à l'avance (au démarrage, dans un fil séparé)

La voix d'un PNJ (champ "voix" de sa fiche) est choisie par attribuer() : une voix du moteur, du genre
du PNJ, plus les réglages de débit et de hauteur (et ceux de la voix du navigateur, en repli).
"""
import io
import json
import random
import threading
import wave


class VoixIndisponible(Exception):
    """La synthèse a échoué (voix absente, réseau coupé…) : le navigateur prend le relais."""


MOTEURS = ("piper", "pocket", "edge")

# Voix du narrateur, qui lit les descriptions entre parenthèses ; à changer avec
# narrateur = "..." dans [voix.piper], [voix.pocket] ou [voix.edge] de config.toml.
NARRATEUR = {"piper": "fr_FR-siwis-medium", "pocket": "estelle", "edge": "fr-FR-VivienneMultilingualNeural"}


def charger(config, base_dir, moteur=None):
    """Le moteur demandé, ou celui de config.toml. Seul celui-là est importé (Pocket TTS charge PyTorch)."""
    cfg = config.get("voix", {})
    moteur = moteur or cfg.get("moteur", "piper")
    classes = {"piper": Piper, "pocket": Pocket, "edge": Edge}
    if moteur not in classes:
        raise ValueError(f"Moteur de voix « {moteur} » inconnu : choisissez piper, pocket ou edge.")
    sous_cfg = cfg.get(moteur, {})
    instance = classes[moteur](sous_cfg, base_dir)
    instance.narrateur = sous_cfg.get("narrateur", NARRATEUR[moteur])
    instance.narrateur_locuteur = sous_cfg.get("narrateur_locuteur")  # voix Piper à plusieurs locuteurs
    return instance


def cle(voix):
    """Identité d'une voix : nom + locuteur (Piper)."""
    return (voix.get("name"), voix.get("speaker"))


def attribuer(moteur, npc, rng=random, eviter=()):
    """Choisit une voix du moteur, du genre du PNJ, réglée d'après son timbre et son débit
    (avec aussi un réglage pour la voix du navigateur, en repli).
    `eviter` : voix déjà prises par les autres PNJ de la scène, écartées tant qu'il en reste d'autres."""
    genre = npc.get("genre")
    debit = {"lent": 1.2, "normal": 1.0, "rapide": 0.85}.get(npc.get("debit"), 1.0)
    pitch = {"grave": 0.7, "moyen": 1.0, "aigu": 1.35}.get(npc.get("timbre"), 1.0)
    pitch *= {"feminin": 1.25, "masculin": 0.85}.get(genre, 1.0)  # voix du navigateur
    voice = {"length_scale": round(debit * rng.uniform(0.95, 1.05), 2), "timbre": npc.get("timbre"),
             "browser_pitch": round(pitch, 2), "browser_rate": round(1 / debit, 2)}
    prises = {cle(v) for v in eviter if isinstance(v, dict)}
    catalogue = [(v, g) for v, g in moteur.catalogue() if cle(v) not in prises] or moteur.catalogue()
    if catalogue:
        # Voix du bon genre ; à défaut (PNJ neutre ou aucune voix de ce genre), n'importe laquelle.
        matching = [v for v, g in catalogue if g == genre]
        voice.update(rng.choice(matching or [v for v, _ in catalogue]))
    voice["genre"] = genre
    voice["moteur"] = moteur.nom
    return voice


def verifier(moteur, npc):
    """Réattribue une voix si celle du PNJ vient d'un autre moteur, manque sur cette machine ou ne
    correspond plus à son genre. Le tirage est fixé par le nom : le PNJ retrouve la même voix à chaque fois."""
    v = npc.get("voix") or {}
    connues = [cle(c) for c, _ in moteur.catalogue()]
    if v.get("moteur", "piper") != moteur.nom or cle(v) not in connues or v.get("genre") != npc.get("genre"):
        npc["voix"] = attribuer(moteur, npc, random.Random(npc.get("nom", "")))
    return npc


def voix_narrateur(moteur, eviter=()):
    """Voix neutre pour les descriptions entre parenthèses : celle de config.toml, sauf si c'est
    celle d'un PNJ de la scène (`eviter`) ; on prend alors une autre voix du même genre. None si aucune voix."""
    pris = {cle(v) for v in eviter}
    catalogue = [(v, g) for v, g in moteur.catalogue() if cle(v) not in pris]
    if not catalogue:
        return None
    voulue = lambda v: v["name"] == moteur.narrateur and moteur.narrateur_locuteur in (None, v.get("speaker"))
    genre = next((g for v, g in moteur.catalogue() if voulue(v)), None)
    choisie = (next((v for v, _ in catalogue if voulue(v)), None)
               or next((v for v, g in catalogue if genre and g == genre), None)
               or catalogue[0][0])
    return {**choisie, "length_scale": 1.0, "timbre": "moyen"}


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
