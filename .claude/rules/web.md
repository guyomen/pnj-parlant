---
paths:
  - "src/pnj_parlant/static/**"
  - "tests/js/**"
  - "tests/e2e/**"
---

# Pages web (index.html, creation.html, static/js/)

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

## Pages
- `index.html` : un module (`js/jeu.js`) et trois vues selon l'adresse (`afficherVue`, `body[data-vue]`) :
  accueil `/` (charger un univers, PNJ au hasard ou inventé, créer son univers, « Nouvelle table »), partie `/#jeu`,
  options `/#options` (voir « Page Options » ; « Retour » vers la vue d'origine). Une seule page : le clic de
  l'accueil autorise le son du PNJ, et la partie continue pendant qu'on navigue.
- « Nouvelle table » (`nouvelleTableBtn`) : `confirm(confirmationNouvelleTable)`, `DELETE /api/univers`, puis remise
  à zéro de la partie (npcs, history, rencontres, positions, lieu, journal, tokens, `CLE_PARTIE`) et rechargement
  des lieux, de la banque et du thème.
- `creation.html` (`js/creation.js`) : même principe d'une seule page, cinq parties selon l'adresse (`afficherSection`,
  `body[data-section]`, `nav.sections`) : Scénario `#scenario` (univers, notes du MJ, export/import), Apparence
  `#apparence` (thèmes et styles de portrait, voir plus bas), Lieux `#lieux` (une `.carte.lieu-fiche` par lieu, PNJ qui y vivent, « Créer un PNJ ici » →
  `#pnj` avec `reqLieu`), PNJ `#pnj` (banque groupée par lieu via `parLieu`, `details#demande` ouvert pour une
  fiche vierge, fiche par rubriques, barre d'enregistrement collante), Aventuriers `#aventuriers` (liste `#avListe`,
  fiche `av-*` : identité, portrait `#avPortraitBloc` comme celui d'un PNJ, système de jeu de /api/systemes,
  `#avStats` construit par `renderStats` : caractéristiques, compétences D&D (maîtrise/expertise) ou capacités COF,
  bonus en aperçu `majBonus` → `apercuBonus` ; `lireAv` lit la fiche ; changer de système repart des valeurs par
  défaut). `majModifs()` met un point
  (`.a-enregistrer`) sur l'onglet modifié : `scenarioModifie()`, `lieuxDirty`, `dirty` (fiche), `avDirty`,
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
  seule à la fois, remplaçable par `poserDialogueMdp` dans les tests) et renvoie la requête, jusqu'à « Annuler »
  (question de la première demande : option `message` de `envoyer` et de `api`) ;
  `verifierAcces({demander, message})` (/api/acces). Export : `fetch` + blob (`nomTelecharge`), plus de lien direct. bandeau.js n'utilise
  `document` que par `globalThis.document` (chargé sous Node par les tests). `apiStream` (api.js : lecteur
  relâché en `finally`, aussi quand `onItem` lève une erreur ; lignes découpées par `decouperNdjson` de scene.js, ligne
  illisible = erreur en français). jeu.js : `alerte(message,
  niveau, cle)` pour les erreurs des actions (création, banque, réplique, transcription, import, micro, `tts` en
  échec) ; `statut()` (ancien `status`, qui masquait `window.status`) reste pour les messages d'information. Diagnostic au chargement, toutes les minutes, à
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
  options, préparation), `.carte`, champs et boutons (`button.petit`), message d'état `.status` ; chaque page n'ajoute que sa mise en page. N'utiliser que les
  variables de couleur (jamais de couleur en dur : `--blanc` et `--noir` pour les reflets et ombres, `color-mix`
  avec `--ink` pour les teintes) : elles changent avec le thème. Un test JS le vérifie.
- Accessibilité et téléphone : un texte en cire s'écrit `color-mix(in srgb, var(--wax) 60%, var(--ink))` (la cire
  seule est trop claire en sombre) ; les noms des 2e et 3e PNJ ont un repère (`●`, `◆`) en plus de la couleur.
  `@media (pointer: coarse)` : cibles d'au moins 2,75 rem. `100dvh` après chaque `100vh`. `.controls` (Parler)
  est collé en bas de la partie (`.line` a un `scroll-margin-bottom`). Dégradés aux bords des onglets qui
  défilent. Les champs `number`, `url` et `password` suivent le thème comme `text`. Changement de vue : titre de
  l'onglet du navigateur et focus sur le titre. `messageContexteMicro` (scene.js) : avertissement en HTTP.

## Thèmes graphiques
- Choisi par le scénario (`theme` de `_scenario.json`), posé sur `<html data-theme>` ; vide ou inconnu = défaut.
- Couleurs dans `style.css` : un bloc `[data-theme=<id>]` (clair) + son `@media (prefers-color-scheme: dark)` par
  thème ; `:root, [data-theme=vert-de-gris]` = défaut ; `donjon` toujours sombre. Variables : `--bg --surface --ink
  --muted --line --glass` (principale, texte des boutons = `--surface`) `--verdigris` (appoint) `--wax --wax-ink`
  (sceau « Parler »). Contrastes visés (`PAIRES` dans js/univers.js, contrôlés pour chaque thème) : ≥ 4,5 pour les textes (ink, muted,
  glass sur bg et surface ; surface/glass ; wax-ink/wax ; cire mêlée d'encre) et ≥ 3 pour `--verdigris`
  (anneau de focus) sur bg et surface.
- `js/univers.js` : `THEMES` = prédéfinis avec leurs palettes (`mode`, `clair`, `sombre`), **identiques à style.css**
  (test JS qui les compare, et qui vérifie leurs contrastes) ; `COULEURS` (variables + libellés de l'éditeur),
  `tousLesThemes(perso)` (origine predefini / modifie / perso), `cssThemes(perso)` (sélecteurs `html[data-theme="id"],
  body [data-theme="id"]` : plus précis que style.css, donc gagnants même placés avant ; `body […]` pour les
  aperçus), `contraste`, `melange`, `alertesContraste`, `identifiant(nom, pris)`, `poserThemesPerso(perso, garder)` (`<style
  id="themes-perso">` ; garder = aussi dans localStorage `theme-css`, sinon simple aperçu), `appliquerTheme(id)`
  (prédéfini ou de l'univers, sinon défaut ; localStorage `theme`), `chargerTheme()` (/api/scenario + /api/styles ;
  réponse en erreur = rien n'est appliqué ni mémorisé). `cssThemes` ignore un thème au mode inconnu ou à une couleur
  qui n'est pas `#rrggbb` (le serveur les refuse déjà).
  Le script du `<head>` des deux pages (`js/tete.js`) pose `theme` et `theme-css` gardés avant l'affichage (pas de flash).
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
- Éditeurs jumeaux (thème, style) : textes communs dans `apparence.js` (`libelleSuppression`,
  `confirmationSuppression`, `messageSuppression` par type `"theme"`/`"style"`), `editionDeTheme`, `themeEdite`,
  `palettesDuMode`, `alertesPalettes`, `portraitsPerso`, `mention`. Fiche : `fiche.js` (`CHAMPS_FICHE`,
  `valeursFormulaire`, `ficheDuFormulaire`, `secretMasque`, `titreFiche`, `voixDuGenre`, `initiale`, `corpsScenario`).
- Interface et commentaires en français ; texte de l'interface avec typographie française (« », ’, espaces).

## Page Options (index.html, `#options`, js/options.js)
- Rubriques (`#optionsNav`, construites par `construireNav` d'après les `section[id][data-titre]` de
  `.options-contenu`, intercalaires « Ce navigateur » / « Le serveur » / « État ») ; un clic fait défiler.
- « Cette partie » : réglages du navigateur (`OPTIONS` en localStorage), en lignes `.reglage` (libellé + aide |
  contrôle) avec interrupteurs (`input.interrupteur[role=switch]`, style.css) ; `#multiOpts` grisé et désactivé sans
  `optMulti` (dans `setBusy`).
- « Le serveur » : `ouvrirOptions()` à l'ouverture de la vue (`chargerReglages()` sauf modifications en attente,
  `refreshSys()`, `verifierSante()` ; différé par `queueMicrotask` depuis `afficherVue`), champs générés d'après le catalogue (`controle(r)`), `modifsReglages`
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
- Un seul objet `partie` (js/partie.js, `nouvellePartie()`) : `npcs` (scène, `maxPnj` au plus : `pnj_max` de
  /api/config, 3 par défaut ; message d'information au-delà de 3), `history` (envoyé tel quel à /api/npc/talk),
  `dernier` (répond si personne n'est nommé), `rencontres` (pour l'export), `lieuActuel`, `positions` (nom → lieu
  pendant la partie). Transitions sur place : `nouvelleScene`, `rejoindre`, `retirer`, `changerDeLieu` (→ `{lieu,
  restent}`), `reprendreImport`, `instantane` (sauvegarde, null si rien à garder), `restaurer`, `vider` ; compteur de
  tokens : `compteurVide`, `cumulerUsage`. Hors de `partie` : `ici` (boutons « Aborder »), `tokenUsage`.
- `busy` + `setBusy(b)` : `appliquerControles()` (état de chaque contrôle calculé par `etatControles`, js/controles.js)
  puis, à la fin d'une action, libère les attentes et `sauverPartie()` ; `libre()` attend la fin de l'action en cours.
- Modèle de l'IA (`#modeleBloc.modele-ia`, dernier bloc de la colonne de droite, styles dans style.css) : liste
  `#modeleSel` construite par `afficherModele()` (dans `chargerConfig`) d'après `modele_dialogue` de /api/config,
  via `choixModele` (scene.js : null avec Claude = bloc caché ; LM Studio : "" = « Modèle chargé dans LM Studio » ;
  modèle configuré absent = « (introuvable) ») ; désactivée par `setBusy` pendant une action et si `modifiable` est
  faux (titre explicatif). Au changement : `changementModele` → `api("/api/reglages", {changements}, "PUT",
  {message})` sous `setBusy(true)` (mot de passe du MJ demandé par `envoyer`, gardé en `mdp-mj`), puis
  `chargerConfig()` et `verifierSante()` ; échec ou « Annuler » = liste remise, alerte `modele`.
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

## Aventurier joué et jets de dés (facultatifs)
- `#aventurierBloc` (« Vous jouez », en tête de la colonne de la scène) : caché si l'univers n'a pas d'aventurier ;
  `chargerAventuriers()` (/api/aventuriers + /api/systemes, au chargement, après un import et « Nouvelle table ») ;
  choix gardé dans localStorage `pnj-aventurier` (aventurier supprimé = anonyme), hors de `partie`.
  `tourDe` envoie `aventurier: ficheAventurier(aventurier)` (sans jets ni portrait).
- `#desBloc` (« Jet : » sous la longueur) : visible seulement avec un aventurier et l'option `optDes` (activée par
  défaut) ; `menuJets` (d20 sans bonus, puis groupes), `#jetMode` (`MODES` : normal, avantage, désavantage ; une
  caractéristique supérieure de COF propose l'avantage). `lancerDe()` : `lancer` (hasard injectable), ligne
  `.line.pj.jet` du journal = `affichageJet` + `<small class="detail">` (`detailJet`, perdu à la reprise), et
  `history` reçoit `texteJet` (« (Jet de Persuasion : bon résultat.) », sans chiffre, élision « d’ ») ; le PNJ
  réagit à sa prochaine réplique. `etatControles` : `jetBtn` (action en cours ou scène vide), `aventurierSel`.

## Dialogue côté navigateur
- Répond le PNJ cité (`interpelles` : nom ou métier), sinon `dernier` ; un PNJ questionné par un autre répond juste
  après (`questionnes`, `MAX_TOURS` = 4 répliques d'affilée). Options « Interventions spontanées »
  (`[dialogue] intervention`), « Laissez-les discuter », « Faire entrer » (`consignesEntree` → /api/npc/generate).
- `jouerTours` / `tourDe` : chaque phrase reçue est synthétisée tout de suite (`prepareSpeech`) et dite à la suite ;
  le PNJ suivant écrit pendant que le précédent parle. Ordre (js/tours.js) : `ordreDesReponses` / `ordreDiscussion`
  (avec `avecIntervention`, hasard injectable), `enchainerTours` (file, `prioriser` les questionnés, `MAX_TOURS`),
  `oublierNonDit` (réplique interrompue raccourcie). Texte entre parenthèses (`segments`) : voix du narrateur,
  en italique (`formatLine`).
- Lieux : menu du lieu, PNJ présents (« Aborder »), compagnons (case « Vous accompagne », `suit`), positions
  (`position`, `parLieu` : fiche « Se trouve », banque groupée par lieu), « allons à la forge » → proposition
  (`lieuEvoque`), narration d'arrivée (`arrivee`).
- Export texte (`texteExport`, `nomFichierExport`) et import (`lireExport`, anciens exports compris) : PNJ de la
  banque, sinon recréés (`consignesRecreation`) ; restent en scène ceux qui ont parlé depuis la dernière arrivée
  dans un lieu (`sceneImportee`).

## Micro
- Le micro exige `localhost` ou HTTPS. `listenLocal(ouvert)` : MediaRecorder + seuil adaptatif (`suiviEcoute`,
  js/micro.js, avec `ouvrirAnalyse`, `niveauRms`, `CONTRAINTES_MICRO`, partagés avec `veiller`), arrêt après
  1,2 s de silence, puis /api/stt (via `requete`, annulée par Échap : `transcription`) ; sinon Web Speech API
  (`recognition`, démarrée par `ecouterNavigateur` : `start()` sous `try`). `ecouteLocale` est posé avant
  `getUserMedia` (pas de double écoute) ; la minuterie arrête son propre enregistrement (`arreter`), pas la globale
  `stopListening`. Barre d'espace = « Parler » seulement dans la vue `jeu`.
- Couper la parole au PNJ : option « Parler interrompt le PNJ » (`optInterrompre` : bouton actif pendant la
  `parole`, barre d'espace) ; option « Couper le PNJ dès que vous parlez » (`optCoupure`, désactivée par défaut :
  `veiller` ouvre le micro pendant la `parole`, `detecteurVoix` décide, puis `listenLocal({stream, bruit})`
  continue sur le même micro). L'écho des haut-parleurs peut déclencher : casque conseillé.
