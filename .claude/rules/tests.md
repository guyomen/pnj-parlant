---
paths:
  - "tests/**"
---

# Tests

Aucun ne demande réseau, modèle ni carte graphique.

```bash
pytest                       # Python ; pytest est dans l'option dev (uv sync --extra tout --extra dev)
npm test                     # node --test "tests/js/*.test.mjs" : modules sans DOM de static/js/ (Node 22+ ;
                             # pas « node --test tests/js/ » : Node 22 prend le dossier pour un fichier)
python tests/e2e/lancer.py   # parcours complet dans Edge ou Chrome sans écran (NAVIGATEUR=... pour le choisir)
```

- `faux.py` : `FauxMoteurs`, `FauxTTS`, `FausseReconnaissance`, `FauxPortraits` (`PNG`, `erreur`, `actif`), `FICHE`,
  `VOIX` ; les tests les importent par `from faux import ...` (jamais `from conftest`). `conftest.py` : fixtures `cfg` (config dans tmp_path), `moteurs`, `tts`, `portraits`, `app` (`create_app` avec les faux),
  `client`, `ctx`.
- `test_sante.py` : `Contexte.problemes` / `/api/sante`, avec `serveur.paquet_installe` et
  `serveur.systeme.etat_ollama` remplacés (aucun réseau). Tests JS : `ajouterAlerte`, `alertesSante`.
- `test_acces.py` (décision D1) : chaque route d'écriture depuis le PC, depuis une adresse distante sans mot de passe
  défini, avec mot de passe (absent, faux, bon, accentué) ; masquage des secrets et notes ; champ masqué gardé ;
  secret relu par /api/npc/talk ; `Origin` étranger ; `Frein` (horloge injectée) et verrou 429 ; tailles (413 : JSON,
  /api/stt, nombre et cumul de l'import : `monkeypatch` de `routes.entrees` (`STT_MAX_OCTETS`) et de `routes.univers`
  (`IMPORT_MAX_*`), importé sous le nom `routes_univers` : `univers` est une fixture). Tests JS : `envoyer`
  (mot de passe demandé, gardé, oublié), `verifierAcces`, `nomTelecharge`.
- `test_reglages.py` : catalogue (défauts dans les bornes), `valider`, `ecrire` (commentaires gardés), routes
  `/api/reglages` (secret jamais renvoyé, application à chaud, refus sans rien écrire, mot de passe du MJ, appareil
  distant via `environ_base={"REMOTE_ADDR": …}`, `time.sleep` remplacé par une fixture autouse). `test_moteurs.py` couvre LM Studio
  (`urlopen` simulé, `etat_lmstudio`).
- Lot 7 (couverture des modules Python : 85 % → 97 %) : `test_reglages_a_chaud.py` (moteurs NON injectés :
  `serveur.Moteurs`, `serveur.voix.charger`, `serveur.Reconnaissance` remplacés ; modèle Claude, moteur de voix sans
  voix, reconnaissance, `OSError` à l'écriture, tomlkit absent), `test_stt_systeme.py` (stt.py, `/api/stt`,
  systeme.py, `/api/etat`, `/api/voice-engine`, accès depuis `::1`), `test_moteurs_local.py` (Ollama hors flux, 404,
  modèles installés, Claude, LM Studio hors flux), `test_moteurs_voix.py` (Piper, Pocket, Edge, `portraits.Local`
  avec faux paquets dans `sys.modules`), `test_lancement.py` (`serveur.main`, `generer.main`, `dependances.main`,
  `python -m pnj_parlant.config` : codes 0, 1, 2 lus par lancer.bat). Tests JS : `tests/js/bandeau.test.mjs` (fichier
  à part : bandeau.js se charge avec un faux `document`).
- `test_cache.py` : caches du lot 6 (modèles Ollama et LM Studio, `/api/sante`, catalogue Piper, scénario/lieux/styles
  de la banque), délai simulé par `time.monotonic` remplacé, invalidation par réglages, date de fichier et écriture.
- `test_styles.py` : `valider_styles` (refus, injection CSS impossible), `prompt_du_style`, stockage, export/import,
  « Nouvelle table », routes `/api/styles`. Tests JS : palettes de `THEMES` = style.css et lisibles, `cssThemes`,
  `tousLesThemes`, `contraste`, `identifiant`.
- `test_aventuriers.py` : fiche (`normaliser`, bornes, deux systèmes), `jets` (modificateurs, maîtrise, expertise,
  capacités, dé bonus), `portrait_pour_le_pnj` (sans chiffre, nom à ne pas utiliser), consignes et scène (voyageuse,
  règle des jets, cas de base inchangé), stockage, export/import, « Nouvelle table », routes (`@mj` : appareil distant
  sans mot de passe → 403), /api/npc/talk avec aventurier. Tests JS : `aventurier.test.mjs` (`lancer` avec hasard
  injecté, `appreciation`, textes et élision, `menuJets`, `apercuBonus` = mêmes bonus que le serveur).
- `test_portraits.py` : description (modèle de langage ou repli), moteurs (Pollinations simulé par `urlopen`),
  stockage, export/import, routes. Aucun test ne charge diffusers ni ne contacte Pollinations.
- `test_exemples.py` : chaque dossier de `src/pnj_parlant/exemples/` (avec `_infos.json`) se charge comme une banque,
  fiches conformes au schéma, lieux existants, pas de `voix` (attribuée par le serveur selon la machine), thème
  présent dans `style.css`.
- `test_diagnostic_gpu.py` : `scripts/diagnostic_gpu.py` chargé par son chemin, `commande` et `urlopen` remplacés
  (ni PowerShell, ni réseau, ni vrais compteurs, `time.sleep` remplacé) : rapport complet sans chemin personnel,
  exception rapportée, relevés des compteurs, octets du registre. Compteurs GPU de Windows (test_stt_systeme.py) :
  `agreger_compteurs` sur des instances inventées, `CompteursWindows` remplacé (requête gardée, refaite après une
  panne) ; vraie lecture PDH seulement sous Windows (`skipif`).
- `test_hook_doc.py` : hook Claude Code `.claude/hooks/doc_a_jour.py` (chargé par son chemin) : blocage si du code
  change sans documentation, une seule fois (`stop_hook_active`), `git status` lancé dans `CLAUDE_PROJECT_DIR`.
- `test_api.py` (`TestPages`) fige la liste des routes de l'API (règle, méthode) et celles gardées par `@mj` : à
  mettre à jour avec toute route ajoutée (Blueprints de `routes/`).
- Tests JS par module (lot 8) : `api.test.mjs` (`apiStream` : vrai `ReadableStream` découpé en morceaux, caractère
  coupé, erreur, lecteur relâché), `tours.test.mjs`, `controles.test.mjs`, `micro.test.mjs` (faux `AudioContext`),
  `partie.test.mjs`, `preparation.test.mjs` (fiche.js, apparence.js), `tete.test.mjs` (script classique exécuté par
  `vm` avec un faux `document`), `mj.test.mjs` (mode MJ : faux `fetch`, `sessionStorage` et fenêtre du mot de passe
  par `poserDialogueMdp`). Ils chargent leur module par son chemin.
- `tests/js/scene.test.mjs` charge scene.js depuis son texte (data: URL), univers.js et api.js par leur chemin (ils
  importent d'autres modules ; le package.json de la racine, `"type": "module"`, en fait des modules ES) ;
  `fauxFetch(reponses)` remplace `fetch` (et `document`/`localStorage` minimaux pour `chargerTheme`). Tests JS de
  `decouperNdjson`, `partieValide`, `fichesRelues`, `api`, `cssThemes` (couleurs piégées). package.json minimal
  (`npm test`, version de Node).
- Outillage : `ruff check .` (config dans pyproject.toml, doit rester vert), `pytest --cov` ; CI GitHub Actions
  `.github/workflows/tests.yml` (Linux et Windows, Python 3.11 et 3.13, Node 22 ; `UV_PYTHON` = version de la matrice,
  sinon `uv run` suit `.python-version` et recrée le .venv sans ruff ni pytest). `tests/e2e/donnees/config.toml`
  est versionné (fausse clé `sk-ant-factice`) ; `/config.toml` et `/pnj/` de la racine sont ignorés.
- e2e : `lancer.py` copie `tests/e2e/donnees/` (config.toml : moteurs locaux, voix Piper absente, reconnaissance
  « navigateur ») dans un dossier temporaire, lance `faux_ollama.py` (port 5918), le vrai serveur (5917) et
  `parcours_lieux.mjs`, qui pilote le navigateur par le protocole DevTools (port 9333). Ports réglables par
  `PNJ_E2E_PORT_OLLAMA`, `PNJ_E2E_PORT_SERVEUR`, `PNJ_E2E_PORT_DEVTOOLS` (lancer.py les écrit aussi dans le
  config.toml copié). Sorties du serveur et du faux Ollama gardées dans des journaux, affichés en cas d'échec ;
  `attendre()` vérifie `poll()` des processus ; un port déjà occupé arrête le test avant de le lancer.
  - Les simulations (`speechSynthesis` instantanée ou bloquée avec `window.__lent`, reconnaissance qui « entend »
    `window.__dicte`) sont évaluées après le chargement : `Page.addScriptToEvaluateOnNewDocument` ne prend pas en
    Edge sans écran.
  - Avant d'agir, attendre que le contrôle soit réactivé (`quand(...)`) : une action pendant une narration ou une
    réplique est ignorée (`busy`).
  - `faux_ollama.py` finit chaque réplique par `{"done": true}` (sans elle, le serveur juge le flux coupé net).
  - Le parcours commence sur `/#jeu` (bandeau : voix Piper absentes signalées, puis fermées ; Entrée dans « Métier »
    ignorée pendant une réplique), puis passe par l'accueil (barre d'espace sans effet, mode joueur puis bouton « MJ » : chargement d'univers et « Nouvelle
    table » cachés puis affichés, exemple Pré-Novice chargé
    deux fois : partie gardée si on refuse de la vider, vidée sinon ; son thème Parchemin, PNJ au
    hasard), un rechargement (conversation reprise, fiche modifiée sur le serveur relue), les options (onglet actif, barre du haut immobile, bouton « MJ » : mode joueur puis de nouveau MJ, sous-options
    grisées, réglage du serveur enregistré dans le config.toml temporaire), la liste « Modèle de l'IA » de la partie
    (`faux_ollama.py` liste `faux` et `autre` dans /api/tags ; changé puis remis), la page de
    préparation (onglets, « Créer un PNJ ici », point de modification, thème créé dans l'onglet Apparence, aventurier
    D&D créé dans l'onglet Aventuriers avec bonus affichés), la partie avec cet aventurier (« Vous jouez », jet de
    Persuasion, fiche et jet sans chiffre vus dans le corps de /api/npc/talk par un `fetch` espionné) et finit
    par « Nouvelle table » (destructive :
    toujours en dernier, suivie seulement d'une sauvegarde abîmée, écrite au `pagehide`, effacée au rechargement).
    `window.confirm` est remplacé par `() => true` avant les clics qui demandent confirmation.
  - Le serveur sur le réseau local (ex. 192.168.1.21:5000) peut être celui de l'utilisateur : ne pas le relancer ;
    pour essayer une page à la main, lancer une copie de `tests/e2e/donnees/` sur un autre port.
  - `tests/e2e/donnees/pnj/ysolde-0001.png` (8×8) : portrait affiché dans la fiche quand on aborde Ysolde.
  - Fin par `Browser.close` : sous Windows, `kill()` laisse vivre les processus d'Edge (port 9333 pris ensuite).
- Ajouter un test à chaque changement de logique ; pour jeu.js, options.js et creation.js (DOM), une étape dans l'e2e.
- Vérifier une page sans lancer tout l'e2e : servir une copie de `tests/e2e/donnees/` sur un autre port et lire la
  console d'Edge sans écran (`Runtime.exceptionThrown`) ; un renommage de variables peut passer `node --check` et
  casser la page (`...rencontres` oublié lors du passage à `partie`).
