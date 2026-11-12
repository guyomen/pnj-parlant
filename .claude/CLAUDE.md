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
  Le serveur coupe la réponse après `[dialogue] phrases_max` phrases (`texte.limiter_phrases`, 3 par défaut).

## Architecture
Paquet Python `pnj_parlant` (layout src/, `pyproject.toml`, `uv.lock`), installé par `uv sync --extra tout`
(ou `pip install -e ".[tout]"`).
```
pyproject.toml       # dépendances (options voix, stt, tout, dev) ; commandes pnj-parlant et pnj-banque
src/pnj_parlant/
  serveur.py         # Flask : create_app(cfg, moteurs=, tts=, reconnaissance=) + main() (Ctrl+C, HTTPS)
  config.py          # config.toml du dossier courant, PNJ_CONFIG ou --config ; chemins relatifs à son dossier
  dependances.py     # dépendances de pyproject.toml absentes du .venv (lancer.bat ; bibliothèque standard seule)
  fiches.py          # création des fiches (prompt, schéma JSON, tirages au sort)
  dialogue.py        # consignes du PNJ, scène vue par chaque PNJ, découpage de sa réponse
  texte.py           # nettoyage pour la voix, nombres en lettres, phrases, « Nom : » en tête
  moteurs.py         # LLM : Claude (API Anthropic) ou modèle local (Ollama)
  voix.py            # synthèse : Pocket TTS, Piper ou Edge ; attribuer/verifier la voix d'un PNJ ; narrateur
  stt.py             # reconnaissance vocale faster-whisper
  banque.py          # banque de PNJ et scénario (JSON)
  systeme.py         # état GPU (nvidia-smi) et Ollama
  generer.py         # pnj-banque 20 [--metier ...]
  static/            # index.html (jeu, <script type="module">), creation.html, js/scene.js (fonctions pures)
tests/               # pytest (faux moteurs dans conftest.py) ; tests/js/*.test.mjs (node --test) ;
                     # tests/e2e/lancer.py : vrai serveur + faux Ollama + Edge/Chrome sans écran (CDP)
config.toml(.example)# tous les réglages ; config.toml (clé API) n'est pas versionné
docker-compose.yml   # Ollama dans Docker (carte NVIDIA)
lancer.bat, ecran.sh # lanceur Windows : Ollama (Windows ou Docker selon la carte) seulement si un moteur est local
                     # (python -m pnj_parlant.config), puis python -m pnj_parlant ; ecran.sh libère la VRAM sous Linux
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
  (nom, metier, apparence, personnalite, humeur, connaissances, secret, salutation,
  genre, timbre, debit). Humeur/trait/initiale du nom tirés au sort en Python pour varier les PNJ.
  Le serveur ajoute `voix` (voix du genre du PNJ + réglages, et pitch/rate pour le repli navigateur).
- `GET|PUT /api/scenario` : `monde` (connu de tous les PNJ, envoyé dans les dialogues) et `notes_mj`
  (servent seulement à la création, jamais envoyées pendant les dialogues).
- `GET|PUT /api/lieux` : lieux du scénario (`pnj/_lieux.json`) : `{id, nom, description, notes_mj}`. La
  description est connue de tous les PNJ et lue par le narrateur ; les notes du MJ ne servent qu'à la création
  (`/api/npc/generate {..., lieu}` rattache le PNJ à son lieu habituel, champ `lieu` de la fiche).
  `/api/npc/talk {..., lieu}` : le PNJ sait où il est (et s'il accompagne le voyageur hors de son lieu).
  Côté navigateur : menu du lieu, PNJ présents (« Aborder »), compagnons (case « Vous accompagne »),
  positions des PNJ pendant la partie (`position`, `parLieu` : fiche « Se trouve », menu de la banque groupé
  par lieu), « allons à la forge » → proposition (`lieuEvoque`).
- `GET|POST /api/bank`, `GET|PUT|DELETE /api/bank/<id>`, `POST /api/voice` (autre voix pour un PNJ).
  `ensure_voice` réattribue une voix stable (graine = nom) si celle du PNJ manque sur la machine.
- `POST /api/npc/talk {npc, presents, history}` : fiche + univers = prompt système ; serveur sans état,
  historique côté navigateur (`[dialogue] historique`, 12 messages) : toute la scène,
  `[{speaker: nom du PNJ ou null pour le joueur, content}]`, salutations comprises. Scène à plusieurs PNJ
  (`presents`, jusqu'à 3 en tout) : chaque PNJ voit ses répliques en `assistant` et celles des autres en
  `user` préfixées par le nom de l'auteur, plus un rappel en fin de dernier message. Les petits modèles
  écrivent quand même la suite de la scène : séquences d'arrêt (`dialogue.arrets` : « Léonard : »,
  « Voyageur: »… → option `stop` d'Ollama, `stop_sequences` de Claude) qui arrêtent la génération à la
  source, puis en filet de sécurité `texte.sans_autres_locuteurs`, qui coupe le flux dès qu'une étiquette
  suit une fin de phrase ; la connexion au modèle est alors fermée.
  Côté navigateur : répond le PNJ cité (nom ou métier), sinon le dernier à avoir parlé ; un PNJ à qui un
  autre pose une question répond juste après (`questionnes`, 4 répliques d'affilée au plus) ; options
  « Interventions spontanées » (`[dialogue] intervention`), « Laissez-les discuter » et « Faire entrer »
  (PNJ créé par `/api/npc/generate` avec la conversation dans `consignes`). Réponse en streaming NDJSON,
  une ligne `{"phrase": ...}` par phrase (ou `{"error": ...}`) ; le navigateur lit chaque phrase dès
  qu'elle arrive et prépare la voix de la suivante.
  Export de la conversation en texte lisible (`texteExport`, avec le lieu) et import (`lireExport`, anciens
  exports compris) : PNJ repris de la banque, sinon recréés par `/api/npc/generate` (`consignesRecreation`) ;
  restent en scène ceux qui ont parlé depuis la dernière arrivée dans un lieu (`sceneImportee`).
- `POST /api/tts {text, voice, narrateur}` : en cas d'échec (503), le navigateur utilise `speechSynthesis`.
  Le texte entre parenthèses (description) est envoyé à part avec `narrateur: true` : voix neutre
  (`narrateur` dans `[voix.<moteur>]`, jamais celle du PNJ), affichée en italique.
- `POST /api/stt` (audio webm/opus + indice) : faster-whisper ; repli sur la Web Speech API.
  Couper la parole au PNJ (Stop, Échap) : option « Parler interrompt le PNJ » (bouton actif pendant qu'il
  parle, barre d'espace) et option « Couper le PNJ dès que vous parlez » (désactivée par défaut : micro
  ouvert pendant la `parole`, `detecteurVoix` de scene.js, puis l'enregistrement continue sur le même micro).

Le micro exige `localhost` ou HTTPS : `[serveur] https = true` crée un certificat auto-signé dans `certs/`.

## Lancement
Voir README.md (Linux) et HOWTO.md (Windows, cartes NVIDIA ou AMD).
```bash
uv sync --extra tout --extra dev     # .venv en Python 3.13 (.python-version), versions figées dans uv.lock
source .venv/bin/activate            # sans uv : python3 -m venv .venv, puis pip install -e ".[tout,dev]"
cp config.toml.example config.toml   # cle_api, ou variable ANTHROPIC_API_KEY
pnj-parlant                          # ou python -m pnj_parlant ; port dans [serveur] port (5000)
pytest && node --test tests/js/      # tests, sans réseau ni modèle
```

## État
- Machine de dev en tout-local (`qwen3:4b-instruct`, NVIDIA T400 4 Go, port 7800 en HTTPS).
  Ollama y tourne encore sur le processeur : installer le pilote NVIDIA, voir A-FAIRE-APRES-INSTALL.md.
- Tests : `pytest` (Python) et `node --test tests/js/` (fonctions de la page de jeu). Ajouter un test à chaque
  changement de logique ; une fonction JS testable va dans `static/js/scene.js`.

## Pistes pour la suite
- Contexte de monde plus riche (ville, rumeurs du jour) et inventaire/prix fixes pour les marchands.
- Vérifier la latence et la charge sur le PC de référence.
