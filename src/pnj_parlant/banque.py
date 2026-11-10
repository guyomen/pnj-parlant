"""
Banque de PNJ et scénario : un fichier JSON par personnage, lisible et modifiable à la main.

    pnj/_scenario.json      {"monde": ..., "notes_mj": ...}  (« _ » : jamais pris pour un PNJ)
    pnj/_lieux.json         [{"id", "nom", "description", "notes_mj"}, ...]
    pnj/<nom>-<hex>.json    fiche d'un PNJ
"""
import json
import re
import secrets
import unicodedata

NPC_ID = re.compile(r"^[a-z0-9-]{1,80}$")  # protège contre les chemins arbitraires


def sans_accents(texte):
    return unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()


def slug(texte, defaut="pnj"):
    """« Forge de Brom » → « forge-de-brom »."""
    return re.sub(r"[^a-z0-9]+", "-", sans_accents(texte).lower()).strip("-")[:60] or defaut


LIEUX_MAX = 60


class Banque:
    def __init__(self, dossier):
        self.dossier = dossier
        self.scenario_path = dossier / "_scenario.json"
        self.lieux_path = dossier / "_lieux.json"

    # --- Scénario ---------------------------------------------------------------
    def scenario(self):
        """{"monde": connu de tous les PNJ, "notes_mj": réservé à la création des PNJ}."""
        try:
            data = json.loads(self.scenario_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return {"monde": data.get("monde", ""), "notes_mj": data.get("notes_mj", "")}

    def enregistrer_scenario(self, data):
        scenario = {k: str(data.get(k, "")).strip()[:20000] for k in ("monde", "notes_mj")}
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
                          "lieu": npc.get("lieu", "")})  # lieu habituel
        return sorted(items, key=lambda n: sans_accents(n["nom"]).lower())  # « Ébène » avant « Ysolde »

    def lire(self, npc_id):
        """Fiche du PNJ (avec son "id"), ou None s'il n'existe pas."""
        if not self.existe(npc_id):
            return None
        npc = json.loads(self.chemin(npc_id).read_text(encoding="utf-8"))
        npc["id"] = npc_id
        return npc

    def ecrire(self, npc_id, npc):
        npc = {k: v for k, v in npc.items() if k != "id"}
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
        return True
