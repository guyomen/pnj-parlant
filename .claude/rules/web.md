---
paths:
  - "src/pnj_parlant/static/**"
  - "tests/js/**"
  - "tests/e2e/**"
---

# Pages web : socle commun (index.html, creation.html, static/js/)

Règles par domaine : `partie.md` (vue Partie, micro), `reglages.md` (vue Options), `apparence.md` (thèmes, onglet
Apparence), `aventuriers.md`, `portraits.md` ; API du serveur : `serveur.md` et les règles de chaque domaine.

## Modules JS (lot 8)
- Les pages n'ont plus de JS en ligne : `index.html` charge `js/jeu.js` (accueil et partie ; il importe `js/options.js`,
  vue Options, à qui il passe `initOptions({config, chargerConfig})`), `creation.html` charge `js/creation.js`. Ces
  trois fichiers ne font que relier le DOM à la logique ; ils ne sont testés que par l'e2e.
- Logique sans DOM, chacune testée dans `tests/js/<module>.test.mjs` (scene.js et univers.js : `scene.test.mjs`) :
  `scene.js` (texte, scène, export, réglages, alertes), `partie.js` (état de la partie et transitions),
  `tours.js` (qui parle, hasard injecté), `controles.js` (`etatControles`), `micro.js`, `api.js` (requêtes, `apiStream`),
  `fiche.js` et `apparence.js` (page de préparation), `univers.js`, `aventurier.js` (aventurier joué, jets de dés,
  aperçu des bonus). `bandeau.js` : DOM par `globalThis.document`.
- `js/tete.js` : script classique (ni module, ni `defer`), chargé dans le `<head>` des deux pages avant `style.css` :
  pose `theme` et `theme-css` gardés avant l'affichage (pas de flash ; test `tete.test.mjs` dans un contexte `vm`).
- Toute nouvelle fonction testable sans DOM va dans le module de son domaine, avec son test dans `tests/js/`.
- Interface et commentaires en français ; texte de l'interface avec typographie française (« », ’, espaces).

## Pages
- `index.html` : un module (`js/jeu.js`) et trois vues selon l'adresse (`afficherVue`, `body[data-vue]`) :
  accueil `/` (charger un univers, PNJ au hasard ou inventé, créer son univers, « Nouvelle table »), partie `/#jeu`,
  options `/#options` (« Retour » vers la vue d'origine). Une seule page : le clic de l'accueil autorise le son du
  PNJ, et la partie continue pendant qu'on navigue. Changement de vue : titre de l'onglet du navigateur et focus sur
  le titre.
- « Nouvelle table » (`nouvelleTableBtn`) : `confirm(confirmationNouvelleTable)`, `DELETE /api/univers`, puis remise
  à zéro de la partie (npcs, history, rencontres, positions, lieu, journal, tokens, `CLE_PARTIE`) et rechargement
  des lieux, de la banque et du thème.
- `creation.html` (`js/creation.js`) : même principe d'une seule page, cinq parties selon l'adresse (`afficherSection`,
  `body[data-section]`, `nav.sections`) : Scénario `#scenario` (univers, notes du MJ, export/import), Apparence
  `#apparence` (voir `apparence.md`), Lieux `#lieux` (une `.carte.lieu-fiche` par lieu, PNJ qui y vivent, « Créer un
  PNJ ici » → `#pnj` avec `reqLieu`), PNJ `#pnj` (banque groupée par lieu via `parLieu`, `details#demande` ouvert pour
  une fiche vierge, fiche par rubriques, barre d'enregistrement collante), Aventuriers `#aventuriers` (voir
  `aventuriers.md`).
- `majModifs()` met un point (`.a-enregistrer`) sur l'onglet modifié : `scenarioModifie()`, `lieuxDirty`, `dirty`
  (fiche), `avDirty`, `apparenceModifiee()` (éditeur ouvert et modifié) ; recalculé après chaque
  `input`/`change`/`click` et après chaque chargement ou enregistrement.
- Fiche d'un PNJ : `fiche.js` (`CHAMPS_FICHE`, `valeursFormulaire`, `ficheDuFormulaire`, `secretMasque`, `titreFiche`,
  `voixDuGenre`, `initiale`, `corpsScenario`).
- `js/univers.js` : import (exemple, zip, dossier `webkitdirectory`), export, messages ; partagé par les deux pages
  (sa partie thèmes : `apparence.md`).

## Requêtes, alertes et accès (api.js, bandeau.js)
- Bandeau d'alertes (`js/bandeau.js`, élément `#bandeau` juste sous la barre du haut des deux pages, styles dans
  style.css) : `signaler(message, {cle, niveau: "erreur" | "avertissement"})` (même clé : remplacée, 5 au plus),
  `retirer(cle)`, `requete(url, opts)` (fetch qui signale « serveur injoignable » et retire l'alerte dès qu'une
  requête aboutit ; AbortError ignorée), `verifierSante()` (/api/sante : alertes `sante:<cle>` remplacées à chaque
  appel ; fermées = « clé|message » en sessionStorage `alertes-fermees`). Logique pure dans scene.js
  (`ajouterAlerte`, `alertesSante`, testées). bandeau.js n'utilise `document` que par `globalThis.document` (chargé
  sous Node par les tests).
- `js/api.js` (commun aux deux pages et à univers.js) : `api(path, body, method, {panne, signal, headers})` et
  `lireReponse(r, {panne})` (erreur du serveur en français ; `panne` : 5xx aussi au bandeau) ; toute requête passe
  par `requete` (jamais « Failed to fetch »). `apiStream` : lecteur relâché en `finally`, aussi quand `onItem` lève
  une erreur ; lignes découpées par `decouperNdjson` de scene.js, ligne illisible = erreur en français.
- Mot de passe du MJ (api.js) : `mdpMJ`/`garderMdp` (sessionStorage `mdp-mj`, partagé avec la page Options),
  `enTeteMdp` (en-tête encodé), `envoyer(path, opts)` (utilisé par `api`, l'import, les exemples et l'export de
  univers.js) : sur un 403 avec `mot_de_passe`, oublie le mot de passe refusé, ouvre `demanderMotDePasse`
  (`<dialog class="dialogue-mdp">`, une seule à la fois, remplaçable par `poserDialogueMdp` dans les tests) et renvoie
  la requête, jusqu'à « Annuler » (question de la première demande : option `message` de `envoyer` et de `api`) ;
  `verifierAcces({demander, message})` (/api/acces). Export : `fetch` + blob (`nomTelecharge`), plus de lien direct.
- jeu.js : `alerte(message, niveau, cle)` pour les erreurs des actions (création, banque, réplique, transcription,
  import, micro, `tts` en échec) ; `statut()` (ancien `status`, qui masquait `window.status`) reste pour les messages
  d'information. Diagnostic au chargement, toutes les minutes, à l'ouverture des options et après un changement de
  réglages.
- creation.html : `api` = celui de js/api.js avec `panne` (erreurs 5xx aussi au bandeau, en plus du message près de
  l'action) ; diagnostic au chargement ; données du serveur dans `innerHTML` toujours par `esc()`, identifiants dans
  les sélecteurs par `CSS.escape()`.
- Accès (décision D1, côté serveur : `serveur.md`) : au chargement de creation.html, `verifierAcces` (mot de passe
  demandé s'il existe) avant de lire scénario, lieux et banque ; refus ou « Annuler » = alerte `acces` « Lecture
  seule » (retirée après une écriture acceptée). Champs réservés au MJ absents de la réponse (`notes` du scénario,
  notes d'un lieu, `f-secret` d'une fiche de la banque) : grisés par `masquerChamp` et jamais renvoyés (le serveur
  garde la valeur) ; révélés par la réponse d'un enregistrement fait avec le mot de passe.

## Mise en page commune (style.css)
- Barre du haut commune (`header.entete` : marque + `nav.onglets` Accueil, Partie, Préparer l’univers, Options),
  même balisage dans les deux pages, styles dans `style.css` ; largeur fixe (`--page-large`), indépendante du contenu,
  et `scrollbar-gutter: stable` : elle ne bouge pas d'une page à l'autre (vérifié par l'e2e). Onglet actif :
  `aria-current="page"` (posé par `afficherVue` dans index.html, en dur dans creation.html).
- `style.css` : jetons (couleurs, `--rayon`, `--ombre`, `--page`, `--gouttiere`), `.page` + `.titre-page` (accueil,
  options, préparation), `.carte`, champs et boutons (`button.petit`), message d'état `.status` ; chaque page
  n'ajoute que sa mise en page. N'utiliser que les variables de couleur (jamais de couleur en dur : `--blanc` et
  `--noir` pour les reflets et ombres, `color-mix` avec `--ink` pour les teintes) : elles changent avec le thème
  (`apparence.md`). Un test JS le vérifie.
- Accessibilité et téléphone : un texte en cire s'écrit `color-mix(in srgb, var(--wax) 60%, var(--ink))` (la cire
  seule est trop claire en sombre) ; les noms des 2e et 3e PNJ ont un repère (`●`, `◆`) en plus de la couleur.
  `@media (pointer: coarse)` : cibles d'au moins 2,75 rem. `100dvh` après chaque `100vh`. `.controls` (Parler)
  est collé en bas de la partie (`.line` a un `scroll-margin-bottom`). Dégradés aux bords des onglets qui
  défilent. Les champs `number`, `url` et `password` suivent le thème comme `text`.
