# PNJ parlants — contexte du projet

## Objectif
Générateur de PNJ (personnages non-joueurs) pour jeu de rôle médiéval-fantastique, avec voix de
synthèse. Le MJ prépare un scénario et une banque de PNJ ; le joueur parle au PNJ au micro depuis
un navigateur, le PNJ répond dans son personnage, à voix haute. Langue : français.

## Contraintes
- Serveur Python sur un PC (le Raspberry Pi est abandonné) ; client = navigateur web (Chrome/Edge),
  y compris les téléphones des joueurs sur le même Wi-Fi.
- Jouable sans réseau une fois la préparation faite : chaque brique a une version locale.
- Solutions gratuites / open source privilégiées pour la voix.
- Réponses courtes (1-3 phrases), sans markdown/emoji/astérisques, car lues à voix haute ; latence faible.

## Architecture
```
app.py               # Flask : routes, prompts, banque de PNJ, reconnaissance vocale
moteurs.py           # LLM : Claude (API Anthropic) ou modèle local (Ollama)
voix.py              # synthèse vocale : Pocket TTS, Piper ou Edge
generer_banque.py    # remplit la banque en lot : python generer_banque.py 20 [--metier ...]
config.toml(.example)# tous les réglages ; config.toml (clé API) n'est pas versionné
docker-compose.yml   # Ollama dans Docker (carte NVIDIA)
lancer.bat, lancerAMD.bat, ecran.sh  # lanceurs Windows ; ecran.sh libère la mémoire vidéo sous Linux
static/index.html    # page de jeu (HTML/CSS/JS vanilla, aucun build)
static/creation.html # préparation : scénario + banque de PNJ
pnj/                 # banque : _scenario.json + un JSON par PNJ (créé à l'usage)
voices/, modeles-stt/  # voix Piper et modèle Whisper, téléchargés, non versionnés
```
Moteurs, choisis dans `config.toml` :
- `[moteurs] creation` et `dialogue` : `"claude"` (`claude-haiku-5-5`, `[claude] modele`) ou `"local"`
  (Ollama, `[local] modele`, ex. `qwen3:4b-instruct` sur 4 Go de VRAM, `qwen3:8b` au-delà).
- `[voix] moteur` : `pocket` (local, WAV), `piper` (local, WAV) ou `edge` (en ligne, MP3).
- `[reconnaissance] moteur` : `local` (faster-whisper, modèle dans `modeles-stt/<modele>`) ou `navigateur`.

Routes :
- `GET /api/config` : moteurs utilisés, moteur de voix, reconnaissance locale disponible ou non.
- `POST /api/npc/generate {role, nom, genre, consignes}` : fiche JSON imposée par un schéma
  (nom, metier, apparence, personnalite, tic_de_langage, humeur, connaissances, secret, salutation,
  genre, timbre, debit). Humeur/trait/initiale du nom tirés au sort en Python pour varier les PNJ.
  Le serveur ajoute `voix` (voix du genre du PNJ + réglages, et pitch/rate pour le repli navigateur).
- `GET|PUT /api/scenario` : `monde` (connu de tous les PNJ, envoyé dans les dialogues) et `notes_mj`
  (servent seulement à la création, jamais envoyées pendant les dialogues).
- `GET|POST /api/bank`, `GET|PUT|DELETE /api/bank/<id>`, `POST /api/voice` (autre voix pour un PNJ).
  `ensure_voice` réattribue une voix stable (graine = nom) si celle du PNJ manque sur la machine.
- `POST /api/npc/talk {npc, history, message}` : fiche + univers = prompt système ; serveur sans état,
  historique côté navigateur (`[dialogue] historique`, 12 messages). Réponse en streaming NDJSON,
  une ligne `{"phrase": ...}` par phrase (ou `{"error": ...}`) ; le navigateur lit chaque phrase dès
  qu'elle arrive et prépare la voix de la suivante.
- `POST /api/tts {text, voice}` : en cas d'échec (503), le navigateur utilise `speechSynthesis`.
- `POST /api/stt` (audio webm/opus + indice) : faster-whisper ; repli sur la Web Speech API.

Le micro exige `localhost` ou HTTPS : `[serveur] https = true` crée un certificat auto-signé dans `certs/`.

## Lancement
Voir README.md (Linux) et HOWTO.md (Windows, cartes NVIDIA ou AMD).
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.toml.example config.toml   # cle_api, ou variable ANTHROPIC_API_KEY
python app.py                        # port dans [serveur] port (5000 par défaut)
```

## État
- Machine de dev en tout-local (`qwen3:4b-instruct`, NVIDIA T400 4 Go, port 7800 en HTTPS).
  Ollama y tourne encore sur le processeur : installer le pilote NVIDIA, voir A-FAIRE-APRES-INSTALL.md.
- Aucun test automatisé.

## Pistes pour la suite
- Contexte de monde plus riche (ville, rumeurs du jour) et inventaire/prix fixes pour les marchands.
- Vérifier la latence et la charge sur le PC de référence.
