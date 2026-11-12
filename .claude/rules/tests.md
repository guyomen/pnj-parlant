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

- `conftest.py` : `FauxMoteurs`, `FauxTTS`, `FausseReconnaissance` ; fixtures `cfg` (config dans tmp_path),
  `moteurs`, `tts`, `app` (`create_app` avec les faux), `client`, `ctx`.
- `test_exemples.py` : chaque dossier de `src/pnj_parlant/exemples/` (avec `_infos.json`) se charge comme une banque,
  fiches conformes au schéma, lieux existants, pas de `voix` (attribuée par le serveur selon la machine), thème
  présent dans `style.css`.
- `tests/js/scene.test.mjs` charge scene.js depuis son texte (data: URL), sans package.json.
- e2e : `lancer.py` copie `tests/e2e/donnees/` (config.toml : moteurs locaux, voix Piper absente, reconnaissance
  « navigateur ») dans un dossier temporaire, lance `faux_ollama.py` (port 5918), le vrai serveur (5917) et
  `parcours_lieux.mjs`, qui pilote le navigateur par le protocole DevTools (port 9333).
  - Les simulations (`speechSynthesis` instantanée ou bloquée avec `window.__lent`, reconnaissance qui « entend »
    `window.__dicte`) sont évaluées après le chargement : `Page.addScriptToEvaluateOnNewDocument` ne prend pas en
    Edge sans écran.
  - Avant d'agir, attendre que le contrôle soit réactivé (`quand(...)`) : une action pendant une narration ou une
    réplique est ignorée (`busy`).
  - Le parcours commence sur `/#jeu`, puis passe par l'accueil (exemple Pré-Novice et son thème Parchemin, PNJ au
    hasard), un rechargement (conversation reprise), les options (onglet actif, barre du haut immobile), la page de
    préparation (onglets, « Créer un PNJ ici », point de modification) et finit par « Nouvelle table » (destructive :
    toujours en dernier). `window.confirm` est remplacé par `() => true` avant les clics qui demandent confirmation.
  - Le serveur sur le réseau local (ex. 192.168.1.21:5000) peut être celui de l'utilisateur : ne pas le relancer ;
    pour essayer une page à la main, lancer une copie de `tests/e2e/donnees/` sur un autre port.
  - Fin par `Browser.close` : sous Windows, `kill()` laisse vivre les processus d'Edge (port 9333 pris ensuite).
- Ajouter un test à chaque changement de logique ; pour index.html, une étape dans l'e2e.
