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
  serveur.py         # Flask : Contexte (moteurs, banque, réglages à chaud, santé), create_app(cfg, moteurs=, tts=,
                     # reconnaissance=) (plafonds, erreurs JSON) + main() (Ctrl+C, HTTPS)
  routes/            # API, un Blueprint par domaine (ctx = entrees.contexte()) : options, univers, pnj, portraits,
                     # aventuriers, voix, dialogue ; acces.py (mot de passe du MJ, @mj), entrees.py (corps(), erreur(), tailles)
  aventuriers.py     # personnages des joueurs (facultatifs) : systèmes D&D 5e / COF 2e, fiche, bonus des jets,
                     # ce qu'en perçoit le PNJ (sans chiffres)
  config.py          # config.toml du dossier courant, PNJ_CONFIG ou --config
  dependances.py     # dépendances absentes du .venv (lancer.bat)
  fiches.py          # création des fiches (prompt, schéma JSON, tirages au sort)
  dialogue.py        # consignes du PNJ, scène vue par chaque PNJ, séquences d'arrêt
  texte.py           # nettoyage pour la voix, nombres en lettres, découpage en phrases
  moteurs.py         # LLM : Claude (API Anthropic), Ollama ou LM Studio (API compatible OpenAI)
  reglages.py        # réglages de la page Options : catalogue, validation, écriture de config.toml (tomlkit)
  voix.py, stt.py    # synthèse (Pocket TTS, Piper, Edge) ; reconnaissance (faster-whisper)
  portraits.py       # portraits des PNJ (facultatif) : SD-Turbo local (diffusers) ou Pollinations en ligne
  banque.py          # banque de PNJ, scénario, lieux et aventuriers (JSON dans pnj/)
  systeme.py         # état GPU et Ollama
  generer.py         # pnj-banque 20 [--metier ...]
  static/            # index.html (accueil, partie, options), creation.html (scénario, lieux, PNJ, aventuriers, apparence),
                     # style.css (thèmes)
                     # js/ : jeu.js + options.js (index.html), creation.js : DOM, relient la page aux modules testés
                     # sans navigateur : scene.js, partie.js (état de la partie), tours.js (qui parle), controles.js,
                     # micro.js, fiche.js, apparence.js, univers.js (univers, thèmes), aventurier.js (jets de dés),
                     # api.js (requêtes, NDJSON),
                     # bandeau.js (alertes) ; tete.js (script classique du <head> : thème sans flash)
  exemples/          # univers d'exemple (format de pnj/ + _infos.json), proposés sur l'accueil
tests/               # pytest ; tests/js (node --test) ; tests/e2e (navigateur sans écran)
config.toml.example  # tous les réglages ; config.toml (clé API) n'est pas versionné
lancer.bat, docker-compose.yml  # lancement Windows, Ollama dans Docker
scripts/ecran.sh     # libère la VRAM sous Linux (écran graphique coupé)
docs/                # installation-windows.md : guide pas à pas Windows
LICENSE              # GPL-3.0 ; static/fonts/OFL.txt pour les polices (SIL OFL 1.1)
```
Moteurs choisis dans `config.toml` (ou la page Options) : `[moteurs] creation` / `dialogue` = `"claude"`, `"local"`
(Ollama) ou `"lmstudio"` ;
`[voix] moteur` = `pocket`, `piper` ou `edge` ; `[reconnaissance] moteur` = `local` ou `navigateur` ;
`[portraits] moteur` = `aucun` (défaut), `local` ou `en_ligne`.

## Détails chargés à la demande
Les règles de `.claude/rules/` se chargent quand on touche aux fichiers concernés (champ `paths`) ; une règle par
domaine, serveur et pages réunis quand le domaine est petit :
- `serveur.md` : organisation Flask et Blueprints, accès à l'univers hors du PC (`@mj`, secrets masqués, frein aux
  essais), tailles maximales des requêtes, /api/config, /api/etat, /api/sante.
- `moteurs.md` : moteurs de langage (Claude, Ollama, LM Studio), valeurs par défaut, caches de latence.
- `univers.md` : banque (scénario, lieux, PNJ), export/import, exemples, intégrité des écritures.
- `dialogue.md` : /api/npc/generate, /api/npc/talk (scène à plusieurs, séquences d'arrêt, NDJSON), texte.py.
- `aventuriers.md` : personnages des joueurs et jets de dés (serveur, préparation, partie).
- `portraits.md` : portraits (moteurs, prompt, stockage, routes, affichage).
- `reglages.md` : réglages à chaud (`/api/reglages`, mot de passe du MJ) et vue Options.
- `voix.md` : synthèse, attribution des voix, narrateur, reconnaissance, routes de la voix.
- `web.md` : socle des pages (modules JS, vues, préparation, barre du haut, bandeau d'alertes, api.js, style.css).
- `partie.md` : vue Partie (état, conversation gardée, dialogue côté navigateur, lieux, micro).
- `apparence.md` : thèmes graphiques, styles de portrait, onglet Apparence, /api/styles.
- `systeme.md` : dépendances, config.toml, lanceurs, Docker/Ollama, documentation.
- `tests.md` : pytest, node, e2e et ses pièges.

## Lancement
Voir README.md (Linux) et docs/installation-windows.md (Windows, cartes NVIDIA ou AMD).
```bash
uv sync --extra tout --extra dev     # .venv en Python 3.13, versions figées dans uv.lock
cp config.toml.example config.toml   # cle_api, ou variable ANTHROPIC_API_KEY
pnj-parlant                          # ou python -m pnj_parlant ; port dans [serveur] port (5000)
pytest && npm test                   # tests, sans réseau ni modèle ; e2e : python tests/e2e/lancer.py
```

## Conventions
- Ajouter un test à chaque changement de logique ; une fonction JS testable (sans DOM) va dans le module de
  `static/js/` de son domaine, avec son test dans `tests/js/` ; jeu.js, options.js et creation.js ne gardent que le DOM.
- Nouvelle route : dans le Blueprint de son domaine (`routes/`), écriture de l'univers sous `@mj` (test_api.py
  fige la liste des routes et celles gardées).
- Tout nouveau réglage : `config.toml.example` (commenté) et README.md.
- Garder README.md, docs/installation-windows.md et ces règles à jour quand le comportement change : un hook
  (`.claude/hooks/doc_a_jour.py`, événement Stop) le rappelle si du code a changé sans la documentation.
- Nouveau réglage utile en partie : l'ajouter aussi au `CATALOGUE` de reglages.py (page Options).
- Fichiers en CRLF dans la copie de travail (Windows) : les modifier avec Edit, ou en gardant les fins de ligne.
- Interface : barre du haut et styles communs dans `style.css` ; couleurs seulement par variables (thèmes).

## État
- Machine de dev Linux en tout-local (`qwen3:4b-instruct`, NVIDIA T400 4 Go, port 7800 en HTTPS),
  Ollama dans Docker sur le GPU.
- Poste Windows : serveur lancé par l'utilisateur sur 192.168.1.21:5000 (fichiers statiques servis depuis le dépôt :
  un rechargement suffit ; le code Python demande de relancer le serveur).

## Pistes pour la suite
- Contexte de monde plus riche (ville, rumeurs du jour) et inventaire/prix fixes pour les marchands.
- Vérifier la latence et la charge sur le PC de référence.
