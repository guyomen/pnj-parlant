---
paths:
  - "src/pnj_parlant/static/**"
  - "tests/js/**"
  - "tests/e2e/**"
---

# Pages web (index.html, creation.html, js/scene.js)

- `index.html` : un seul `<script type="module">` et trois vues selon l'adresse (`afficherVue`, `body[data-vue]`) :
  accueil `/` (charger un univers, PNJ au hasard ou inventé, créer son univers), partie `/#jeu`, options `/#options`
  (cases à cocher, modèle local, état machine ; « Retour » vers la vue d'origine). Une seule page : le clic de
  l'accueil autorise le son du PNJ, et la partie continue pendant qu'on navigue.
- `creation.html` (module ES) : scénario, lieux, fiches, banque, export/import de l'univers.
- Barre du haut commune (`header.entete` : marque + `nav.onglets` Accueil, Partie, Préparer l’univers, Options),
  même balisage dans les deux pages, styles dans `style.css` ; largeur fixe (`--page-large`), indépendante du contenu,
  et `scrollbar-gutter: stable` : elle ne bouge pas d'une page à l'autre (vérifié par l'e2e). Onglet actif :
  `aria-current="page"` (posé par `afficherVue` dans index.html, en dur dans creation.html).
- `style.css` : jetons (couleurs, `--rayon`, `--ombre`, `--page`, `--gouttiere`), `.page` + `.titre-page` (accueil,
  options, préparation), `.carte`, champs et boutons ; chaque page n'ajoute que sa mise en page. N'utiliser que les
  variables de couleur (jamais de couleur en dur) : elles changent avec le thème.

## Thèmes graphiques
- Choisi par le scénario (`theme` de `_scenario.json`), posé sur `<html data-theme>` ; vide ou inconnu = défaut.
- Couleurs dans `style.css` : un bloc `[data-theme=<id>]` (clair) + son `@media (prefers-color-scheme: dark)` par
  thème ; `:root, [data-theme=vert-de-gris]` = défaut ; `donjon` toujours sombre. Variables : `--bg --surface --ink
  --muted --line --glass` (principale, texte des boutons = `--surface`) `--verdigris` (appoint) `--wax --wax-ink`
  (sceau « Parler »). Contraste visé ≥ 4,5 pour ink/bg, muted/surface, surface/glass, wax-ink/wax.
- Liste (id, nom, résumé) : `THEMES` dans `js/univers.js` ; `appliquerTheme(id)` (pose + garde dans localStorage
  `theme`), `chargerTheme()` (relit /api/scenario). Un petit script dans le `<head>` des deux pages pose le thème
  gardé avant l'affichage (pas de flash), puis `chargerTheme()` au chargement et après un import d'univers.
- Préparation : `fieldset#themes`, une carte par thème portant son propre `data-theme` (aperçu dans ses couleurs) ;
  le clic essaie le thème sans le garder, « Enregistrer le scénario » l'envoie (`themeChoisi`, `nonEnregistre`).
- Ajouter un thème : bloc(s) dans `style.css` + entrée dans `THEMES` (le serveur accepte tout id `[a-z0-9-]`).
- `js/univers.js` : import (exemple, zip, dossier `webkitdirectory`), export, messages ; partagé par les deux pages.
- Toute fonction testable sans DOM va dans `static/js/scene.js` (export) avec son test dans
  `tests/js/scene.test.mjs` ; index.html n'est testé que par l'e2e.
- Interface et commentaires en français ; texte de l'interface avec typographie française (« », ’, espaces).

## État de la page de jeu
- `npcs` (scène, 3 au plus), `history` (envoyé tel quel à /api/npc/talk), `dernier` (répond si personne n'est
  nommé), `rencontres` (pour l'export), `lieuActuel`, `positions` (nom → lieu pendant la partie), `ici`.
- `busy` + `setBusy(b)` : active/désactive tous les contrôles ; `libre()` attend la fin de l'action en cours.
- `parole` (`debutParole` / `finParole` / `stopNpc`) : prise de parole en cours, `{ctrl: AbortController, stop}`.
  Stop/Échap annule requêtes et son ; une réplique interrompue est raccourcie dans `history` à ce qui a été dit.
- Options mémorisées dans localStorage (`OPTIONS`, `DESACTIVEES` = désactivées par défaut).
- Conversation gardée dans localStorage (`CLE_PARTIE` : rencontres, scène, history, lieu, positions, journal
  affiché, tokens) : `sauverPartie` à chaque `setBusy(false)`, `retirer` et `pagehide` ; `restaurerPartie` au
  chargement (après les lieux et la banque ; aucune sauvegarde avant, `partieRestauree`).

## Dialogue côté navigateur
- Répond le PNJ cité (`interpelles` : nom ou métier), sinon `dernier` ; un PNJ questionné par un autre répond juste
  après (`questionnes`, `MAX_TOURS` = 4 répliques d'affilée). Options « Interventions spontanées »
  (`[dialogue] intervention`), « Laissez-les discuter », « Faire entrer » (`consignesEntree` → /api/npc/generate).
- `jouerTours` / `tourDe` : chaque phrase reçue est synthétisée tout de suite (`prepareSpeech`) et dite à la suite ;
  le PNJ suivant écrit pendant que le précédent parle. Texte entre parenthèses (`segments`) : voix du narrateur,
  en italique (`formatLine`).
- Lieux : menu du lieu, PNJ présents (« Aborder »), compagnons (case « Vous accompagne », `suit`), positions
  (`position`, `parLieu` : fiche « Se trouve », banque groupée par lieu), « allons à la forge » → proposition
  (`lieuEvoque`), narration d'arrivée (`arrivee`).
- Export texte (`texteExport`, `nomFichierExport`) et import (`lireExport`, anciens exports compris) : PNJ de la
  banque, sinon recréés (`consignesRecreation`) ; restent en scène ceux qui ont parlé depuis la dernière arrivée
  dans un lieu (`sceneImportee`).

## Micro
- Le micro exige `localhost` ou HTTPS. `listenLocal(ouvert)` : MediaRecorder + seuil adaptatif, arrêt après
  1,2 s de silence, puis /api/stt ; sinon Web Speech API (`recognition`).
- Couper la parole au PNJ : option « Parler interrompt le PNJ » (`optInterrompre` : bouton actif pendant la
  `parole`, barre d'espace) ; option « Couper le PNJ dès que vous parlez » (`optCoupure`, désactivée par défaut :
  `veiller` ouvre le micro pendant la `parole`, `detecteurVoix` décide, puis `listenLocal({stream, bruit})`
  continue sur le même micro). L'écho des haut-parleurs peut déclencher : casque conseillé.
