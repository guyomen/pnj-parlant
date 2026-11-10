"""
PoC : générateur de PNJ parlants.
- Claude Haiku ou un modèle local (Ollama) invente le PNJ (fiche JSON) puis joue son rôle.
- Piper, Pocket TTS ou Edge lit les répliques à voix haute (sinon, repli sur la voix du navigateur).
- La voix du joueur est reconnue sur le serveur par faster-whisper (sans réseau),
  ou à défaut par le navigateur (Web Speech API, qui envoie l'audio à Google ou Microsoft).

Lancement :  python app.py   puis ouvrir http://localhost:5000
Réglages :   config.toml (à créer à partir de config.toml.example)
"""
import io
import json
import random
import re
import secrets
import threading
import subprocess
import tomllib
import unicodedata
import urllib.request
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file
from num2words import num2words

import voix
from moteurs import MoteurIndisponible, Moteurs

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.toml"
if not CONFIG_PATH.exists():
    raise SystemExit("config.toml introuvable : copiez config.toml.example en config.toml "
                     "et renseignez votre clé API.")
with open(CONFIG_PATH, "rb") as f:
    CONFIG = tomllib.load(f)

HISTORIQUE = CONFIG.get("dialogue", {}).get("historique", 12)  # messages gardés pour le contexte

app = Flask(__name__, static_folder="static", static_url_path="")
moteurs = Moteurs(CONFIG)  # Claude ou modèle local, d'après la section [moteurs]
try:
    tts = voix.charger(CONFIG, BASE_DIR)  # Piper, Pocket TTS ou Edge, d'après la section [voix]
except ValueError as e:
    raise SystemExit(f"[voix] {e}")
_tts_charges = {tts.nom: tts}  # moteurs déjà chargés : on ne recharge pas Pocket TTS à chaque bascule

# --- Reconnaissance vocale locale : faster-whisper (optionnel) ---------------
try:
    from faster_whisper import WhisperModel
    WHISPER_OK = True
except ImportError:
    WHISPER_OK = False

STT_CFG = CONFIG.get("reconnaissance", {})
STT_DIR = BASE_DIR / STT_CFG.get("dossier", "modeles-stt") / STT_CFG.get("modele", "small")
_stt_model = None
_stt_lock = threading.Lock()


def stt_local():
    """Vrai si la reconnaissance locale est choisie et que le modèle est sur la machine."""
    return STT_CFG.get("moteur", "navigateur") == "local" and WHISPER_OK and (STT_DIR / "model.bin").exists()


def precharger_cuda12():
    """CTranslate2 veut CUDA 12 et cuDNN 9 : on charge ceux du paquet pip (nvidia-cublas-cu12,
    nvidia-cudnn-cu12) si le système n'a pas les siens. Sans effet s'ils sont absents."""
    import ctypes
    import site
    for racine in site.getsitepackages():
        for motif in ("nvidia/cublas/lib/libcublas.so.12", "nvidia/cudnn/lib/libcudnn.so.9"):
            for lib in Path(racine).glob(motif):
                ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)


def load_stt():
    global _stt_model
    with _stt_lock:  # deux requêtes simultanées ne chargent pas le modèle deux fois
        if _stt_model is None:
            appareil = STT_CFG.get("appareil", "cpu")
            if appareil == "cuda":
                precharger_cuda12()
            _stt_model = WhisperModel(str(STT_DIR), device=appareil,
                                      compute_type=STT_CFG.get("precision", "float16" if appareil == "cuda" else "int8"))
    return _stt_model


# --- Aléatoire injecté côté code (pour éviter les PNJ tous pareils) ----------
HUMEURS = ["jovial", "méfiant", "fatigué", "pressé", "mélancolique", "rusé",
           "nerveux", "bavard", "bougon", "rêveur", "obséquieux", "distrait"]
TRAITS = ["avare", "superstitieux", "vantard", "généreux", "curieux", "rancunier",
          "pieux", "joueur", "érudit", "paranoïaque", "sentimental", "philosophe"]
INITIALES = "ABCDEFGHIJKLMNOPRSTVZ"
METIERS = ["marchand de potions", "forgeron", "aubergiste", "garde de la porte nord",
           "herboriste", "cartographe", "passeur", "colporteur", "fossoyeur", "barde"]

GEN_SYSTEM = """Tu crées des personnages non-joueurs (PNJ) pour un jeu de rôle médiéval-fantastique.
Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour ni balises markdown, avec ces clés :
"nom" (prénom + surnom ou nom), "metier", "apparence" (une phrase), "personnalite" (une phrase),
"humeur",
"connaissances" (liste de 3 rumeurs ou informations utiles qu'il peut révéler),
"secret" (une chose qu'il cache), "salutation" (première réplique, 1 ou 2 phrases, à l'oral),
"genre" ("feminin", "masculin" ou "neutre" : le genre grammatical utilisé pour parler du personnage),
"timbre" ("grave", "moyen" ou "aigu"), "debit" ("lent", "normal" ou "rapide").
Évite les noms et clichés trop courants. Tout est en français.

Si un contexte de scénario est fourni, le PNJ s'y inscrit :
- ses connaissances, son secret et sa salutation ne citent que des lieux, personnages, factions,
  objets et événements présents dans le contexte ou dans les consignes du MJ ;
- n'invente aucun autre nom propre, à part le nom du PNJ lui-même ; reste vague plutôt que d'inventer ;
- les consignes du MJ priment sur tout le reste, y compris sur les suggestions d'humeur et de trait."""

# Schéma imposé à la réponse (sorties structurées) : garantit un JSON valide et complet.
_TEXTE = {"type": "string"}
NPC_SCHEMA = {
    "type": "object",
    "properties": {
        "nom": _TEXTE, "metier": _TEXTE, "apparence": _TEXTE, "personnalite": _TEXTE,
        "humeur": _TEXTE,
        "connaissances": {"type": "array", "items": _TEXTE},
        "secret": _TEXTE, "salutation": _TEXTE,
        "genre": {"type": "string", "enum": ["feminin", "masculin", "neutre"]},
        "timbre": {"type": "string", "enum": ["grave", "moyen", "aigu"]},
        "debit": {"type": "string", "enum": ["lent", "normal", "rapide"]},
    },
    "required": ["nom", "metier", "apparence", "personnalite", "humeur",
                 "connaissances", "secret", "salutation", "genre", "timbre", "debit"],
    "additionalProperties": False,
}


def parse_json(text):
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def clean_for_speech(text):
    """Retire didascalies *...*, markdown et emojis avant la synthèse vocale."""
    text = re.sub(r"\*[^*]*\*", "", text)
    text = re.sub(r"[#_`>]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def chiffres_en_lettres(text):
    """Écrit les nombres en toutes lettres (« 12 » → « douze »), que la synthèse vocale lit mal en chiffres."""
    def ordinal(m):
        return num2words(int(m[1]), lang="fr", to="ordinal")  # 1er → premier, 2e → deuxième

    def nombre(m):
        entier, decimales = m[1], m[2]
        if len(entier) > 15:  # trop long pour un nombre : chiffre par chiffre
            return " ".join(num2words(int(c), lang="fr") for c in entier)
        mot = num2words(int(entier), lang="fr")
        if decimales:
            if decimales.startswith("0"):  # 2,05 → deux virgule zéro cinq
                mot += " virgule " + " ".join(num2words(int(c), lang="fr") for c in decimales)
            else:
                mot += " virgule " + num2words(int(decimales), lang="fr")
        return mot

    text = re.sub(r"\b(\d+)\s?(er|re|ère|ere|e|è|ème|eme)\b", ordinal, text)
    text = re.sub(r"(?<=\d)[\u202f\u00a0 ](?=\d{3}\b)", "", text)  # « 1 000 » → « 1000 »
    return re.sub(r"(\d+)(?:[,.](\d+))?", nombre, text)


# Fin de phrase : ponctuation, éventuels guillemets ou parenthèse fermants, puis une espace
FIN_DE_PHRASE = re.compile(r"[.!?…]+[»”\"')]*\s+")
PHRASE_MIN = 40  # caractères : « Ah ! » attend la phrase suivante, pour éviter un blanc entre deux sons


def phrases(morceaux):
    """Regroupe en phrases complètes le texte qui arrive morceau par morceau,
    pour que chaque phrase soit lue pendant que le modèle écrit la suivante."""
    tampon = ""
    for morceau in morceaux:
        tampon += morceau
        while True:
            # on ne coupe pas au milieu d'une didascalie *...*, que clean_for_speech retire en entier,
            # ni d'une description (...), que le navigateur fait lire par la voix du narrateur
            fin = next((m.end() for m in FIN_DE_PHRASE.finditer(tampon)
                        if len(tampon[:m.end()].strip()) >= PHRASE_MIN
                        and tampon[:m.end()].count("*") % 2 == 0
                        and tampon[:m.end()].count("(") <= tampon[:m.end()].count(")")), None)
            if fin is None:
                break
            yield tampon[:fin]
            tampon = tampon[fin:]
    if tampon.strip():
        yield tampon


def assign_voice(npc, rng=random):
    """Choisit une voix du moteur de synthèse, du genre du PNJ, réglée d'après son timbre et son débit
    (avec aussi un réglage pour la voix du navigateur, en repli)."""
    genre = npc.get("genre")
    debit = {"lent": 1.2, "normal": 1.0, "rapide": 0.85}.get(npc.get("debit"), 1.0)
    pitch = {"grave": 0.7, "moyen": 1.0, "aigu": 1.35}.get(npc.get("timbre"), 1.0)
    pitch *= {"feminin": 1.25, "masculin": 0.85}.get(genre, 1.0)  # voix du navigateur
    voice = {"length_scale": round(debit * rng.uniform(0.95, 1.05), 2), "timbre": npc.get("timbre"),
             "browser_pitch": round(pitch, 2), "browser_rate": round(1 / debit, 2)}
    catalogue = tts.catalogue()
    if catalogue:
        # Voix du bon genre ; à défaut (PNJ neutre ou aucune voix de ce genre), n'importe laquelle.
        matching = [v for v, g in catalogue if g == genre]
        voice.update(rng.choice(matching or [v for v, _ in catalogue]))
    voice["genre"] = genre
    voice["moteur"] = tts.nom
    return voice


def ensure_voice(npc):
    """Réattribue une voix si celle du PNJ vient d'un autre moteur de synthèse, manque sur cette machine
    ou ne correspond plus à son genre."""
    v = npc.get("voix") or {}
    connues = [(c["name"], c.get("speaker")) for c, _ in tts.catalogue()]
    if (v.get("moteur", "piper") != tts.nom or (v.get("name"), v.get("speaker")) not in connues
            or v.get("genre") != npc.get("genre")):
        # tirage fixé par le nom : le PNJ retrouve la même voix à chaque chargement
        npc["voix"] = assign_voice(npc, random.Random(npc.get("nom", "")))
    return npc


# --- Routes -----------------------------------------------------------------
@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/config")
def config():
    installes = moteurs.modeles_locaux() if "local" in moteurs.choix.values() else []
    return jsonify({"moteurs": moteurs.description(), "tts": tts.nom if tts.catalogue() else None,
                    "stt_local": stt_local(), "modeles_locaux": installes,
                    "modele_local": moteurs.modele_local_installe(installes)})


def _ollama_get(chemin):
    url = f"{moteurs.local_cfg.get('url', 'http://localhost:11434').rstrip('/')}{chemin}"
    with urllib.request.urlopen(url, timeout=2) as r:
        return json.loads(r.read())


def etat_gpu():
    """Utilisation de la carte NVIDIA via nvidia-smi ; None si absent ou en panne."""
    try:
        sortie = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3, check=True).stdout
        nom, usage, utilisee, totale = [x.strip() for x in sortie.splitlines()[0].split(",")]
        return {"nom": nom, "usage": int(usage), "memoire_mo": int(utilisee), "memoire_totale_mo": int(totale)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


@app.get("/api/etat")
def etat():
    """État de la machine pour la page de jeu : Ollama (si un moteur local est choisi) et GPU."""
    res = {"gpu": etat_gpu(), "ollama": None}
    if "local" in moteurs.choix.values():
        try:
            charges = _ollama_get("/api/ps").get("models", [])
            res["ollama"] = {"ok": True, "charges": [
                {"nom": m["name"], "vram_mo": round(m.get("size_vram", 0) / 1e6)} for m in charges]}
        except (OSError, ValueError, KeyError):
            res["ollama"] = {"ok": False}
    return jsonify(res)


@app.post("/api/model")
def choisir_modele():
    """Change le modèle local pour tout le serveur, sans toucher à config.toml."""
    try:
        moteurs.choisir_modele_local((request.json or {}).get("modele", ""))
    except MoteurIndisponible as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"modele_local": moteurs.local_cfg["modele"]})


def create_npc(role="", nom="", genre="", consignes=""):
    """Fait inventer un PNJ par Claude, dans le contexte du scénario.
    Lève ValueError si la fiche reçue est invalide."""
    scenario = load_scenario()
    parts = []
    if scenario["monde"]:
        parts.append(f"<univers>\n{scenario['monde']}\n</univers>")
    if scenario["notes_mj"]:
        parts.append(f"<notes_du_mj>\n{scenario['notes_mj']}\n</notes_du_mj>")
    if consignes.strip():
        parts.append(f"<consignes_pour_ce_pnj>\n{consignes.strip()[:4000]}\n</consignes_pour_ce_pnj>")
    demande = [f"Métier : {role.strip()[:80] or random.choice(METIERS)}."]
    if nom.strip():
        demande.append(f"Nom imposé : {nom.strip()[:80]}.")
    else:
        demande.append(f"Le nom commence par la lettre {random.choice(INITIALES)}.")
    if genre in ("feminin", "masculin", "neutre"):
        demande.append(f"Genre : {genre}.")
    demande.append(f"Suggestions : humeur {random.choice(HUMEURS)}, trait dominant {random.choice(TRAITS)}.")
    parts.append(" ".join(demande))
    seed = "\n\n".join(parts)
    text = moteurs.fiche(GEN_SYSTEM, seed, NPC_SCHEMA)
    try:
        npc = parse_json(text)
    except (ValueError, IndexError) as e:
        app.logger.warning("JSON PNJ invalide : %r", text[:500])
        raise ValueError("fiche invalide") from e
    npc["salutation"] = clean_for_speech(npc.get("salutation", "Bonjour, voyageur."))
    npc["voix"] = assign_voice(npc)
    return npc


@app.post("/api/npc/generate")
def generate_npc():
    try:
        d = request.json or {}
        return jsonify(create_npc(d.get("role", ""), d.get("nom", ""),
                                  d.get("genre", ""), d.get("consignes", "")))
    except ValueError:
        return jsonify({"error": "Le modèle n'a pas renvoyé de JSON valide. Relancez la génération."}), 502
    except MoteurIndisponible as e:
        return jsonify({"error": f"{e} Choisissez un PNJ dans la banque."}), 503


# --- Banque de PNJ : un fichier JSON par personnage dans pnj/ ----------------
BANK_DIR = BASE_DIR / CONFIG.get("banque", {}).get("dossier", "pnj")
NPC_ID = re.compile(r"^[a-z0-9-]{1,80}$")  # protège contre les chemins arbitraires


SCENARIO_PATH = BANK_DIR / "_scenario.json"  # « _ » : jamais pris pour un PNJ


def load_scenario():
    """{"monde": connu de tous les PNJ, "notes_mj": réservé à la création des PNJ}."""
    try:
        data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"monde": data.get("monde", ""), "notes_mj": data.get("notes_mj", "")}


@app.get("/api/scenario")
def scenario_get():
    return jsonify(load_scenario())


@app.put("/api/scenario")
def scenario_put():
    data = request.json or {}
    scenario = {k: str(data.get(k, "")).strip()[:20000] for k in ("monde", "notes_mj")}
    BANK_DIR.mkdir(exist_ok=True)
    SCENARIO_PATH.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(scenario)


def npc_path(npc_id):
    if not NPC_ID.match(npc_id or ""):
        return None
    return BANK_DIR / f"{npc_id}.json"


def write_npc(npc_id, npc):
    npc = ensure_voice({k: v for k, v in npc.items() if k != "id"})
    npc["salutation"] = clean_for_speech(npc.get("salutation", ""))
    BANK_DIR.mkdir(exist_ok=True)
    npc_path(npc_id).write_text(json.dumps(npc, ensure_ascii=False, indent=2), encoding="utf-8")


def save_npc(npc):
    """Enregistre un nouveau PNJ dans la banque et renvoie son identifiant."""
    nom = unicodedata.normalize("NFKD", str(npc.get("nom", "pnj"))).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", nom.lower()).strip("-")[:60] or "pnj"
    npc_id = f"{slug}-{secrets.token_hex(2)}"
    write_npc(npc_id, npc)
    return npc_id


@app.get("/api/bank")
def bank_list():
    items = []
    for f in sorted(BANK_DIR.glob("*.json")) if BANK_DIR.exists() else []:
        if f.stem.startswith("_"):
            continue  # _scenario.json
        try:
            npc = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue  # fichier abîmé ou en cours d'édition : on l'ignore
        items.append({"id": f.stem, "nom": npc.get("nom", f.stem), "metier": npc.get("metier", "")})
    return jsonify(sorted(items, key=lambda n: n["nom"].lower()))


@app.get("/api/bank/<npc_id>")
def bank_get(npc_id):
    path = npc_path(npc_id)
    if not path or not path.exists():
        return jsonify({"error": "PNJ introuvable."}), 404
    npc = json.loads(path.read_text(encoding="utf-8"))
    ensure_voice(npc)
    npc["id"] = npc_id
    return jsonify(npc)


@app.post("/api/bank")
def bank_save():
    npc = request.json or {}
    if not npc.get("nom") or not npc.get("salutation"):
        return jsonify({"error": "Fiche de PNJ incomplète."}), 400
    return jsonify({"id": save_npc(npc)})


@app.put("/api/bank/<npc_id>")
def bank_update(npc_id):
    path = npc_path(npc_id)
    npc = request.json or {}
    if not path or not path.exists():
        return jsonify({"error": "PNJ introuvable."}), 404
    if not npc.get("nom") or not npc.get("salutation"):
        return jsonify({"error": "Fiche de PNJ incomplète."}), 400
    write_npc(npc_id, npc)
    return jsonify({"id": npc_id})


@app.post("/api/voice")
def new_voice():
    """Tire une autre voix pour le PNJ (changement de genre ou de moteur),
    ou applique celle demandée dans `choix` (nom de voix de GET /api/voices)."""
    npc = request.json or {}
    voice = assign_voice(npc)
    choix = npc.get("choix")
    if choix:
        trouvee = next((v for v, _ in tts.catalogue() if v["name"] == choix), None)
        if not trouvee:
            return jsonify({"error": "Voix inconnue."}), 404
        voice.update(trouvee)
    return jsonify(voice)


@app.get("/api/voice-engine")
def voice_engine_get():
    return jsonify({"actuel": tts.nom, "moteurs": list(voix.MOTEURS)})


@app.put("/api/voice-engine")
def voice_engine_set():
    """Change de moteur de synthèse pour tout le serveur, sans toucher à config.toml."""
    global tts
    nom = (request.json or {}).get("moteur", "")
    try:
        moteur = _tts_charges.get(nom) or voix.charger(CONFIG, BASE_DIR, nom)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not moteur.catalogue():
        return jsonify({"error": f"Le moteur « {nom} » n'est pas utilisable ici (paquet ou voix manquants)."}), 400
    if nom not in _tts_charges:
        _tts_charges[nom] = moteur
        threading.Thread(target=moteur.prechauffer, daemon=True).start()
    tts = moteur
    return jsonify({"actuel": tts.nom})


@app.get("/api/voices")
def voices_list():
    """Voix du moteur de synthèse, avec leur genre, pour la liste de choix de la page de création."""
    return jsonify([{**v, "genre": g} for v, g in tts.catalogue()])


@app.delete("/api/bank/<npc_id>")
def bank_delete(npc_id):
    path = npc_path(npc_id)
    if not path or not path.exists():
        return jsonify({"error": "PNJ introuvable."}), 404
    path.unlink()
    return jsonify({"ok": True})


def npc_system_prompt(npc):
    infos = "\n".join(f"- {c}" for c in npc.get("connaissances", []))
    monde = load_scenario()["monde"]  # jamais les notes du MJ : elles peuvent contenir l'intrigue
    univers = (f"""Ce que tout habitant sait du monde :
<univers>
{monde}
</univers>
""" if monde else "")
    return f"""{univers}Tu es {npc.get('nom')}, {npc.get('metier')}, dans un monde médiéval-fantastique.
Apparence : {npc.get('apparence')}
Personnalité : {npc.get('personnalite')} Humeur du jour : {npc.get('humeur')}.
Ce que tu sais et peux révéler :
{infos}
Ton secret (ne le révèle que si le voyageur gagne vraiment ta confiance ou te paie bien) : {npc.get('secret')}

Règles :
- Tes réponses sont LUES À VOIX HAUTE : 1 à 3 phrases courtes, langage parlé.
- Aucun markdown, aucun emoji, aucune action entre astérisques.
- Reste toujours dans ton personnage. Tu ne sais rien du monde réel moderne.
- Ne cite aucun lieu, personnage, faction ou événement absent de l'univers ci-dessus ou de ta fiche.
  Si on te demande quelque chose que tu ignores, dis-le à ta manière ou reste vague, sans inventer de nom propre.
- Si c'est ton métier, tu peux proposer des marchandises avec des prix en pièces d'or ou d'argent."""


@app.post("/api/npc/talk")
def talk():
    data = request.json or {}
    npc = data.get("npc") or {}
    message = (data.get("message") or "").strip()[:500]
    if not npc or not message:
        return jsonify({"error": "Il manque le PNJ ou la question."}), 400

    history = [m for m in data.get("history", [])
               if m.get("role") in ("user", "assistant") and m.get("content")][-HISTORIQUE:]
    # L'API attend un premier message « user » : on met en scène l'arrivée du joueur.
    messages = [{"role": "user", "content": "(Un voyageur s'approche de toi.)"},
                {"role": "assistant", "content": npc.get("salutation", "Bonjour.")}]
    for m in history:  # fusionne d'éventuels messages consécutifs du même rôle
        if messages[-1]["role"] == m["role"]:
            messages[-1]["content"] += "\n" + m["content"]
        else:
            messages.append({"role": m["role"], "content": m["content"]})
    if messages[-1]["role"] == "user":
        messages[-1]["content"] += "\n" + message
    else:
        messages.append({"role": "user", "content": message})

    try:
        morceaux = moteurs.replique(npc_system_prompt(npc), messages)
    except MoteurIndisponible as e:
        return jsonify({"error": str(e)}), 503

    def lignes():
        """Une ligne JSON par phrase prête à être lue : {"phrase": "..."}, ou {"error": "..."}."""
        try:
            for phrase in map(clean_for_speech, phrases(morceaux)):
                if phrase:
                    yield json.dumps({"phrase": phrase}, ensure_ascii=False) + "\n"
        except MoteurIndisponible as e:
            yield json.dumps({"error": str(e)}, ensure_ascii=False) + "\n"
    return Response(lignes(), mimetype="application/x-ndjson")


@app.post("/api/tts")
def synthese():
    data = request.json or {}
    text = chiffres_en_lettres(clean_for_speech(data.get("text", "")))[:600]
    if not text:
        return jsonify({"error": "Rien à lire."}), 400
    voice = data.get("voice") or {}
    if data.get("narrateur"):  # description entre parenthèses : voix neutre, autre que celle du PNJ
        voice = voix.voix_narrateur(tts, voice)
        if voice is None:
            return jsonify({"error": "Synthèse vocale indisponible."}), 503
    try:
        audio, mimetype = tts.synthese(text, voice)
    except voix.VoixIndisponible as e:
        app.logger.warning("Synthèse vocale : %s", e)
        return jsonify({"error": "Synthèse vocale indisponible."}), 503
    return send_file(io.BytesIO(audio), mimetype=mimetype)


@app.post("/api/stt")
def stt():
    """Transcrit l'enregistrement du micro (webm/opus envoyé par le navigateur)."""
    audio = request.files.get("audio")
    if not stt_local():
        return jsonify({"error": "Reconnaissance vocale locale indisponible."}), 404
    if not audio:
        return jsonify({"error": "Aucun enregistrement reçu."}), 400
    # L'indice (nom et métier du PNJ) aide Whisper à écrire les noms propres et le vocabulaire du jeu.
    indice = request.form.get("indice", "").strip()[:200] or None
    try:
        segments, _ = load_stt().transcribe(io.BytesIO(audio.read()), language="fr", beam_size=STT_CFG.get("beam_size", 5),
                                            vad_filter=True, initial_prompt=indice)
        text = " ".join(s.text.strip() for s in segments).strip()
    except ValueError:
        text = ""  # enregistrement vide ou illisible
    return jsonify({"text": text})


if __name__ == "__main__":
    threading.Thread(target=tts.prechauffer, daemon=True).start()  # voix prêtes avant la 1re réplique
    if STT_CFG.get("moteur") == "local":
        if stt_local():
            threading.Thread(target=load_stt, daemon=True).start()  # prêt avant la première question
        else:
            print(f"[reconnaissance] modèle Whisper absent de {STT_DIR} : la reconnaissance du navigateur "
                  "sera utilisée. Téléchargez-le avec le réseau (voir README).")
    # HTTPS auto-signé si serveur.https = true : nécessaire pour le micro quand on
    # accède au serveur depuis une autre machine (ex. le téléphone d'un joueur).
    # Le certificat est créé une seule fois dans certs/ puis réutilisé : le navigateur
    # garde ainsi l'exception de sécurité et l'autorisation du micro d'un lancement à l'autre.
    srv = CONFIG["serveur"]
    ssl = None
    if srv["https"]:
        from werkzeug.serving import make_ssl_devcert
        cert, key = BASE_DIR / "certs" / "devcert.crt", BASE_DIR / "certs" / "devcert.key"
        if not (cert.exists() and key.exists()):
            cert.parent.mkdir(exist_ok=True)
            make_ssl_devcert(str(cert.with_suffix("")), host="pnj-parlants")
        ssl = (str(cert), str(key))
    app.run(host=srv["hote"], port=srv["port"], ssl_context=ssl)
