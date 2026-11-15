---
paths:
  - "tests/**"
---

# Tests

Aucun ne demande réseau, modèle ni carte graphique.

```bash
pytest                       # Python ; pytest est dans l'option dev (uv sync --extra tout --extra dev)
node --test tests/js/        # fonctions pures de static/js/scene.js (Node 22+)
python tests/e2e/lancer.py   # parcours complet dans Edge ou Chrome sans écran (NAVIGATEUR=... pour le choisir)
```

- `conftest.py` : `FauxMoteurs`, `FauxTTS`, `FausseReconnaissance`, `FauxPortraits` (`PNG`, `erreur`, `actif`) ;
  fixtures `cfg` (config dans tmp_path), `moteurs`, `tts`, `portraits`, `app` (`create_app` avec les faux),
  `client`, `ctx`.
- `test_sante.py` : `Contexte.problemes` / `/api/sante`, avec `serveur.paquet_installe` et
  `serveur.systeme.etat_ollama` remplacés (aucun réseau). Tests JS : `ajouterAlerte`, `alertesSante`.
- `test_acces.py` (décision D1) : chaque route d'écriture depuis le PC, depuis une adresse distante sans mot de passe
  défini, avec mot de passe (absent, faux, bon, accentué) ; masquage des secrets et notes ; champ masqué gardé ;
  secret relu par /api/npc/talk ; `Origin` étranger ; `Frein` (horloge injectée) et verrou 429 ; tailles (413 : JSON,
  /api/stt, nombre et cumul de l'import, constantes de `serveur` remplacées par `monkeypatch`). Tests JS : `envoyer`
  (mot de passe demandé, gardé, oublié), `verifierAcces`, `nomTelecharge`.
- `test_reglages.py` : catalogue (défauts dans les bornes), `valider`, `ecrire` (commentaires gardés), routes
  `/api/reglages` (secret jamais renvoyé, application à chaud, refus sans rien écrire, mot de passe du MJ, appareil
  distant via `environ_base={"REMOTE_ADDR": …}`, `time.sleep` remplacé). `test_moteurs.py` couvre LM Studio
  (`urlopen` simulé, `etat_lmstudio`).
- `test_styles.py` : `valider_styles` (refus, injection CSS impossible), `prompt_du_style`, stockage, export/import,
  « Nouvelle table », routes `/api/styles`. Tests JS : palettes de `THEMES` = style.css et lisibles, `cssThemes`,
  `tousLesThemes`, `contraste`, `identifiant`.
- `test_portraits.py` : description (modèle de langage ou repli), moteurs (Pollinations simulé par `urlopen`),
  stockage, export/import, routes. Aucun test ne charge diffusers ni ne contacte Pollinations.
- `test_exemples.py` : chaque dossier de `src/pnj_parlant/exemples/` (avec `_infos.json`) se charge comme une banque,
  fiches conformes au schéma, lieux existants, pas de `voix` (attribuée par le serveur selon la machine), thème
  présent dans `style.css`.
- `tests/js/scene.test.mjs` charge scene.js depuis son texte (data: URL), univers.js et api.js par leur chemin (ils
  importent d'autres modules ; le package.json de la racine, `"type": "module"`, en fait des modules ES) ;
  `fauxFetch(reponses)` remplace `fetch` (et `document`/`localStorage` minimaux pour `chargerTheme`). Tests JS de
  `decouperNdjson`, `partieValide`, `fichesRelues`, `api`, `cssThemes` (couleurs piégées). package.json minimal
  (`npm test`, version de Node).
- Outillage : `ruff check .` (config dans pyproject.toml, doit rester vert), `pytest --cov` ; CI GitHub Actions
  `.github/workflows/tests.yml` (Linux et Windows, Python 3.11 et 3.13, Node 22). `tests/e2e/donnees/config.toml`
  est versionné (fausse clé `sk-ant-factice`) ; `/config.toml` et `/pnj/` de la racine sont ignorés.
- e2e : `lancer.py` copie `tests/e2e/donnees/` (config.toml : moteurs locaux, voix Piper absente, reconnaissance
  « navigateur ») dans un dossier temporaire, lance `faux_ollama.py` (port 5918), le vrai serveur (5917) et
  `parcours_lieux.mjs`, qui pilote le navigateur par le protocole DevTools (port 9333).
  - Les simulations (`speechSynthesis` instantanée ou bloquée avec `window.__lent`, reconnaissance qui « entend »
    `window.__dicte`) sont évaluées après le chargement : `Page.addScriptToEvaluateOnNewDocument` ne prend pas en
    Edge sans écran.
  - Avant d'agir, attendre que le contrôle soit réactivé (`quand(...)`) : une action pendant une narration ou une
    réplique est ignorée (`busy`).
  - `faux_ollama.py` finit chaque réplique par `{"done": true}` (sans elle, le serveur juge le flux coupé net).
  - Le parcours commence sur `/#jeu` (bandeau : voix Piper absentes signalées, puis fermées ; Entrée dans « Métier »
    ignorée pendant une réplique), puis passe par l'accueil (barre d'espace sans effet, exemple Pré-Novice chargé
    deux fois : partie gardée si on refuse de la vider, vidée sinon ; son thème Parchemin, PNJ au
    hasard), un rechargement (conversation reprise, fiche modifiée sur le serveur relue), les options (onglet actif, barre du haut immobile, sous-options
    grisées, réglage du serveur enregistré dans le config.toml temporaire), la page de
    préparation (onglets, « Créer un PNJ ici », point de modification, thème créé dans l'onglet Apparence) et finit
    par « Nouvelle table » (destructive :
    toujours en dernier, suivie seulement d'une sauvegarde abîmée, écrite au `pagehide`, effacée au rechargement).
    `window.confirm` est remplacé par `() => true` avant les clics qui demandent confirmation.
  - Le serveur sur le réseau local (ex. 192.168.1.21:5000) peut être celui de l'utilisateur : ne pas le relancer ;
    pour essayer une page à la main, lancer une copie de `tests/e2e/donnees/` sur un autre port.
  - `tests/e2e/donnees/pnj/ysolde-0001.png` (8×8) : portrait affiché dans la fiche quand on aborde Ysolde.
  - Fin par `Browser.close` : sous Windows, `kill()` laisse vivre les processus d'Edge (port 9333 pris ensuite).
- Ajouter un test à chaque changement de logique ; pour index.html, une étape dans l'e2e.
