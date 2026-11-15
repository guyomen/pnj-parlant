---
paths:
  - "src/pnj_parlant/static/**"
  - "tests/js/**"
  - "tests/e2e/**"
---

# Pages web (index.html, creation.html, js/scene.js)

- `index.html` : un seul `<script type="module">` et trois vues selon l'adresse (`afficherVue`, `body[data-vue]`) :
  accueil `/` (charger un univers, PNJ au hasard ou inventé, créer son univers, « Nouvelle table »), partie `/#jeu`,
  options `/#options` (voir « Page Options » ; « Retour » vers la vue d'origine). Une seule page : le clic de
  l'accueil autorise le son du PNJ, et la partie continue pendant qu'on navigue.
- « Nouvelle table » (`nouvelleTableBtn`) : `confirm(confirmationNouvelleTable)`, `DELETE /api/univers`, puis remise
  à zéro de la partie (npcs, history, rencontres, positions, lieu, journal, tokens, `CLE_PARTIE`) et rechargement
  des lieux, de la banque et du thème.
- `creation.html` (module ES) : même principe d'une seule page, quatre parties selon l'adresse (`afficherSection`,
  `body[data-section]`, `nav.sections`) : Scénario `#scenario` (univers, notes du MJ, export/import), Apparence
  `#apparence` (thèmes et styles de portrait, voir plus bas), Lieux `#lieux` (une `.carte.lieu-fiche` par lieu, PNJ qui y vivent, « Créer un PNJ ici » →
  `#pnj` avec `reqLieu`), PNJ `#pnj` (banque groupée par lieu via `parLieu`, `details#demande` ouvert pour une
  fiche vierge, fiche par rubriques, barre d'enregistrement collante). `majModifs()` met un point
  (`.a-enregistrer`) sur l'onglet modifié : `scenarioModifie()`, `lieuxDirty`, `dirty` (fiche),
  `apparenceModifiee()` (éditeur ouvert et modifié) ; recalculé après
  chaque `input`/`change`/`click` et après chaque chargement ou enregistrement.
- Bandeau d'alertes (`js/bandeau.js`, élément `#bandeau` juste sous la barre du haut des deux pages, styles dans
  style.css) : `signaler(message, {cle, niveau: "erreur" | "avertissement"})` (même clé : remplacée, 5 au plus),
  `retirer(cle)`, `requete(url, opts)` (fetch qui signale « serveur injoignable » et retire l'alerte dès qu'une
  requête aboutit ; AbortError ignorée), `verifierSante()` (/api/sante : alertes `sante:<cle>` remplacées à chaque
  appel ; fermées = « clé|message » en sessionStorage `alertes-fermees`). Logique pure dans scene.js
  (`ajouterAlerte`, `alertesSante`, testées). `js/api.js` (commun aux deux pages et à univers.js) : `api(path, body,
  method, {panne, signal, headers})` et `lireReponse(r, {panne})` (erreur du serveur en français ; `panne` : 5xx
  aussi au bandeau) ; toute requête passe par `requete` (jamais « Failed to fetch »). Mot de passe du MJ (api.js) :
  `mdpMJ`/`garderMdp` (sessionStorage `mdp-mj`, partagé avec la page Options), `enTeteMdp` (en-tête encodé),
  `envoyer(path, opts)` (utilisé par `api`, l'import, les exemples et l'export de univers.js) : sur un 403 avec
  `mot_de_passe`, oublie le mot de passe refusé, ouvre `demanderMotDePasse` (`<dialog class="dialogue-mdp">`, une
  seule à la fois, remplaçable par `poserDialogueMdp` dans les tests) et renvoie la requête, jusqu'à « Annuler » ;
  `verifierAcces({demander, message})` (/api/acces). Export : `fetch` + blob (`nomTelecharge`), plus de lien direct. bandeau.js n'utilise
  `document` que par `globalThis.document` (chargé sous Node par les tests). index.html : `apiStream` (lecteur
  relâché en `finally`, lignes découpées par `decouperNdjson` de scene.js, ligne illisible = erreur en français) ; `alerte(message,
  niveau, cle)` pour les erreurs des actions (création, banque, réplique, transcription, import, micro, `tts` en
  échec) ; `status()` reste pour les messages d'information. Diagnostic au chargement, toutes les minutes, à
  l'ouverture des options et après un changement de réglages. creation.html : `api` = celui de js/api.js avec
  `panne` (erreurs 5xx aussi au bandeau, en plus du message près de l'action) ; diagnostic au chargement ; données
  du serveur dans `innerHTML` toujours par `esc()`, identifiants dans les sélecteurs par `CSS.escape()`.
  Accès (décision D1) : au chargement, `verifierAcces` (mot de passe demandé s'il existe) avant de lire scénario,
  lieux et banque ; refus ou « Annuler » = alerte `acces` « Lecture seule » (retirée après une écriture acceptée).
  Champs réservés au MJ absents de la réponse (`notes` du scénario, notes d'un lieu, `f-secret` d'une fiche de la
  banque) : grisés par `masquerChamp` et jamais renvoyés (le serveur garde la valeur) ; révélés par la réponse d'un
  enregistrement fait avec le mot de passe.
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
- `js/univers.js` : `THEMES` = prédéfinis avec leurs palettes (`mode`, `clair`, `sombre`), **identiques à style.css**
  (test JS qui les compare, et qui vérifie leurs contrastes) ; `COULEURS` (variables + libellés de l'éditeur),
  `tousLesThemes(perso)` (origine predefini / modifie / perso), `cssThemes(perso)` (sélecteurs `html[data-theme="id"],
  body [data-theme="id"]` : plus précis que style.css, donc gagnants même placés avant ; `body […]` pour les
  aperçus), `contraste`, `alertesContraste`, `identifiant(nom, pris)`, `poserThemesPerso(perso, garder)` (`<style
  id="themes-perso">` ; garder = aussi dans localStorage `theme-css`, sinon simple aperçu), `appliquerTheme(id)`
  (prédéfini ou de l'univers, sinon défaut ; localStorage `theme`), `chargerTheme()` (/api/scenario + /api/styles ;
  réponse en erreur = rien n'est appliqué ni mémorisé). `cssThemes` ignore un thème au mode inconnu ou à une couleur
  qui n'est pas `#rrggbb` (le serveur les refuse déjà).
  Le script du `<head>` des deux pages pose `theme` et `theme-css` gardés avant l'affichage (pas de flash).
- Thèmes et styles de l'univers : `/api/styles` (`stylesUnivers` = {themes: {id: thème}, portraits: liste complète}),
  PUT de tout (`enregistrerStyles(themes, portraitsPerso())`). Chargés avant le scénario (`chargerStyles().then(
  loadScenario)`, idem après un import) : le thème ou le style choisi peut en venir.
- Onglet Apparence : cartes de thèmes (`.theme-carte` : `label.theme-choix[data-theme]` + « Modifier ») et de styles
  (`.style-carte`) ; un clic sur une carte choisit et enregistre aussitôt. Éditeur de thème (`editionTheme`,
  `#editeurTheme`) : palettes en `input[type=color]` (`data-mode`, `data-couleur`), aperçu en direct sur toute la page
  (`apercuTheme` : `poserThemesPerso(…, false)`, id `apercu-theme` pour un nouveau), alertes de contraste ; un nouveau
  thème part du thème choisi et est choisi à l'enregistrement ; prédéfini modifié → « Rétablir » (retire l'entrée),
  créé → « Supprimer » (le scénario revient au thème par défaut s'il l'utilisait). Éditeur de style (`editionStyle`,
  `#editeurStyle`) : nom, résumé, prompt anglais, même logique. Un seul éditeur ouvert à la fois.
- Style des portraits : `#stylesCarte` cachée sans moteur de portraits ; "" affiché comme le premier ; rappelé dans
  la fiche (`#portraitStyle`). Tout enregistrement du scénario passe par `enregistrerScenario(changements)` = PUT
  `{...scenarioCharge, ...changements}` : version *enregistrée* (pas la saisie en cours), un champ n'en efface pas un autre.
- Ajouter un thème prédéfini : bloc(s) dans `style.css` + même palette dans `THEMES` (le test JS le vérifie).
- Portraits : `adressePortrait(pnj)` (scene.js) = `/api/bank/<id>/portrait?v=<version>` ou "" ; partie :
  `img.portrait` en tête de `.pnj-card` (grand pour le premier, vignette flottante sinon) ; préparation :
  `figure#portraitBloc` à droite de l'identité (`majPortrait`, `peinture` pendant la génération, seulement pour un
  PNJ enregistré, visible si `/api/config` donne un moteur ou si le PNJ a déjà un portrait) et vignettes dans la
  banque (`vignette`). Import d'un dossier : `fichiersImportables` garde aussi png/jpg/webp.
- `js/univers.js` : import (exemple, zip, dossier `webkitdirectory`), export, messages ; partagé par les deux pages.
- Toute fonction testable sans DOM va dans `static/js/scene.js` (export) avec son test dans
  `tests/js/scene.test.mjs` ; index.html n'est testé que par l'e2e.
- Interface et commentaires en français ; texte de l'interface avec typographie française (« », ’, espaces).

## Page Options (index.html, `#options`)
- Rubriques (`#optionsNav`, construites par `construireNav` d'après les `section[id][data-titre]` de
  `.options-contenu`, intercalaires « Ce navigateur » / « Le serveur » / « État ») ; un clic fait défiler.
- « Cette partie » : réglages du navigateur (`OPTIONS` en localStorage), en lignes `.reglage` (libellé + aide |
  contrôle) avec interrupteurs (`input.interrupteur[role=switch]`, style.css) ; `#multiOpts` grisé et désactivé sans
  `optMulti` (dans `setBusy`).
- « Le serveur » : `chargerReglages()` à l'ouverture de la vue (différé par `queueMicrotask` : au premier affichage,
  le code plus bas n'a pas encore tourné), champs générés d'après le catalogue (`controle(r)`), `modifsReglages`
  (valeur revenue à l'origine = retirée ; secret : "" ignoré, « Effacer » = null), point `.modifie`, barre collante
  « N réglages modifiés » (`resumeModifs`), groupes des moteurs non choisis en retrait (`groupeUtile`, recalculé si
  `moteurs.*` change). Accès (`afficherAcces`) : déverrouillé / formulaire du mot de passe / modifiable depuis ce PC /
  lecture seule ; mot de passe gardé en sessionStorage `mdp-mj`, envoyé en `X-Mot-De-Passe-MJ`, oublié sur 403
  (champs réaffichés verrouillés, modifications gardées). `controle(r)` affiche la valeur en attente s'il y en a
  une ; « Verrouiller » abandonne les modifications ; un nombre vidé reprend sa valeur en quittant le champ.
  Après enregistrement : message (fichier, réglages au redémarrage), `chargerConfig()` (la partie reprend les
  moteurs) et `refreshSys()`. `beforeunload` si des modifications attendent.
- « État » (`refreshSys`, toutes les 3 s seulement sur la vue Options) : moteurs (/api/config), Ollama, LM Studio, GPU.
- Fonctions pures (scene.js, testées) : `valeurReglage(type, champ)`, `groupeUtile(groupe, valeurs)`, `resumeModifs(n)`.

## État de la page de jeu
- `npcs` (scène, `maxPnj` au plus : `pnj_max` de /api/config, 3 par défaut ; message d'information au-delà de 3), `history` (envoyé tel quel à /api/npc/talk), `dernier` (répond si personne n'est
  nommé), `rencontres` (pour l'export), `lieuActuel`, `positions` (nom → lieu pendant la partie), `ici`.
- `busy` + `setBusy(b)` : active/désactive tous les contrôles ; `libre()` attend la fin de l'action en cours.
- `parole` (`debutParole` / `finParole` / `stopNpc`) : prise de parole en cours, `{ctrl: AbortController, stop}`.
  Stop/Échap annule requêtes et son ; une réplique interrompue est raccourcie dans `history` à ce qui a été dit.
- Options mémorisées dans localStorage (`OPTIONS`, `DESACTIVEES` = désactivées par défaut).
- Conversation gardée dans localStorage (`CLE_PARTIE` : `version` (`VERSION_PARTIE`), rencontres, scène, history,
  lieu, positions, journal affiché, tokens) : `sauverPartie` à chaque `setBusy(false)`, `retirer` et `pagehide`
  (stockage refusé : une alerte `sauvegarde`, une fois) ; `restaurerPartie` au chargement, seulement si les lieux et
  la banque ont été lus (`chargerLieux`/`refreshBank` renvoient faux sinon ; aucune sauvegarde avant,
  `partieRestauree`). Sauvegarde vérifiée par `partieValide` (scene.js) ; illisible ou en échec → clé effacée,
  `viderPartie()`, alerte. Décision D5 : les fiches de la banque sont relues (`/api/bank/<id>`, 404 ou PNJ inventé
  = copie gardée) et fusionnées par `fichesRelues` (scene.js : garde nom, `suit` et voix réattribuée).
- `viderPartie()` : remise à zéro de la partie (« Nouvelle table », nouvel univers chargé depuis l'accueil si le
  joueur accepte `confirmationViderPartie` ; « Annuler » garde la partie).
- Gardes : `generate`/`loadFromBank` ne font rien si `busy` ; `debutParole` fait taire une parole en cours ;
  `jouerTours`, `saluer`, `changerLieu` en `try/finally` (contrôles toujours réactivés) ; `send`/`discuter` appelés
  avec `.catch` ; question dictée refusée (`envoyerDictee`) laissée dans le champ.

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
  1,2 s de silence, puis /api/stt (via `requete`, annulée par Échap : `transcription`) ; sinon Web Speech API
  (`recognition`, démarrée par `ecouterNavigateur` : `start()` sous `try`). `ecouteLocale` est posé avant
  `getUserMedia` (pas de double écoute) ; la minuterie arrête son propre enregistrement (`arreter`), pas la globale
  `stopListening`. Barre d'espace = « Parler » seulement dans la vue `jeu`.
- Couper la parole au PNJ : option « Parler interrompt le PNJ » (`optInterrompre` : bouton actif pendant la
  `parole`, barre d'espace) ; option « Couper le PNJ dès que vous parlez » (`optCoupure`, désactivée par défaut :
  `veiller` ouvre le micro pendant la `parole`, `detecteurVoix` décide, puis `listenLocal({stream, bruit})`
  continue sur le même micro). L'écho des haut-parleurs peut déclencher : casque conseillé.
