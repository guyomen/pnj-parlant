# PNJ parlants — contexte du projet

## Objectif
Générateur de PNJ (personnages non-joueurs) pour jeu de rôle médiéval-fantastique, avec voix de
synthèse. Le MJ prépare un scénario et une banque de PNJ ; le joueur parle au PNJ au micro depuis
un navigateur, le PNJ répond dans son personnage, à voix haute. Langue : français (code, commentaires,
interface et documentation).

## Contraintes
- Serveur Python sur un PC (le Raspberry Pi est abandonné) ; client = navigateur web (Chrome/Edge),
  y compris les téléphones des joueurs sur le même Wi-Fi.
- Jouable sans réseau une fois la préparation faite : chaque brique a une version locale.
- Solutions gratuites / open source privilégiées pour la voix.
- Réponses courtes (1-3 phrases), sans markdown/emoji/astérisques, car lues à voix haute ; latence faible.

## Architecture
Paquet Python `pnj_parlant` (layout src/), installé par `uv sync --extra tout` (ou `pip install -e ".[tout]"`).
```
src/pnj_parlant/
  serveur.py         # Flask : create_app(cfg, moteurs=, tts=, reconnaissance=) + main() (Ctrl+C, HTTPS)
  config.py          # config.toml du dossier courant, PNJ_CONFIG ou --config
  dependances.py     # dépendances absentes du .venv (lancer.bat)
  fiches.py          # création des fiches (prompt, schéma JSON, tirages au sort)
  dialogue.py        # consignes du PNJ, scène vue par chaque PNJ, séquences d'arrêt
  texte.py           # nettoyage pour la voix, nombres en lettres, découpage en phrases
  moteurs.py         # LLM : Claude (API Anthropic) ou modèle local (Ollama)
  voix.py, stt.py    # synthèse (Pocket TTS, Piper, Edge) ; reconnaissance (faster-whisper)
  banque.py          # banque de PNJ, scénario et lieux (JSON dans pnj/)
  systeme.py         # état GPU et Ollama
  generer.py         # pnj-banque 20 [--metier ...]
  static/            # index.html (jeu), creation.html, js/scene.js (fonctions pures testées)
tests/               # pytest ; tests/js (node --test) ; tests/e2e (navigateur sans écran)
config.toml.example  # tous les réglages ; config.toml (clé API) n'est pas versionné
lancer.bat, docker-compose.yml  # lancement Windows, Ollama dans Docker
scripts/ecran.sh     # libère la VRAM sous Linux (écran graphique coupé)
docs/                # installation-windows.md : guide pas à pas Windows
```
Moteurs choisis dans `config.toml` : `[moteurs] creation` / `dialogue` = `"claude"` ou `"local"` (Ollama) ;
`[voix] moteur` = `pocket`, `piper` ou `edge` ; `[reconnaissance] moteur` = `local` ou `navigateur`.

## Détails chargés à la demande
Les règles de `.claude/rules/` se chargent quand on touche aux fichiers concernés :
- `serveur.md` : routes, /api/npc/talk (scène à plusieurs, séquences d'arrêt, NDJSON), moteurs de langage.
- `web.md` : page de jeu (état, dialogue, lieux, export/import, micro et interruption).
- `voix.md` : synthèse, attribution des voix, narrateur, reconnaissance.
- `systeme.md` : dépendances, config.toml, lanceurs, Docker/Ollama, documentation.
- `tests.md` : pytest, node, e2e et ses pièges.

## Lancement
Voir README.md (Linux) et docs/installation-windows.md (Windows, cartes NVIDIA ou AMD).
```bash
uv sync --extra tout --extra dev     # .venv en Python 3.13, versions figées dans uv.lock
cp config.toml.example config.toml   # cle_api, ou variable ANTHROPIC_API_KEY
pnj-parlant                          # ou python -m pnj_parlant ; port dans [serveur] port (5000)
pytest && node --test tests/js/      # tests, sans réseau ni modèle ; e2e : python tests/e2e/lancer.py
```

## Conventions
- Ajouter un test à chaque changement de logique ; une fonction JS testable va dans `static/js/scene.js`.
- Tout nouveau réglage : `config.toml.example` (commenté) et README.md.
- Garder README.md, docs/installation-windows.md et ces règles à jour quand le comportement change.

## État
- Machine de dev Linux en tout-local (`qwen3:4b-instruct`, NVIDIA T400 4 Go, port 7800 en HTTPS),
  Ollama dans Docker sur le GPU.

## Pistes pour la suite
- Contexte de monde plus riche (ville, rumeurs du jour) et inventaire/prix fixes pour les marchands.
- Vérifier la latence et la charge sur le PC de référence.
