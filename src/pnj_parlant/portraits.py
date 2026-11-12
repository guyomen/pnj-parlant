"""
Portraits des PNJ (facultatif) : une image générée pendant la préparation, gardée à côté de la fiche
(pnj/<id>.png, .jpg ou .webp) et exportée avec l'univers. Rien n'est généré pendant la partie : elle reste
jouable sans réseau.

    [portraits] moteur = "aucun"     (défaut) pas de portraits
                         "local"     Stable Diffusion Turbo sur ce PC (option portraits : diffusers) ;
                                     le modèle (~2,5 Go) est téléchargé à la première génération
                         "en_ligne"  Pollinations (gratuit, sans clé) : réseau nécessaire, la description
                                     du PNJ est envoyée à ce service

Le générateur d'images comprend mieux l'anglais : le modèle de création (Claude ou Ollama) traduit l'apparence
de la fiche en une courte description ; s'il ne répond pas, la description est tirée telle quelle de la fiche.
Le style de dessin est choisi par le scénario parmi STYLES (champ « style_portrait »), sinon [portraits] style.
"""
import importlib.util
import io
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .fiches import parse_json
from .moteurs import MoteurIndisponible

log = logging.getLogger(__name__)

STYLE = ("head and shoulders portrait, medieval fantasy character, detailed painting, "
         "soft dramatic lighting, plain dark background")
# Styles de dessin proposés au scénario : identifiant → nom, résumé (pour la page), suite du prompt (anglais)
STYLES = {
    "peinture": ("Peinture fantasy", "Tableau détaillé, lumière dramatique", STYLE),
    "manga": ("Manga", "Animé japonais, traits nets, couleurs vives",
              "head and shoulders portrait, anime style, Japanese manga illustration, clean line art, cel shading, "
              "vibrant colors, fantasy character, simple background"),
    "jdr80": ("JDR années 80", "Encre noir et blanc des premiers livres de jeu de rôle",
              "black and white ink illustration from an old 1980s fantasy role-playing rulebook, comic book inking, "
              "bold outlines, crosshatch shading, retro pulp fantasy line art, head and shoulders portrait"),
    "photo": ("Photo", "Réaliste, comme un portrait photographié",
              "head and shoulders portrait photograph, photorealistic, medieval fantasy costume, natural light, "
              "85mm lens, shallow depth of field, detailed skin texture"),
    "crayon": ("Fait main", "Dessin au crayon sur papier",
               "monochrome graphite pencil drawing, grayscale only, no color, hand-drawn sketch on paper, "
               "cross-hatching, visible pencil strokes, head and shoulders portrait"),
}


def style_valide(style):
    """Identifiant d'un style de STYLES, ou "" (style par défaut : [portraits] style de config.toml)."""
    style = str(style or "").strip().lower()
    return style if style in STYLES else ""


def styles():
    """[{id, nom, resume}] des styles proposés, pour la page de préparation."""
    return [{"id": i, "nom": nom, "resume": resume} for i, (nom, resume, _) in STYLES.items()]
SCHEMA = {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"],
          "additionalProperties": False}
CONSIGNES = ("Tu écris la description d'un portrait pour un générateur d'images. Réponds en JSON {\"prompt\": ...} : "
             "une seule phrase en anglais, 40 mots au plus, qui décrit ce qu'on voit du personnage : son âge en "
             "chiffres (ex. « in her fifties »), sa corpulence, son visage, ses cheveux, son expression, des vêtements "
             "d'époque couvrants et les accessoires de son métier. Pas de nom propre, pas de décor, pas de texte.")
GENRES = {"feminin": "woman", "masculin": "man", "neutre": "person"}
TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
TAILLE_MAX = 8_000_000  # octets d'une image reçue


class PortraitIndisponible(Exception):
    """Message destiné à l'utilisateur : moteur désactivé, paquet ou modèle absent, réseau coupé…"""


def description(npc):
    """Ce que le modèle de langage sait du personnage pour décrire son portrait."""
    champs = [("Métier", "metier"), ("Genre", "genre"), ("Apparence", "apparence"), ("Personnalité", "personnalite"),
              ("Humeur", "humeur")]
    return "\n".join(f"{titre} : {npc[cle]}" for titre, cle in champs if str(npc.get(cle) or "").strip())


def prompt_portrait(moteurs, npc, style=STYLE):
    """Style puis description anglaise du portrait (le générateur donne plus de poids au début : le style passe
    devant). Repli sans modèle de langage : genre, métier, apparence."""
    sujet = ""
    try:
        sujet = str(parse_json(moteurs.fiche(CONSIGNES, description(npc), SCHEMA)).get("prompt") or "")
    except (MoteurIndisponible, ValueError, AttributeError, TypeError) as e:
        log.info("Description du portrait tirée directement de la fiche (%s)", e)
    if not sujet.strip():
        parties = [GENRES.get(npc.get("genre"), "person"), npc.get("metier"), npc.get("apparence")]
        sujet = ", ".join(str(p).strip() for p in parties if str(p or "").strip())
    sujet = " ".join(sujet.split())[:500]
    return f"{style}, {sujet}" if style else sujet


def type_image(octets):
    """Extension d'après les premiers octets (png, jpg, webp), ou None si ce n'est pas une image reconnue."""
    if octets.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if octets.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if octets[:4] == b"RIFF" and octets[8:12] == b"WEBP":
        return "webp"
    return None


class Aucun:
    nom = "aucun"

    def disponible(self):
        return False

    def generer(self, prompt, graine):
        raise PortraitIndisponible("Portraits désactivés : choisissez un moteur dans [portraits] de config.toml.")


class EnLigne:
    """Pollinations : une simple adresse web renvoie l'image (gratuit, sans clé). L'accès gratuit est limité
    (une image toutes les 45 s par adresse IP en novembre 2026 : réponse 402 ou 429 avec Retry-After) : on attend
    puis on réessaie une fois si l'attente demandée ne dépasse pas `attente_max` secondes."""
    nom = "en_ligne"
    URL = "https://image.pollinations.ai/prompt/"

    def __init__(self, cfg, dormir=time.sleep):
        self.url = cfg.get("url", self.URL)
        self.taille = int(cfg.get("taille", 512))
        self.delai = float(cfg.get("delai", 120))
        self.attente_max = float(cfg.get("attente_max", 60))
        self.dormir = dormir  # remplacé dans les tests

    def disponible(self):
        return True

    def adresse(self, prompt, graine):
        parametres = {"width": self.taille, "height": self.taille, "seed": graine, "nologo": "true"}
        return f"{self.url}{urllib.parse.quote(prompt, safe='')}?{urllib.parse.urlencode(parametres)}"

    def _telecharger(self, adresse):
        requete = urllib.request.Request(adresse, headers={"User-Agent": "pnj-parlant"})
        with urllib.request.urlopen(requete, timeout=self.delai) as r:
            return r.read(TAILLE_MAX + 1)

    def generer(self, prompt, graine):
        adresse = self.adresse(prompt, graine)
        try:
            try:
                octets = self._telecharger(adresse)
            except urllib.error.HTTPError as e:
                attente = attente_demandee(e)
                if attente is None or attente > self.attente_max:
                    raise
                log.info("Pollinations : limite gratuite, nouvel essai dans %s s", attente)
                self.dormir(attente)
                octets = self._telecharger(adresse)
        except urllib.error.HTTPError as e:
            attente = attente_demandee(e)
            if attente is not None:
                raise PortraitIndisponible("Le service gratuit de portraits limite le rythme (une image toutes les "
                                           f"45 s environ) : réessayez dans {round(attente)} s.") from e
            raise PortraitIndisponible(f"Le service de portraits en ligne a refusé la demande (erreur {e.code}).") from e
        except OSError as e:
            raise PortraitIndisponible("Le service de portraits en ligne ne répond pas (réseau coupé ?).") from e
        ext = type_image(octets)
        if not ext or len(octets) > TAILLE_MAX:
            raise PortraitIndisponible("Le service de portraits en ligne a renvoyé autre chose qu'une image.")
        return octets, ext


def attente_demandee(erreur):
    """Secondes à attendre si la réponse HTTP est une limite de rythme (402, 429, 503 avec Retry-After), sinon None."""
    if erreur.code not in (402, 429, 503):
        return None
    try:
        return max(1.0, float(erreur.headers.get("Retry-After", "")))
    except (TypeError, ValueError, AttributeError):
        return 45.0 if erreur.code in (402, 429) else None


class Local:
    """Stable Diffusion Turbo (diffusers) : une image 512×512 en 1 à 4 étapes, sur la carte NVIDIA si elle est
    disponible, sinon sur le processeur (de 20 s à 1 min). Chargé à la première génération, puis gardé."""
    nom = "local"

    def __init__(self, cfg):
        self.modele = cfg.get("modele", "stabilityai/sd-turbo")
        self.etapes = int(cfg.get("etapes", 2))
        self.taille = int(cfg.get("taille", 512))
        self.appareil = cfg.get("appareil", "auto")
        self._pipe = None
        self._verrou = threading.Lock()  # une génération à la fois

    def disponible(self):
        return all(importlib.util.find_spec(m) for m in ("torch", "diffusers", "transformers"))

    def _charger(self):
        import torch  # pylint: disable=import-outside-toplevel
        from diffusers import AutoPipelineForText2Image  # pylint: disable=import-outside-toplevel
        appareil = self.appareil
        if appareil == "auto":
            appareil = "cuda" if torch.cuda.is_available() else "cpu"
        # poids en 16 bits (téléchargement deux fois plus petit), calcul en 32 bits sur le processeur
        dtype = torch.float16 if appareil == "cuda" else torch.float32
        log.info("Chargement de %s sur %s", self.modele, appareil)
        pipe = AutoPipelineForText2Image.from_pretrained(self.modele, torch_dtype=dtype, variant="fp16")
        pipe = pipe.to(appareil)
        if appareil == "cuda":
            pipe.enable_attention_slicing()  # tient dans 4 Go de mémoire vidéo
        pipe.set_progress_bar_config(disable=True)
        self._pipe, self._appareil = pipe, appareil
        return pipe

    def generer(self, prompt, graine):
        if not self.disponible():
            raise PortraitIndisponible("Portraits locaux : installez l'option portraits (uv sync --extra tout "
                                       "--extra portraits).")
        with self._verrou:
            try:
                pipe = self._pipe or self._charger()
            except OSError as e:
                raise PortraitIndisponible(f"Modèle « {self.modele} » introuvable : la première génération le "
                                           "télécharge (réseau nécessaire, environ 2,5 Go).") from e
            import torch  # pylint: disable=import-outside-toplevel
            hasard = torch.Generator(device=self._appareil).manual_seed(graine)
            image = pipe(prompt=prompt, num_inference_steps=self.etapes, guidance_scale=0.0,
                         width=self.taille, height=self.taille, generator=hasard).images[0]
        tampon = io.BytesIO()
        image.save(tampon, format="PNG")
        return tampon.getvalue(), "png"


def charger(cfg):
    """Moteur de portraits d'après la section [portraits] de config.toml."""
    moteur = cfg.get("moteur", "aucun")
    if moteur == "local":
        local = Local(cfg.get("local", {}))
        if not local.disponible():
            log.warning("[portraits] moteur = \"local\" : paquets absents (uv sync --extra tout --extra portraits).")
        return local
    if moteur == "en_ligne":
        return EnLigne(cfg.get("en_ligne", {}))
    if moteur != "aucun":
        log.warning("[portraits] moteur inconnu : %s (aucun, local ou en_ligne)", json.dumps(moteur))
    return Aucun()
