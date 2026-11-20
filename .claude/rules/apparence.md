---
paths:
  - "src/pnj_parlant/static/style.css"
  - "src/pnj_parlant/static/js/univers.js"
  - "src/pnj_parlant/static/js/apparence.js"
  - "src/pnj_parlant/static/js/tete.js"
  - "tests/test_styles.py"
  - "tests/js/scene.test.mjs"
  - "tests/js/tete.test.mjs"
  - "tests/js/preparation.test.mjs"
---

# Thèmes graphiques, styles de portrait et onglet Apparence

## Serveur : GET|PUT /api/styles
- `pnj/_styles.json`, `Banque.styles` / `enregistrer_styles`, `valider_styles` (400 si invalide) : thèmes
  `{id: {nom, resume, mode (auto|sombre|clair), clair, sombre}}` (les 9 couleurs `#rrggbb` de `COULEURS`, seulement
  les palettes du mode ; aucune injection CSS possible) et styles de portrait `{id: {nom, resume, prompt}}`, 30 de
  chaque au plus. Un id prédéfini = remplacement pour l'univers. GET renvoie
  `{themes, portraits: portraits.styles(perso)}` (liste complète avec `origine`). Exporté, importé (écrit avant le
  scénario, illisible → `ignores`), vidé par « Nouvelle table ».
- Le thème choisi est `theme` de `/api/scenario` (`banque.theme_valide`, voir `univers.md`).

## Thèmes (style.css, js/univers.js)
- Choisi par le scénario (`theme` de `_scenario.json`), posé sur `<html data-theme>` ; vide ou inconnu = défaut.
- Couleurs dans `style.css` : un bloc `[data-theme=<id>]` (clair) + son `@media (prefers-color-scheme: dark)` par
  thème ; `:root, [data-theme=vert-de-gris]` = défaut ; `donjon` toujours sombre. Variables : `--bg --surface --ink
  --muted --line --glass` (principale, texte des boutons = `--surface`) `--verdigris` (appoint) `--wax --wax-ink`
  (sceau « Parler »). Contrastes visés (`PAIRES` dans js/univers.js, contrôlés pour chaque thème) : ≥ 4,5 pour les
  textes (ink, muted, glass sur bg et surface ; surface/glass ; wax-ink/wax ; cire mêlée d'encre) et ≥ 3 pour
  `--verdigris` (anneau de focus) sur bg et surface.
- `js/univers.js` : `THEMES` = prédéfinis avec leurs palettes (`mode`, `clair`, `sombre`), **identiques à style.css**
  (test JS qui les compare, et qui vérifie leurs contrastes) ; `COULEURS` (variables + libellés de l'éditeur),
  `tousLesThemes(perso)` (origine predefini / modifie / perso), `cssThemes(perso)` (sélecteurs `html[data-theme="id"],
  body [data-theme="id"]` : plus précis que style.css, donc gagnants même placés avant ; `body […]` pour les
  aperçus), `contraste`, `melange`, `alertesContraste`, `identifiant(nom, pris)`, `poserThemesPerso(perso, garder)`
  (`<style id="themes-perso">` ; garder = aussi dans localStorage `theme-css`, sinon simple aperçu),
  `appliquerTheme(id)` (prédéfini ou de l'univers, sinon défaut ; localStorage `theme`), `chargerTheme()`
  (/api/scenario + /api/styles ; réponse en erreur = rien n'est appliqué ni mémorisé). `cssThemes` ignore un thème au
  mode inconnu ou à une couleur qui n'est pas `#rrggbb` (le serveur les refuse déjà).
- Le script du `<head>` des deux pages (`js/tete.js`) pose `theme` et `theme-css` gardés avant l'affichage (pas de
  flash).
- Ajouter un thème prédéfini : bloc(s) dans `style.css` + même palette dans `THEMES` (le test JS le vérifie).

## Onglet Apparence (creation.html, js/creation.js, js/apparence.js)
- Thèmes et styles de l'univers : `/api/styles` (`stylesUnivers` = {themes: {id: thème}, portraits: liste complète}),
  PUT de tout (`enregistrerStyles(themes, portraitsPerso())`). Chargés avant le scénario (`chargerStyles().then(
  loadScenario)`, idem après un import) : le thème ou le style choisi peut en venir.
- Cartes de thèmes (`.theme-carte` : `label.theme-choix[data-theme]` + « Modifier ») et de styles (`.style-carte`) ;
  un clic sur une carte choisit et enregistre aussitôt. Éditeur de thème (`editionTheme`, `#editeurTheme`) : palettes
  en `input[type=color]` (`data-mode`, `data-couleur`), aperçu en direct sur toute la page (`apercuTheme` :
  `poserThemesPerso(…, false)`, id `apercu-theme` pour un nouveau), alertes de contraste ; un nouveau thème part du
  thème choisi et est choisi à l'enregistrement ; prédéfini modifié → « Rétablir » (retire l'entrée), créé →
  « Supprimer » (le scénario revient au thème par défaut s'il l'utilisait). Éditeur de style (`editionStyle`,
  `#editeurStyle`) : nom, résumé, prompt anglais, même logique. Un seul éditeur ouvert à la fois.
- Éditeurs jumeaux (thème, style) : textes communs dans `apparence.js` (`libelleSuppression`,
  `confirmationSuppression`, `messageSuppression` par type `"theme"`/`"style"`), `editionDeTheme`, `themeEdite`,
  `palettesDuMode`, `alertesPalettes`, `portraitsPerso`, `mention`.
- Style des portraits : `#stylesCarte` cachée sans moteur de portraits ; "" affiché comme le premier ; rappelé dans
  la fiche (`#portraitStyle`). Tout enregistrement du scénario passe par `enregistrerScenario(changements)` = PUT
  `{...scenarioCharge, ...changements}` : version *enregistrée* (pas la saisie en cours), un champ n'en efface pas
  un autre.
