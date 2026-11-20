---
paths:
  - "src/pnj_parlant/static/index.html"
  - "src/pnj_parlant/static/js/jeu.js"
  - "src/pnj_parlant/static/js/partie.js"
  - "src/pnj_parlant/static/js/tours.js"
  - "src/pnj_parlant/static/js/controles.js"
  - "src/pnj_parlant/static/js/micro.js"
  - "src/pnj_parlant/static/js/scene.js"
  - "tests/js/partie.test.mjs"
  - "tests/js/tours.test.mjs"
  - "tests/js/controles.test.mjs"
  - "tests/js/micro.test.mjs"
---

# Vue Partie (index.html `#jeu`, js/jeu.js)

Côté serveur de la réplique : `dialogue.md`. Aventurier joué et jets de dés : `aventuriers.md`. Vue Options :
`reglages.md`.

## État de la partie
- Un seul objet `partie` (js/partie.js, `nouvellePartie()`) : `npcs` (scène, `maxPnj` au plus : `pnj_max` de
  /api/config, 3 par défaut ; message d'information au-delà de 3), `history` (envoyé tel quel à /api/npc/talk),
  `dernier` (répond si personne n'est nommé), `rencontres` (pour l'export), `lieuActuel`, `positions` (nom → lieu
  pendant la partie). Transitions sur place : `nouvelleScene`, `rejoindre`, `retirer`, `changerDeLieu` (→ `{lieu,
  restent}`), `reprendreImport`, `instantane` (sauvegarde, null si rien à garder), `restaurer`, `vider` ; compteur de
  tokens : `compteurVide`, `cumulerUsage`. Hors de `partie` : `ici` (boutons « Aborder »), `tokenUsage`.
- `busy` + `setBusy(b)` : `appliquerControles()` (état de chaque contrôle calculé par `etatControles`, js/controles.js)
  puis, à la fin d'une action, libère les attentes et `sauverPartie()` ; `libre()` attend la fin de l'action en cours.
- Modèle de l'IA (`#modeleBloc.modele-ia`, dernier bloc de la colonne de droite, styles dans style.css ; `data-mj-seul` :
  caché en mode joueur, js/mj.js) : liste
  `#modeleSel` construite par `afficherModele()` (dans `chargerConfig`) d'après `modele_dialogue` de /api/config,
  via `choixModele` (scene.js : null avec Claude = bloc caché ; LM Studio : "" = « Modèle chargé dans LM Studio » ;
  modèle configuré absent = « (introuvable) ») ; désactivée par `setBusy` pendant une action et si `modifiable` est
  faux (titre explicatif). Au changement : `changementModele` → `api("/api/reglages", {changements}, "PUT",
  {message})` sous `setBusy(true)` (mot de passe du MJ demandé par `envoyer`, gardé en `mdp-mj`), puis
  `chargerConfig()` et `verifierSante()` ; échec ou « Annuler » = liste remise, alerte `modele`.
- `parole` (`debutParole` / `finParole` / `stopNpc`) : prise de parole en cours, `{ctrl: AbortController, stop}`.
  Stop/Échap annule requêtes et son ; une réplique interrompue est raccourcie dans `history` à ce qui a été dit.
- Options mémorisées dans localStorage (`OPTIONS`, `DESACTIVEES` = désactivées par défaut).
- Gardes : `generate`/`loadFromBank` ne font rien si `busy` ; `debutParole` fait taire une parole en cours ;
  `jouerTours`, `saluer`, `changerLieu` en `try/finally` (contrôles toujours réactivés) ; `send`/`discuter` appelés
  avec `.catch` ; question dictée refusée (`envoyerDictee`) laissée dans le champ.

## Conversation gardée
- Dans localStorage (`CLE_PARTIE` : `version` (`VERSION_PARTIE`), rencontres, scène, history, lieu, positions, journal
  affiché, tokens) : `sauverPartie` à chaque `setBusy(false)`, `retirer` et `pagehide` (stockage refusé : une alerte
  `sauvegarde`, une fois) ; `restaurerPartie` au chargement, seulement si les lieux et la banque ont été lus
  (`chargerLieux`/`refreshBank` renvoient faux sinon ; aucune sauvegarde avant, `partieRestauree`).
- Sauvegarde vérifiée par `partieValide` (scene.js) ; illisible ou en échec → clé effacée, `viderPartie()`, alerte.
  Décision D5 : les fiches de la banque sont relues (`/api/bank/<id>`, 404 ou PNJ inventé = copie gardée) et
  fusionnées par `fichesRelues` (scene.js : garde nom, `suit` et voix réattribuée).
- `viderPartie()` : remise à zéro de la partie (« Nouvelle table », nouvel univers chargé depuis l'accueil si le
  joueur accepte `confirmationViderPartie` ; « Annuler » garde la partie).

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
- Le micro exige `localhost` ou HTTPS (`messageContexteMicro` de scene.js : avertissement en HTTP).
  `listenLocal(ouvert)` : MediaRecorder + seuil adaptatif (`suiviEcoute`, js/micro.js, avec `ouvrirAnalyse`,
  `niveauRms`, `CONTRAINTES_MICRO`, partagés avec `veiller`), arrêt après 1,2 s de silence, puis /api/stt (via
  `requete`, annulée par Échap : `transcription`) ; sinon Web Speech API (`recognition`, démarrée par
  `ecouterNavigateur` : `start()` sous `try`). `ecouteLocale` est posé avant `getUserMedia` (pas de double écoute) ;
  la minuterie arrête son propre enregistrement (`arreter`), pas la globale `stopListening`. Barre d'espace =
  « Parler » seulement dans la vue `jeu`.
- Couper la parole au PNJ : option « Parler interrompt le PNJ » (`optInterrompre` : bouton actif pendant la
  `parole`, barre d'espace) ; option « Couper le PNJ dès que vous parlez » (`optCoupure`, désactivée par défaut :
  `veiller` ouvre le micro pendant la `parole`, `detecteurVoix` décide, puis `listenLocal({stream, bruit})`
  continue sur le même micro). L'écho des haut-parleurs peut déclencher : casque conseillé.
