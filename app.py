"""
PoC : générateur de PNJ parlants.
- Claude Haiku ou un modèle local (Ollama) invente le PNJ (fiche JSON) puis joue son rôle.
- Piper lit les répliques à voix haute (sinon, repli sur la voix du navigateur).
- La reconnaissance vocale du joueur se fait dans le navigateur (Web Speech API).

Lancement :  python app.py   puis ouvrir http://localhost:5000
Réglages :   config.toml (à créer à partir de config.toml.example)
"""
import io
import json
import random
import re
import secrets
import tomllib
import unicodedata
import wave
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from moteurs import MoteurIndisponible, Moteurs

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.toml"
if not CONFIG_PATH.exists():
    raise SystemExit("config.toml introuvable : copiez config.toml.example en config.toml "
                     "et renseignez votre clé API.")
with open(CONFIG_PATH, "rb") as f:
    CONFIG = tomllib.load(f)

HISTORIQUE = CONFIG.get("dialogue", {}).get("historique", 12)  # messages gardés pour le contexte
VOICES_DIR = BASE_DIR / CONFIG["voix"]["dossier"]  # un chemin absolu reste absolu

app = Flask(__name__, static_folder="static", static_url_path="")
moteurs = Moteurs(CONFIG)  # Claude ou modèle local, d'après la section [moteurs]

# --- Piper (optionnel) -------------------------------------------------------
try:
    from piper import PiperVoice, SynthesisConfig
    PIPER_OK = True
except ImportError:
    PIPER_OK = False

_voice_cache = {}


def list_voices():
    """Toutes les voix .onnx présentes dans voices/, avec leur nombre de locuteurs."""
    if not PIPER_OK or not VOICES_DIR.exists():
        return []
    voices = []
    for onnx in sorted(VOICES_DIR.glob("*.onnx")):
        cfg = onnx.with_suffix(".onnx.json")
        speakers = 1
        if cfg.exists():
            speakers = json.loads(cfg.read_text(encoding="utf-8")).get("num_speakers", 1)
        voices.append({"name": onnx.stem, "speakers": max(1, speakers)})
    return voices


def load_voice(name):
    if name not in _voice_cache:
        _voice_cache[name] = PiperVoice.load(VOICES_DIR / f"{name}.onnx")
    return _voice_cache[name]


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
"tic_de_langage" (une expression ou manie verbale), "humeur",
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
        "tic_de_langage": _TEXTE, "humeur": _TEXTE,
        "connaissances": {"type": "array", "items": _TEXTE},
        "secret": _TEXTE, "salutation": _TEXTE,
        "genre": {"type": "string", "enum": ["feminin", "masculin", "neutre"]},
        "timbre": {"type": "string", "enum": ["grave", "moyen", "aigu"]},
        "debit": {"type": "string", "enum": ["lent", "normal", "rapide"]},
    },
    "required": ["nom", "metier", "apparence", "personnalite", "tic_de_langage", "humeur",
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


def speaker_genders(voice):
    """{numéro de locuteur: genre} d'après la section [voix.genres] de config.toml."""
    g = CONFIG["voix"].get("genres", {}).get(voice["name"])
    if isinstance(g, str):  # voix à un seul genre : tous ses locuteurs
        return {i: g for i in range(voice["speakers"])}
    if isinstance(g, dict):  # voix multi-locuteurs : { feminin = [0], masculin = [1] }
        return {i: genre for genre, ids in g.items() for i in ids if i < voice["speakers"]}
    return {}  # genre inconnu


def assign_voice(npc):
    """Choisit une voix Piper du genre du PNJ (et un réglage navigateur) d'après timbre et débit."""
    genre = npc.get("genre")
    debit = {"lent": 1.2, "normal": 1.0, "rapide": 0.85}.get(npc.get("debit"), 1.0)
    pitch = {"grave": 0.7, "moyen": 1.0, "aigu": 1.35}.get(npc.get("timbre"), 1.0)
    pitch *= {"feminin": 1.25, "masculin": 0.85}.get(genre, 1.0)  # voix du navigateur
    voice = {"length_scale": round(debit * random.uniform(0.95, 1.05), 2),
             "browser_pitch": round(pitch, 2), "browser_rate": round(1 / debit, 2)}
    voices = list_voices()
    if voices:
        # Locuteurs du bon genre ; à défaut (PNJ neutre ou aucune voix de ce genre), n'importe lequel.
        matching = [(v["name"], i) for v in voices
                    for i, g in speaker_genders(v).items() if g == genre]
        everyone = [(v["name"], i) for v in voices for i in range(v["speakers"])]
        voice["name"], voice["speaker"] = random.choice(matching or everyone)
    voice["genre"] = genre
    return voice


def ensure_voice(npc):
    """Réattribue une voix si celle du PNJ manque sur cette machine ou ne correspond plus à son genre."""
    v = npc.get("voix") or {}
    if v.get("name") not in {x["name"] for x in list_voices()} or v.get("genre") != npc.get("genre"):
        npc["voix"] = assign_voice(npc)
    return npc


# --- Routes -----------------------------------------------------------------
@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/config")
def config():
    return jsonify({"moteurs": moteurs.description(), "piper": bool(list_voices()), "voices": list_voices()})


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
    """Tire une autre voix pour le PNJ (bouton « Autre voix » de la page de création)."""
    return jsonify(assign_voice(request.json or {}))


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
Tic de langage : {npc.get('tic_de_langage')}
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
        reply = moteurs.replique(npc_system_prompt(npc), messages)
    except MoteurIndisponible as e:
        return jsonify({"error": str(e)}), 503
    return jsonify({"reply": clean_for_speech(reply)})


@app.post("/api/tts")
def tts():
    data = request.json or {}
    text = clean_for_speech(data.get("text", ""))[:600]
    voice = data.get("voice") or {}
    names = {v["name"]: v["speakers"] for v in list_voices()}
    name = voice.get("name")
    if not text or name not in names:  # protège aussi contre les chemins arbitraires
        return jsonify({"error": "Voix Piper indisponible."}), 404

    speaker = voice.get("speaker") if names[name] > 1 else None
    cfg = SynthesisConfig(speaker_id=speaker,
                          length_scale=float(voice.get("length_scale", 1.0)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        load_voice(name).synthesize_wav(text, wav_file, syn_config=cfg)
    buf.seek(0)
    return send_file(buf, mimetype="audio/wav")


if __name__ == "__main__":
    # HTTPS auto-signé si serveur.https = true : nécessaire pour le micro quand on
    # accède au serveur depuis une autre machine (ex. le Raspberry Pi sur le réseau).
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
