"""
Banque de PNJ et scénario : un fichier JSON par personnage, lisible et modifiable à la main.

    pnj/_scenario.json      {"monde", "notes_mj", "theme", "style_portrait"}  (« _ » : jamais pris pour un PNJ)
    pnj/_lieux.json         [{"id", "nom", "description", "notes_mj"}, ...]
    pnj/_styles.json        thèmes et styles de portrait créés ou modifiés pour l'univers (voir valider_styles)
    pnj/<nom>-<hex>.json    fiche d'un PNJ
    pnj/<nom>-<hex>.png     son portrait, facultatif (.png, .jpg ou .webp)
    pnj/_aventurier-<nom>-<hex>.json   fiche d'un aventurier (personnage d'un joueur, voir aventuriers.py),
    pnj/_aventurier-<nom>-<hex>.png    et son portrait ; « _ » : jamais pris pour un PNJ, même par une version
                                       qui ne connaît pas les aventuriers

Un scénario complet (scénario, lieux, PNJ, aventuriers) s'exporte en zip et s'importe depuis un zip ou un dossier.
"""
import copy
import io
import json
import os
import re
import secrets
import tempfile
import threading
import time
import unicodedata
import zipfile
from pathlib import PurePosixPath

from .aventuriers import normaliser as normaliser_aventurier
from .portraits import style_valide, type_image

NPC_ID = re.compile(r"^[a-z0-9-]{1,80}$")  # protège contre les chemins arbitraires
THEME = re.compile(r"^[a-z0-9-]{1,40}$")   # thème graphique : identifiant défini dans static/style.css
SCENARIO, LIEUX, STYLES_UNIVERS = "_scenario.json", "_lieux.json", "_styles.json"
AVENTURIER = "_aventurier-"  # préfixe des fichiers d'un aventurier
AVENTURIERS_MAX = 50
COULEURS = ("bg", "surface", "ink", "muted", "line", "glass", "verdigris", "wax", "wax-ink")  # voir style.css
COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")
MODES = ("auto", "sombre", "clair")  # auto : palettes claire et sombre selon l'appareil
STYLES_MAX = 30                       # thèmes, et styles de portrait, par univers
IMPORT_MAX_FICHIERS = 500
IMPORT_MAX_OCTETS = 60_000_000  # contenu décompressé (portraits compris) : protège contre les archives piégées
IMAGES = ("png", "jpg", "webp")  # portraits des PNJ


def sans_accents(texte):
    return unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()


def slug(texte, defaut="pnj"):
    """« Forge de Brom » → « forge-de-brom »."""
    return re.sub(r"[^a-z0-9]+", "-", sans_accents(texte).lower()).strip("-")[:60] or defaut


def _ecrire(chemin, octets):
    """Écrit `octets` dans `chemin` par remplacement atomique : fichier temporaire dans le même dossier, puis
    os.replace. Un lecteur voit l'ancien contenu ou le nouveau, jamais un fichier vide ; un plantage ne perd rien.
    Le fichier temporaire est supprimé si l'écriture échoue."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=".tmp-", suffix=chemin.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(octets)
        for essai in range(20):  # Windows : refusé tant qu'un lecteur a le fichier ouvert (quelques millisecondes)
            try:
                os.replace(tmp, chemin)
                break
            except PermissionError:
                if essai == 19:
                    raise
                time.sleep(0.01)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _lire(chemin):
    """Texte d'un fichier de la banque. Windows refuse la lecture pendant le remplacement du fichier (quelques
    millisecondes) : on réessaie avant de laisser passer l'erreur."""
    for essai in range(20):
        try:
            return chemin.read_text(encoding="utf-8")
        except PermissionError:
            if essai == 19:
                raise
            time.sleep(0.01)


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


FICHE_TEXTES = {"nom": 80, "metier": 120, "apparence": 600, "personnalite": 600, "humeur": 120,
                "secret": 1500, "salutation": 600}
FICHE_ENUMS = {"genre": ("feminin", "masculin", "neutre"), "timbre": ("grave", "moyen", "aigu"),
               "debit": ("lent", "normal", "rapide")}
CONNAISSANCES_MAX, CONNAISSANCE_LONGUEUR = 30, 600


def _chaine(valeur):
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return str(valeur)
    return ""


def normaliser_fiche(npc):
    """Fiche d'un PNJ aux champs sûrs, pour l'enregistrer ou l'importer : textes de longueur bornée (null, liste ou
    objet deviennent vides), `lieu` texte s'il est présent, `connaissances` = liste de chaînes non vides en nombre
    borné, genre, timbre et débit parmi leurs valeurs permises (sinon retirés : la voix se réattribue).
    Les autres champs (voix…) sont gardés."""
    propre = dict(npc)
    for cle, longueur in FICHE_TEXTES.items():
        propre[cle] = _chaine(propre.get(cle)).strip()[:longueur]
    if "lieu" in propre:
        propre["lieu"] = _chaine(propre["lieu"]).strip()[:80]
    connaissances = propre.get("connaissances")
    propre["connaissances"] = ([c.strip()[:CONNAISSANCE_LONGUEUR] for c in map(_chaine, connaissances) if c.strip()]
                               [:CONNAISSANCES_MAX] if isinstance(connaissances, list) else [])
    for cle, valeurs in FICHE_ENUMS.items():
        if propre.get(cle) not in valeurs:
            propre.pop(cle, None)
    return propre


def _texte(valeur, longueur):
    return " ".join(str(valeur or "").split())[:longueur]


def valider_styles(data):
    """Thèmes et styles de portrait de l'univers, vérifiés ; lève ValueError (message pour l'utilisateur).
        {"themes": {id: {nom, resume, mode, clair: {couleur: "#rrggbb"}, sombre: {...}}},
         "portraits": {id: {nom, resume, prompt}}}
    Un identifiant prédéfini (thème de style.css, style de portraits.STYLES) le remplace pour cet univers.
    mode « auto » : deux palettes ; « sombre » ou « clair » : la seule palette de ce nom."""
    if not isinstance(data, dict):
        raise ValueError("Styles illisibles.")
    themes, portraits = {}, {}
    for tid, t in (data.get("themes") or {}).items():
        if not THEME.fullmatch(str(tid)) or not isinstance(t, dict):
            raise ValueError(f"Identifiant de thème invalide : {tid}.")
        nom, mode = _texte(t.get("nom"), 60), t.get("mode", "auto")
        if not nom:
            raise ValueError("Chaque thème a besoin d'un nom.")
        if mode not in MODES:
            raise ValueError(f"Thème « {nom} » : mode inconnu.")
        theme = {"nom": nom, "resume": _texte(t.get("resume"), 120), "mode": mode}
        for palette in ("clair", "sombre") if mode == "auto" else (mode,):
            couleurs = t.get(palette)
            if not isinstance(couleurs, dict) or not all(COULEUR.match(str(couleurs.get(c, ""))) for c in COULEURS):
                raise ValueError(f"Thème « {nom} » : couleurs incomplètes ou invalides.")
            theme[palette] = {c: couleurs[c].lower() for c in COULEURS}
        themes[tid] = theme
    for sid, st in (data.get("portraits") or {}).items():
        if not THEME.fullmatch(str(sid)) or not isinstance(st, dict):
            raise ValueError(f"Identifiant de style invalide : {sid}.")
        nom, prompt = _texte(st.get("nom"), 60), _texte(st.get("prompt"), 600)
        if not nom or not prompt:
            raise ValueError("Chaque style de portrait a besoin d'un nom et d'une description.")
        portraits[sid] = {"nom": nom, "resume": _texte(st.get("resume"), 160), "prompt": prompt}
    if len(themes) > STYLES_MAX or len(portraits) > STYLES_MAX:
        raise ValueError(f"Au plus {STYLES_MAX} thèmes et {STYLES_MAX} styles de portrait par univers.")
    return {"themes": themes, "portraits": portraits}


def theme_valide(theme):
    """Identifiant de thème graphique, ou "" (thème par défaut) s'il est absent ou mal formé."""
    theme = str(theme or "").strip().lower()
    return theme if THEME.fullmatch(theme) else ""


LIEUX_MAX = 60


class Banque:
    def __init__(self, dossier):
        self.dossier = dossier
        self.scenario_path = dossier / SCENARIO
        self.lieux_path = dossier / LIEUX
        self._verrou = threading.RLock()  # opérations composées (import, vider, portrait) : une à la fois
        self._memo = {}  # scénario, lieux, styles lus : {nom: (signature des fichiers, valeur)}, voir _en_cache
        self._verrou_memo = threading.Lock()

    @staticmethod
    def _signature(chemin):
        """Date, taille et numéro du fichier (un remplacement atomique en crée un nouveau) ; None s'il manque."""
        try:
            s = chemin.stat()
        except OSError:
            return None
        return (s.st_mtime_ns, s.st_size, s.st_ino)

    def _en_cache(self, nom, chemins, calculer):
        """Valeur de `calculer()`, gardée tant que les fichiers `chemins` n'ont pas changé (relus à chaque réplique
        sinon). Invalidé par la signature des fichiers, donc aussi par une modification faite à la main, et par
        nos propres écritures (`_invalider`). Chaque appelant reçoit sa copie : il peut la modifier."""
        signature = tuple(self._signature(c) for c in chemins)
        with self._verrou_memo:
            trouve = self._memo.get(nom)
        if trouve and trouve[0] == signature:
            return copy.deepcopy(trouve[1])
        valeur = calculer()
        with self._verrou_memo:
            self._memo[nom] = (signature, valeur)
        return copy.deepcopy(valeur)

    def _invalider(self):
        with self._verrou_memo:
            self._memo.clear()

    def _ecrire(self, chemin, octets):
        _ecrire(chemin, octets)
        self._invalider()
    # --- Scénario ---------------------------------------------------------------
    def scenario(self):
        """{"monde": connu de tous les PNJ, "notes_mj": réservé à la création des PNJ,
        "theme": thème graphique des pages ("" : thème par défaut),
        "style_portrait": style de dessin des portraits (portraits.STYLES, "" : style par défaut)}."""
        return self._en_cache("scenario", (self.scenario_path, self.dossier / STYLES_UNIVERS), self._lire_scenario)

    def _lire_scenario(self):
        try:
            data = json.loads(_lire(self.scenario_path))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {"monde": data.get("monde", ""), "notes_mj": data.get("notes_mj", ""),
                "theme": theme_valide(data.get("theme")),
                "style_portrait": style_valide(data.get("style_portrait"), self.styles()["portraits"])}

    def enregistrer_scenario(self, data):
        scenario = {k: str(data.get(k, "")).strip()[:20000] for k in ("monde", "notes_mj")}
        scenario["theme"] = theme_valide(data.get("theme"))
        scenario["style_portrait"] = style_valide(data.get("style_portrait"), self.styles()["portraits"])
        with self._verrou:
            self._ecrire(self.scenario_path, _json(scenario))
        return scenario

    # --- Lieux ------------------------------------------------------------------
    def lieux(self):
        """[{"id", "nom", "description" (publique, lue par le narrateur, connue des PNJ),
        "notes_mj" (secrets du lieu, servent seulement à la création des PNJ)}]."""
        return self._en_cache("lieux", (self.lieux_path,), self._lire_lieux)

    def _lire_lieux(self):
        try:
            data = json.loads(_lire(self.lieux_path))
        except (OSError, ValueError):
            return []
        return [lieu for lieu in data if isinstance(lieu, dict) and lieu.get("id") and lieu.get("nom")] \
            if isinstance(data, list) else []

    def lieu(self, lieu_id):
        return next((lieu for lieu in self.lieux() if lieu["id"] == lieu_id), None) if lieu_id else None

    def enregistrer_lieux(self, liste):
        """Remplace la liste des lieux. Un lieu garde son identifiant (les PNJ y sont rattachés) ;
        un nouveau lieu en reçoit un, tiré de son nom. Les lieux sans nom sont ignorés."""
        lieux, pris = [], set()
        for item in (liste if isinstance(liste, list) else [])[:LIEUX_MAX]:
            if not isinstance(item, dict) or not str(item.get("nom") or "").strip():
                continue
            nom = str(item["nom"]).strip()[:80]
            lieu_id = str(item.get("id") or "")
            if not NPC_ID.fullmatch(lieu_id) or lieu_id in pris:
                base = lieu_id = slug(nom, "lieu")
                n = 2
                while lieu_id in pris:
                    lieu_id, n = f"{base}-{n}", n + 1
            pris.add(lieu_id)
            lieux.append({"id": lieu_id, "nom": nom,
                          "description": str(item.get("description") or "").strip()[:2000],
                          "notes_mj": str(item.get("notes_mj") or "").strip()[:4000]})
        with self._verrou:
            self._ecrire(self.lieux_path, _json(lieux))
        return lieux

    # --- Thèmes et styles de portrait de l'univers -------------------------------------
    def styles(self):
        """Thèmes et styles créés ou modifiés pour l'univers (voir valider_styles) ; vides si absents ou abîmés."""
        return self._en_cache("styles", (self.dossier / STYLES_UNIVERS,), self._lire_styles)

    def _lire_styles(self):
        try:
            return valider_styles(json.loads(_lire(self.dossier / STYLES_UNIVERS)))
        except (OSError, ValueError):
            return {"themes": {}, "portraits": {}}

    def enregistrer_styles(self, data):
        """Remplace les thèmes et styles de l'univers ; lève ValueError s'ils sont invalides."""
        styles = valider_styles(data)
        with self._verrou:
            self._ecrire(self.dossier / STYLES_UNIVERS, _json(styles))
        return styles

    # --- PNJ --------------------------------------------------------------------
    def chemin(self, npc_id):
        """Fichier du PNJ, ou None si l'identifiant est invalide."""
        if not isinstance(npc_id, str) or not NPC_ID.fullmatch(npc_id):
            return None
        return self.dossier / f"{npc_id}.json"

    def existe(self, npc_id):
        chemin = self.chemin(npc_id)
        return bool(chemin and chemin.exists())

    def liste(self):
        """[{"id", "nom", "metier"}] triée par nom."""
        items = []
        for f in sorted(self.dossier.glob("*.json")) if self.dossier.exists() else []:
            if f.stem.startswith("_"):
                continue  # _scenario.json
            try:
                npc = json.loads(_lire(f))
            except (OSError, ValueError):
                continue  # fichier abîmé ou en cours d'édition : on l'ignore
            if not isinstance(npc, dict):
                continue  # JSON valide mais pas une fiche
            items.append({"id": f.stem, "nom": npc.get("nom", f.stem), "metier": npc.get("metier", ""),
                          "lieu": npc.get("lieu", ""),  # lieu habituel
                          "portrait": self.version_portrait(f.stem)})
        return sorted(items, key=lambda n: sans_accents(n["nom"]).lower())  # « Ébène » avant « Ysolde »

    def lire(self, npc_id):
        """Fiche du PNJ (avec son "id" et "portrait" : voir version_portrait), ou None s'il n'existe pas."""
        if not self.existe(npc_id):
            return None
        try:
            npc = json.loads(_lire(self.chemin(npc_id)))
        except (OSError, ValueError):
            return None  # fichier abîmé : comme un PNJ introuvable, pas une erreur 500
        if not isinstance(npc, dict):
            return None
        npc["id"] = npc_id
        npc["portrait"] = self.version_portrait(npc_id)
        return npc

    def ecrire(self, npc_id, npc):
        npc = {k: v for k, v in npc.items() if k not in ("id", "portrait")}
        with self._verrou:
            _ecrire(self.chemin(npc_id), _json(npc))

    def ajouter(self, npc):
        """Enregistre un nouveau PNJ et renvoie son identifiant (nom sans accents + 4 chiffres hexa)."""
        npc_id = f"{slug(npc.get('nom', 'pnj'))}-{secrets.token_hex(2)}"
        self.ecrire(npc_id, npc)
        return npc_id

    def supprimer(self, npc_id):
        """Vrai si le PNJ existait."""
        with self._verrou:
            if not self.existe(npc_id):
                return False
            self.chemin(npc_id).unlink()
            self.supprimer_portrait(npc_id)
            return True

    # --- Portraits (d'un PNJ ; d'un aventurier avec prefixe=AVENTURIER) -----------------
    def portrait(self, npc_id, prefixe=""):
        """Fichier du portrait du PNJ, ou None s'il n'en a pas."""
        if not isinstance(npc_id, str) or not NPC_ID.fullmatch(npc_id):
            return None
        return next((p for ext in IMAGES if (p := self.dossier / f"{prefixe}{npc_id}.{ext}").exists()), None)

    def version_portrait(self, npc_id, prefixe=""):
        """Version du portrait (date du fichier en millisecondes), 0 s'il n'y en a pas : sert à l'adresse de
        l'image, pour que le navigateur la garde en cache sans montrer un ancien portrait."""
        chemin = self.portrait(npc_id, prefixe)
        return chemin.stat().st_mtime_ns // 1_000_000 if chemin else 0

    def enregistrer_portrait(self, npc_id, octets, ext, prefixe=""):
        """Remplace le portrait du PNJ (`ext` : png, jpg ou webp). Renvoie faux, sans rien écrire, si la fiche du PNJ
        n'existe plus (supprimé pendant la génération) : pas de portrait orphelin."""
        if not isinstance(npc_id, str) or not NPC_ID.fullmatch(npc_id) or ext not in IMAGES:
            raise ValueError("Portrait invalide.")
        with self._verrou:
            if not (self.dossier / f"{prefixe}{npc_id}.json").exists():
                return False
            self.supprimer_portrait(npc_id, prefixe)
            _ecrire(self.dossier / f"{prefixe}{npc_id}.{ext}", octets)
            return True

    def supprimer_portrait(self, npc_id, prefixe=""):
        """Vrai si le PNJ avait un portrait."""
        with self._verrou:
            chemin = self.portrait(npc_id, prefixe)
            if chemin:
                chemin.unlink()
            return chemin is not None

    # --- Aventuriers (personnages des joueurs) -------------------------------------
    def chemin_aventurier(self, av_id):
        """Fichier de l'aventurier, ou None si l'identifiant est invalide."""
        if not isinstance(av_id, str) or not NPC_ID.fullmatch(av_id):
            return None
        return self.dossier / f"{AVENTURIER}{av_id}.json"

    def aventuriers(self):
        """Fiches de tous les aventuriers (normalisées, avec "id" et "portrait"), triées par nom."""
        fiches = []
        for f in sorted(self.dossier.glob(f"{AVENTURIER}*.json")) if self.dossier.exists() else []:
            fiche = self.lire_aventurier(f.stem[len(AVENTURIER):])
            if fiche and fiche["nom"]:
                fiches.append(fiche)
        return sorted(fiches, key=lambda a: sans_accents(a["nom"]).lower())

    def lire_aventurier(self, av_id):
        """Fiche de l'aventurier (normalisée, avec "id" et "portrait"), ou None s'il n'existe pas ou est abîmé."""
        chemin = self.chemin_aventurier(av_id)
        if not chemin or not chemin.exists():
            return None
        try:
            data = json.loads(_lire(chemin))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return {**normaliser_aventurier(data), "id": av_id, "portrait": self.version_portrait(av_id, AVENTURIER)}

    def ecrire_aventurier(self, av_id, av):
        """Écrit la fiche (normalisée) ; renvoie l'identifiant."""
        with self._verrou:
            _ecrire(self.chemin_aventurier(av_id), _json(normaliser_aventurier(av)))
        return av_id

    def ajouter_aventurier(self, av):
        """Nouvel aventurier ; lève ValueError s'il y en a déjà AVENTURIERS_MAX."""
        existants = list(self.dossier.glob(f"{AVENTURIER}*.json")) if self.dossier.exists() else []
        if len(existants) >= AVENTURIERS_MAX:
            raise ValueError(f"Au plus {AVENTURIERS_MAX} aventuriers par univers.")
        av = normaliser_aventurier(av)
        return self.ecrire_aventurier(f"{slug(av['nom'], 'aventurier')}-{secrets.token_hex(2)}", av)

    def _ids_aventuriers(self):
        """Identifiants de tous les fichiers d'aventurier, même abîmés."""
        fichiers = self.dossier.glob(f"{AVENTURIER}*.json") if self.dossier.exists() else []
        return [f.stem[len(AVENTURIER):] for f in fichiers if NPC_ID.fullmatch(f.stem[len(AVENTURIER):])]

    def supprimer_aventurier(self, av_id):
        """Vrai si l'aventurier existait (son portrait part avec lui)."""
        with self._verrou:
            chemin = self.chemin_aventurier(av_id)
            if not chemin or not chemin.exists():
                return False
            chemin.unlink()
            self.supprimer_portrait(av_id, AVENTURIER)
            return True

    def vider(self):
        """Nouvelle table : supprime tous les PNJ et les aventuriers, vide le scénario (thème compris), les lieux,
        les thèmes et styles de l'univers. Renvoie le nombre de PNJ supprimés."""
        with self._verrou:
            pnjs = self.liste()
            for item in pnjs:
                self.supprimer(item["id"])
            for av in self._ids_aventuriers():
                self.supprimer_aventurier(av)
            self.enregistrer_styles({})
            self.enregistrer_scenario({})
            self.enregistrer_lieux([])
            return len(pnjs)

    # --- Export et import d'un scénario complet ------------------------------------
    def exporter_zip(self):
        """Archive zip à plat : _scenario.json, _lieux.json, _styles.json, une fiche JSON par PNJ et son portrait."""
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
            for f in sorted(self.dossier.iterdir()) if self.dossier.exists() else []:
                if f.name in (SCENARIO, LIEUX, STYLES_UNIVERS) or (  # PNJ et aventuriers, fiches et portraits
                        NPC_ID.fullmatch(f.stem.removeprefix(AVENTURIER)) and f.suffix[1:] in ("json", *IMAGES)):
                    archive.write(f, f.name)
        return tampon.getvalue()

    def importer(self, fichiers, remplacer=True):
        """Copie un scénario dans la banque. `fichiers` : {nom de fichier: octets} (voir `lire_zip`).
        remplacer : les PNJ actuels absents de l'import sont supprimés (après l'écriture des nouveaux : une erreur
        disque ne laisse pas une banque à moitié vide) et le scénario et les lieux absents de l'import sont vidés ;
        sinon les PNJ importés s'ajoutent (même identifiant : remplacé) et seuls le scénario et les lieux fournis
        remplacent les actuels. Tout est vérifié avant d'écrire quoi que ce soit.
        Les portraits (<id du PNJ>.png, .jpg, .webp) suivent leur fiche ; un portrait sans fiche est ignoré.
        Les thèmes et styles de l'univers (_styles.json) suivent la même règle que le scénario ; les aventuriers
        (_aventurier-<id>.json et leur portrait), celle des PNJ.
        Renvoie {"scenario": bool, "lieux": nombre, "pnj": nombre, "aventuriers": nombre, "ignores": [noms]}."""
        scenario, lieux, styles, pnjs, aventuriers, ignores = None, None, None, {}, {}, []
        images, ids = {}, {}  # portraits : nom du fichier sans extension → (octets, ext) ; nom de fiche → id
        for nom, octets in fichiers.items():
            stem, _, ext = nom.rpartition(".")
            if ext.lower() in ("png", "jpg", "jpeg", "webp"):
                if type_image(octets):
                    images[stem] = (octets, type_image(octets))
                else:
                    ignores.append(nom)
                continue
            try:
                data = json.loads(octets.decode("utf-8-sig"))
            except (UnicodeDecodeError, ValueError):
                ignores.append(nom)
                continue
            stem = nom[:-5] if nom.lower().endswith(".json") else nom
            if nom == SCENARIO and isinstance(data, dict):
                scenario = data
            elif nom == LIEUX and isinstance(data, list):
                lieux = data
            elif nom == STYLES_UNIVERS:
                try:
                    styles = valider_styles(data)
                except ValueError:
                    ignores.append(nom)
            elif (stem.startswith(AVENTURIER) and isinstance(data, dict)
                  and normaliser_aventurier(data)["nom"]):
                av_id = stem[len(AVENTURIER):]
                if not NPC_ID.fullmatch(av_id):  # renommé à la main
                    av_id = f"{slug(normaliser_aventurier(data)['nom'], 'aventurier')}-{secrets.token_hex(2)}"
                aventuriers[av_id] = normaliser_aventurier(data)
                ids[stem] = AVENTURIER + av_id  # son portrait le suit
            elif not stem.startswith("_") and isinstance(data, dict) and str(data.get("nom") or "").strip():
                # fichier renommé à la main : il reçoit un identifiant valide, tiré du nom du PNJ
                npc_id = stem if NPC_ID.fullmatch(stem) else f"{slug(data['nom'])}-{secrets.token_hex(2)}"
                pnjs[npc_id] = normaliser_fiche(data)
                ids[stem] = npc_id
            else:
                ignores.append(nom)
        if scenario is None and lieux is None and not pnjs and not aventuriers:
            raise ValueError("Aucun scénario, lieu ni PNJ reconnu dans les fichiers.")
        if len(aventuriers) > AVENTURIERS_MAX:
            raise ValueError(f"Au plus {AVENTURIERS_MAX} aventuriers par univers.")

        with self._verrou:
            if styles is not None or remplacer:  # avant le scénario : son style de portrait peut en venir
                self.enregistrer_styles(styles or {})
            if scenario is not None or remplacer:
                self.enregistrer_scenario(scenario or {})
            nb_lieux = (len(self.enregistrer_lieux(lieux or [])) if lieux is not None or remplacer
                        else len(self.lieux()))
            for npc_id, npc in pnjs.items():
                self.ecrire(npc_id, npc)
                self.supprimer_portrait(npc_id)  # celui d'avant ne correspond plus à la fiche importée
            for av_id, av in aventuriers.items():
                self.ecrire_aventurier(av_id, av)
                self.supprimer_portrait(av_id, AVENTURIER)
            for stem, (octets, ext) in images.items():
                if stem in ids:
                    cible = ids[stem]
                    if cible.startswith(AVENTURIER):
                        self.enregistrer_portrait(cible[len(AVENTURIER):], octets, ext, AVENTURIER)
                    else:
                        self.enregistrer_portrait(cible, octets, ext)
                else:
                    ignores.append(f"{stem}.{ext}")
            if remplacer:  # en dernier : tout ce qui est écrit plus haut est déjà en sécurité
                for item in self.liste():
                    if item["id"] not in pnjs:
                        self.supprimer(item["id"])
                for av_id in self._ids_aventuriers():
                    if av_id not in aventuriers:
                        self.supprimer_aventurier(av_id)
        return {"scenario": scenario is not None, "lieux": nb_lieux, "pnj": len(pnjs),
                "aventuriers": len(aventuriers), "ignores": sorted(ignores)}


def nom_de_fichier(chemin):
    """« pre-novice/lyse.json » ou « C:\\x\\lyse.json » → « lyse.json » : seul le nom compte, jamais le chemin."""
    return PurePosixPath(str(chemin).replace("\\", "/")).name


def lire_zip(octets):
    """{nom: octets} des fiches (.json) et portraits d'une archive (sous-dossiers aplatis), avec limites de taille."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(octets))
    except zipfile.BadZipFile as e:
        raise ValueError("Ce fichier n'est pas une archive zip valide.") from e
    with archive:
        infos = [i for i in archive.infolist() if not i.is_dir() and "__MACOSX" not in i.filename
                 and i.filename.lower().endswith((".json", ".png", ".jpg", ".jpeg", ".webp"))]
        if len(infos) > IMPORT_MAX_FICHIERS or sum(i.file_size for i in infos) > IMPORT_MAX_OCTETS:
            raise ValueError("Archive trop volumineuse pour un scénario.")
        fichiers = {}
        for info in infos:
            nom = nom_de_fichier(info.filename)
            if nom in fichiers:
                raise ValueError(f"Deux fichiers « {nom} » dans l'archive : un seul scénario à la fois.")
            fichiers[nom] = archive.read(info)
        return fichiers
