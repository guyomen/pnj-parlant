"""
Banque de PNJ et scénario : un fichier JSON par personnage, lisible et modifiable à la main.

    pnj/_scenario.json      {"monde", "notes_mj", "theme", "style_portrait"}  (« _ » : jamais pris pour un PNJ)
    pnj/_lieux.json         [{"id", "nom", "description", "notes_mj"}, ...]
    pnj/<nom>-<hex>.json    fiche d'un PNJ
    pnj/<nom>-<hex>.png     son portrait, facultatif (.png, .jpg ou .webp)

Un scénario complet (scénario, lieux, PNJ) s'exporte en zip et s'importe depuis un zip ou un dossier.
"""
import io
import json
import re
import secrets
import unicodedata
import zipfile
from pathlib import PurePosixPath

from .portraits import style_valide, type_image

NPC_ID = re.compile(r"^[a-z0-9-]{1,80}$")  # protège contre les chemins arbitraires
THEME = re.compile(r"^[a-z0-9-]{1,40}$")   # thème graphique : identifiant défini dans static/style.css
SCENARIO, LIEUX = "_scenario.json", "_lieux.json"
IMPORT_MAX_FICHIERS = 500
IMPORT_MAX_OCTETS = 60_000_000  # contenu décompressé (portraits compris) : protège contre les archives piégées
IMAGES = ("png", "jpg", "webp")  # portraits des PNJ


def sans_accents(texte):
    return unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()


def slug(texte, defaut="pnj"):
    """« Forge de Brom » → « forge-de-brom »."""
    return re.sub(r"[^a-z0-9]+", "-", sans_accents(texte).lower()).strip("-")[:60] or defaut


def theme_valide(theme):
    """Identifiant de thème graphique, ou "" (thème par défaut) s'il est absent ou mal formé."""
    theme = str(theme or "").strip().lower()
    return theme if THEME.match(theme) else ""


LIEUX_MAX = 60


class Banque:
    def __init__(self, dossier):
        self.dossier = dossier
        self.scenario_path = dossier / "_scenario.json"
        self.lieux_path = dossier / "_lieux.json"

    # --- Scénario ---------------------------------------------------------------
    def scenario(self):
        """{"monde": connu de tous les PNJ, "notes_mj": réservé à la création des PNJ,
        "theme": thème graphique des pages ("" : thème par défaut),
        "style_portrait": style de dessin des portraits (portraits.STYLES, "" : style par défaut)}."""
        try:
            data = json.loads(self.scenario_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {"monde": data.get("monde", ""), "notes_mj": data.get("notes_mj", ""),
                "theme": theme_valide(data.get("theme")), "style_portrait": style_valide(data.get("style_portrait"))}

    def enregistrer_scenario(self, data):
        scenario = {k: str(data.get(k, "")).strip()[:20000] for k in ("monde", "notes_mj")}
        scenario["theme"] = theme_valide(data.get("theme"))
        scenario["style_portrait"] = style_valide(data.get("style_portrait"))
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.scenario_path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
        return scenario

    # --- Lieux ------------------------------------------------------------------
    def lieux(self):
        """[{"id", "nom", "description" (publique, lue par le narrateur, connue des PNJ),
        "notes_mj" (secrets du lieu, servent seulement à la création des PNJ)}]."""
        try:
            data = json.loads(self.lieux_path.read_text(encoding="utf-8"))
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
            if not NPC_ID.match(lieu_id) or lieu_id in pris:
                base = lieu_id = slug(nom, "lieu")
                n = 2
                while lieu_id in pris:
                    lieu_id, n = f"{base}-{n}", n + 1
            pris.add(lieu_id)
            lieux.append({"id": lieu_id, "nom": nom,
                          "description": str(item.get("description") or "").strip()[:2000],
                          "notes_mj": str(item.get("notes_mj") or "").strip()[:4000]})
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.lieux_path.write_text(json.dumps(lieux, ensure_ascii=False, indent=2), encoding="utf-8")
        return lieux

    # --- PNJ --------------------------------------------------------------------
    def chemin(self, npc_id):
        """Fichier du PNJ, ou None si l'identifiant est invalide."""
        if not NPC_ID.match(npc_id or ""):
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
                npc = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue  # fichier abîmé ou en cours d'édition : on l'ignore
            items.append({"id": f.stem, "nom": npc.get("nom", f.stem), "metier": npc.get("metier", ""),
                          "lieu": npc.get("lieu", ""),  # lieu habituel
                          "portrait": self.version_portrait(f.stem)})
        return sorted(items, key=lambda n: sans_accents(n["nom"]).lower())  # « Ébène » avant « Ysolde »

    def lire(self, npc_id):
        """Fiche du PNJ (avec son "id" et "portrait" : voir version_portrait), ou None s'il n'existe pas."""
        if not self.existe(npc_id):
            return None
        npc = json.loads(self.chemin(npc_id).read_text(encoding="utf-8"))
        npc["id"] = npc_id
        npc["portrait"] = self.version_portrait(npc_id)
        return npc

    def ecrire(self, npc_id, npc):
        npc = {k: v for k, v in npc.items() if k not in ("id", "portrait")}
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.chemin(npc_id).write_text(json.dumps(npc, ensure_ascii=False, indent=2), encoding="utf-8")

    def ajouter(self, npc):
        """Enregistre un nouveau PNJ et renvoie son identifiant (nom sans accents + 4 chiffres hexa)."""
        npc_id = f"{slug(npc.get('nom', 'pnj'))}-{secrets.token_hex(2)}"
        self.ecrire(npc_id, npc)
        return npc_id

    def supprimer(self, npc_id):
        """Vrai si le PNJ existait."""
        if not self.existe(npc_id):
            return False
        self.chemin(npc_id).unlink()
        self.supprimer_portrait(npc_id)
        return True

    # --- Portraits ----------------------------------------------------------------
    def portrait(self, npc_id):
        """Fichier du portrait du PNJ, ou None s'il n'en a pas."""
        if not NPC_ID.match(npc_id or ""):
            return None
        return next((p for ext in IMAGES if (p := self.dossier / f"{npc_id}.{ext}").exists()), None)

    def version_portrait(self, npc_id):
        """Version du portrait (date du fichier en millisecondes), 0 s'il n'y en a pas : sert à l'adresse de
        l'image, pour que le navigateur la garde en cache sans montrer un ancien portrait."""
        chemin = self.portrait(npc_id)
        return chemin.stat().st_mtime_ns // 1_000_000 if chemin else 0

    def enregistrer_portrait(self, npc_id, octets, ext):
        """Remplace le portrait du PNJ (`ext` : png, jpg ou webp)."""
        if not NPC_ID.match(npc_id or "") or ext not in IMAGES:
            raise ValueError("Portrait invalide.")
        self.supprimer_portrait(npc_id)
        self.dossier.mkdir(parents=True, exist_ok=True)
        (self.dossier / f"{npc_id}.{ext}").write_bytes(octets)

    def supprimer_portrait(self, npc_id):
        """Vrai si le PNJ avait un portrait."""
        chemin = self.portrait(npc_id)
        if chemin:
            chemin.unlink()
        return chemin is not None

    def vider(self):
        """Nouvelle table : supprime tous les PNJ, vide le scénario (thème compris) et les lieux.
        Renvoie le nombre de PNJ supprimés."""
        pnjs = self.liste()
        for item in pnjs:
            self.supprimer(item["id"])
        self.enregistrer_scenario({})
        self.enregistrer_lieux([])
        return len(pnjs)

    # --- Export et import d'un scénario complet ------------------------------------
    def exporter_zip(self):
        """Archive zip à plat : _scenario.json, _lieux.json, une fiche JSON par PNJ et son portrait."""
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
            for f in sorted(self.dossier.iterdir()) if self.dossier.exists() else []:
                if f.name in (SCENARIO, LIEUX) or (NPC_ID.match(f.stem) and f.suffix[1:] in ("json", *IMAGES)):
                    archive.write(f, f.name)
        return tampon.getvalue()

    def importer(self, fichiers, remplacer=True):
        """Copie un scénario dans la banque. `fichiers` : {nom de fichier: octets} (voir `lire_zip`).
        remplacer : les PNJ actuels sont supprimés et le scénario et les lieux absents de l'import sont vidés ;
        sinon les PNJ importés s'ajoutent (même identifiant : remplacé) et seuls le scénario et les lieux fournis
        remplacent les actuels. Tout est vérifié avant d'écrire quoi que ce soit.
        Les portraits (<id du PNJ>.png, .jpg, .webp) suivent leur fiche ; un portrait sans fiche est ignoré.
        Renvoie {"scenario": bool, "lieux": nombre, "pnj": nombre, "ignores": [noms]}."""
        scenario, lieux, pnjs, ignores = None, None, {}, []
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
            elif not stem.startswith("_") and isinstance(data, dict) and str(data.get("nom") or "").strip():
                # fichier renommé à la main : il reçoit un identifiant valide, tiré du nom du PNJ
                npc_id = stem if NPC_ID.match(stem) else f"{slug(data['nom'])}-{secrets.token_hex(2)}"
                pnjs[npc_id] = data
                ids[stem] = npc_id
            else:
                ignores.append(nom)
        if scenario is None and lieux is None and not pnjs:
            raise ValueError("Aucun scénario, lieu ni PNJ reconnu dans les fichiers.")

        if remplacer:
            for item in self.liste():
                self.supprimer(item["id"])
        if scenario is not None or remplacer:
            self.enregistrer_scenario(scenario or {})
        nb_lieux = len(self.enregistrer_lieux(lieux or [])) if lieux is not None or remplacer else len(self.lieux())
        for npc_id, npc in pnjs.items():
            self.ecrire(npc_id, npc)
            self.supprimer_portrait(npc_id)  # celui d'avant ne correspond plus à la fiche importée
        for stem, (octets, ext) in images.items():
            if stem in ids:
                self.enregistrer_portrait(ids[stem], octets, ext)
            else:
                ignores.append(f"{stem}.{ext}")
        return {"scenario": scenario is not None, "lieux": nb_lieux, "pnj": len(pnjs), "ignores": sorted(ignores)}


def nom_de_fichier(chemin):
    """« pre-novice/lyse.json » ou « C:\\x\\lyse.json » → « lyse.json » : seul le nom compte, jamais le chemin."""
    return PurePosixPath(str(chemin).replace("\\", "/")).name


def lire_zip(octets):
    """{nom: octets} des fiches (.json) et portraits d'une archive (sous-dossiers aplatis), avec des limites de taille."""
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
