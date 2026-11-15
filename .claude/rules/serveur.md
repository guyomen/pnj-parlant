---
paths:
  - "src/pnj_parlant/serveur.py"
  - "src/pnj_parlant/dialogue.py"
  - "src/pnj_parlant/texte.py"
  - "src/pnj_parlant/fiches.py"
  - "src/pnj_parlant/moteurs.py"
  - "src/pnj_parlant/banque.py"
  - "src/pnj_parlant/portraits.py"
  - "src/pnj_parlant/reglages.py"
  - "src/pnj_parlant/config.py"
  - "src/pnj_parlant/generer.py"
  - "src/pnj_parlant/exemples/**"
  - "src/pnj_parlant/static/**"
  - "tests/test_api.py"
  - "tests/test_dialogue.py"
  - "tests/test_texte.py"
  - "tests/test_fiches.py"
  - "tests/test_moteurs.py"
  - "tests/test_banque.py"
  - "tests/test_portraits.py"
  - "tests/test_reglages.py"
  - "tests/test_sante.py"
---

# Serveur Flask, routes et dialogue

`create_app(cfg, moteurs=, tts=, reconnaissance=, portraits=)` (serveur.py) : les tests injectent leurs faux moteurs
(`Contexte.injectes` : jamais remplacés quand les réglages changent).
Serveur sans état : l'historique vit dans le navigateur.

## Accès à l'univers (décision D1) et tailles
- Depuis le PC du serveur (`depuis_le_serveur()` : 127.0.0.1, ::1), rien n'est demandé. Ailleurs, toute écriture de
  l'univers (décorateur `@mj` : PUT scénario, styles, lieux ; POST/PUT/DELETE banque ; POST/DELETE portrait ; import ;
  export (il contient les secrets) ; exemples ; DELETE /api/univers ; PUT /api/voice-engine) demande le mot de passe
  du MJ dans l'en-tête `X-Mot-De-Passe-MJ` (encodé par `encodeURIComponent`, décodé par `mot_de_passe_recu`).
  Refus : 403 avec `mot_de_passe: true` si un mot de passe existe (la page peut le demander), sinon message « depuis
  le PC du serveur ». Lectures et partie restent ouvertes (generate, talk, voice, tts, stt, config).
- `droits(mdp, univers)` → ok / verrou / refus ; `univers` faux pour les réglages (mot de passe exigé même sur le PC
  s'il existe : `reglages.autorise`). `est_mj()` : `GET /api/scenario`, `/api/lieux` et `/api/bank/<id>` retirent
  `notes_mj` et `secret` (`masquer` : champ absent, pas vide). `GET /api/acces` → `{mj, protege, local}`.
- Champ masqué absent d'un PUT = gardé : `secret` (PUT /api/bank/<id>), `notes_mj` (PUT /api/scenario, et par lieu
  existant dans PUT /api/lieux). Une fiche lue sans mot de passe puis renvoyée n'efface rien.
- `/api/npc/talk` relit le `secret` dans la banque par l'`id` du PNJ (la partie reçoit les fiches sans secret) ; un
  PNJ inventé (sans fiche en banque) garde celui du navigateur. `/api/npc/generate` renvoie la fiche entière (PNJ
  pas encore en banque, son secret ne vit que dans le navigateur).
- Frein (`reglages.Frein`, `ctx.frein`, par adresse) : après 5 mauvais mots de passe, verrou de 5 s qui double à
  chaque échec (5 min au plus ; 429, rien n'est comparé pendant le verrou) ; succès = compte effacé ; un mot de passe
  absent ne compte pas ; un mauvais mot de passe attend aussi 1 s.
- Écriture venue d'une autre page web (`Origin` d'un autre hôte, ou `null`) : 403 (`plafond`), car l'import
  multipart et un POST sans corps ne passent pas par la pré-vérification CORS.
- Tailles (`plafond`, 413 en JSON) : `MAX_CONTENT_LENGTH` = `IMPORT_MAX_OCTETS` (60 Mo) + marge multipart pour
  l'import, qui vérifie aussi le nombre (`IMPORT_MAX_FICHIERS`, 500) et le cumul de tous les fichiers, zip
  décompressés compris ; `STT_MAX_OCTETS` (5 Mo) pour /api/stt ; `CORPS_MAX` (2 Mo) pour le reste.
- `[serveur] hote` : `0.0.0.0` par défaut (téléphones) ; `127.0.0.1` pour jouer seul (documenté).

## Moteurs de langage (moteurs.py)
- `[moteurs] creation` et `dialogue` : `"claude"` (`[claude] modele`, `claude-haiku-5-5`), `"local"` (Ollama,
  `[local] modele`) ou `"lmstudio"` (`[lmstudio]` : API compatible OpenAI, `/v1/chat/completions` en SSE ; modèle vide
  = celui chargé, trouvé par `/api/v0/models` ; `<think>…</think>` retiré ; `contexte_max` = contexte du modèle
  chargé ; `etat_lmstudio()` pour la page Options). `MoteurIndisponible` : message destiné au joueur (réseau, Docker
  arrêté, LM Studio arrêté, modèle absent).
- Valeurs par défaut : une seule table `moteurs.DEFAUTS` (égale à `config.toml.example` et au `CATALOGUE` : création et
  dialogue `local`), fusionnée dans `Moteurs.__init__` (`avec_defauts`) : `Moteurs({})` fonctionne, un `config.toml`
  ancien aussi. Claude : délai `[claude] delai_max` (60 s, connexion 5 s), clé absente → `MoteurIndisponible`.
  Ollama / LM Studio : une ligne `{"error"}` ou un flux Ollama sans `done: true` = `MoteurIndisponible` ; délai dépassé
  = message distinct d'« injoignable ».
- Réponses en streaming pour les trois moteurs ; `usage` (tokens) renvoyé en fin de réplique.

## Caches de latence (lot 6)
- Chaque cache a son invalidation ; tests dans `tests/test_cache.py`.
- `Moteurs._en_cache` (`DUREE_CACHE` = 15 s) : liste des modèles d'Ollama (`modeles_locaux`, aussi quand Ollama est
  injoignable : c'est le délai de connexion qu'on évite) et de LM Studio (`/api/v0/models`, une erreur n'est pas
  gardée). Un modèle LM Studio fixé dans `config.toml` ne coûte aucun aller-retour avant la réplique. Vidé en
  reconstruisant `Moteurs` (`appliquer_reglages`) ou par `Moteurs.oublier()`.
- `Contexte.problemes_recents()` (`SANTE_DUREE` = 15 s) sert `/api/sante` ; vidé par `appliquer_reglages` (même en
  cas d'échec) et `changer_tts`. `problemes()` reste sans cache (console au démarrage, tests).
- `Banque` : scénario, lieux et styles gardés (`_en_cache`), invalidés par la signature du fichier (date, taille,
  inode : une modification à la main compte) et par chaque écriture de la banque (`Banque._ecrire` → `_invalider`) ;
  `scenario()` dépend aussi de `_styles.json`. Chaque appelant reçoit une copie.

## Routes
- `GET /api/config` : moteurs, moteur de voix (`tts`, null si aucune voix), `stt_local`, `modeles_locaux`,
  `modele_local`, `intervention`, `pnj_max`, `contexte_max`, `modele_dialogue` (liste « Modèle de l'IA » de la vue
  Partie : null avec Claude, sinon `{moteur, cle: "local.modele"|"lmstudio.modele", valeur, modeles, modifiable}` ;
  modèles d'Ollama, ou `Moteurs.modeles_lmstudio()` = identifiants llm/vlm de LM Studio, liste gardée, vide s'il
  est injoignable ; `modifiable` = mot de passe du MJ défini ou PC du serveur).
- Entrées : `corps(dict|list)` (400 si le JSON n'a pas le bon type), `chaine`, `fiche_recue` : aucune route ne répond 500
  sur un corps mal formé (tests : `TestEntreesInvalides`).
- `GET /api/etat` : GPU (`systeme.etat_gpu`), Ollama si un moteur est `local`, LM Studio s'il est choisi.
- `GET|PUT /api/reglages`, `POST /api/reglages/verifier` : voir « Réglages à chaud » ci-dessous.
- `GET /api/sante` → `{problemes: [{cle, niveau, message}]}` (`Contexte.problemes`, aussi affiché dans la console au
  démarrage) : tomlkit absent (erreur), voix sans catalogue (avertissement : paquet absent ou aucune voix), reconnaissance
  locale choisie mais indisponible (avertissement : faster-whisper ou modèle absent), portraits locaux sans l'option
  (erreur), clé Claude absente (config ni ANTHROPIC_API_KEY ; erreur), Ollama injoignable ou modèle non installé,
  LM Studio injoignable (erreurs). Paquets testés par `paquet_installe` (find_spec, sans importer). Un nouveau cas
  « dépendance absente mais le serveur démarre » va ici, avec un conseil (commande à lancer).
- `POST /api/npc/generate {role, nom, genre, consignes, lieu}` : fiche JSON imposée par un schéma (nom, metier,
  apparence, personnalite, humeur, connaissances, secret, salutation, genre, timbre, debit, lieu). Humeur, trait et
  initiale du nom tirés au sort en Python pour varier les PNJ. Le serveur ajoute `voix` (voix du genre du PNJ +
  réglages, et pitch/rate pour le repli navigateur).
- `GET|PUT /api/scenario` : `monde` (connu de tous les PNJ, envoyé dans les dialogues), `notes_mj` (création
  seulement, jamais envoyées pendant les dialogues), `theme` (thème graphique des pages, `banque.theme_valide` :
  id `[a-z0-9-]{1,40}` sinon `""` = défaut ; la liste des thèmes vit côté navigateur) et `style_portrait` (style de
  dessin, prédéfini ou de l'univers, sinon `""`). PUT remplace tout : envoyer tous les champs.
- `GET|PUT /api/styles` (`pnj/_styles.json`, `Banque.styles` / `enregistrer_styles`, `valider_styles` : 400 si
  invalide) : thèmes `{id: {nom, resume, mode (auto|sombre|clair), clair, sombre}}` (les 9 couleurs `#rrggbb` de
  `COULEURS`, seulement les palettes du mode ; aucune injection CSS possible) et styles de portrait
  `{id: {nom, resume, prompt}}`, 30 de chaque au plus. Un id prédéfini = remplacement pour l'univers. GET renvoie
  `{themes, portraits: portraits.styles(perso)}` (liste complète avec `origine`). Exporté, importé (écrit avant le
  scénario, illisible → `ignores`), vidé par « Nouvelle table ».
- `GET|PUT /api/lieux` (`pnj/_lieux.json`) : `{id, nom, description, notes_mj}`. Description connue de tous les PNJ
  et lue par le narrateur ; notes du MJ pour la création seulement.
- `DELETE /api/univers` → `Banque.vider()` : « Nouvelle table » de l'accueil, supprime tous les PNJ, vide le scénario
  (thème compris) et les lieux ; renvoie `{pnj: nombre supprimé}`.
- `GET /api/scenario/export` : zip à plat (`_scenario.json`, `_lieux.json`, fiches). `POST /api/scenario/import`
  (multipart `fichiers` : un zip ou les .json d'un dossier ; `remplacer` "0" garde les PNJ) → `Banque.importer` :
  tout est vérifié avant d'écrire (`lire_zip` : noms aplatis, taille et nombre limités ; fichier renommé à la main →
  nouvel identifiant). `GET /api/exemples`, `POST /api/exemples/<id> {remplacer}` : univers de
  `src/pnj_parlant/exemples/<id>/` (`_infos.json` = nom et résumé pour l'accueil, jamais importé).
- Les fiches lues (`GET /api/bank`, `/api/bank/<id>`) ont `portrait` = version de l'image (`Banque.version_portrait` :
  date en ms, 0 sans portrait) ; jamais écrit dans le JSON (`ecrire` le retire, comme `id`).
- `GET|POST /api/bank`, `GET|PUT|DELETE /api/bank/<id>` ; `POST /api/voice` (autre voix pour un PNJ, `eviter`) ;
  `GET /api/voices`, `GET|PUT /api/voice-engine` (page de création ; voir la règle voix).
- `POST /api/tts {text, voice, narrateur, eviter}` : 503 en cas d'échec → le navigateur utilise `speechSynthesis`.
- `POST /api/stt` (audio webm/opus + `indice`) : 404 si la reconnaissance locale est indisponible.
- `POST /api/npc/talk {npc, presents, history, lieu, longueur}` : détaillé ci-dessous.

## Réglages à chaud (reglages.py, page Options)
- `CATALOGUE` : groupes (`id`, `titre`, `aide`, `si` = moteur de langage qui rend le groupe utile) de réglages
  `{cle "section.sous.cle", libelle, type (choix, texte, url, entier, nombre, booleen, secret), defaut, aide, choix,
  min/max/pas, suggestions, redemarrage}`. Les `defaut` doivent égaler ceux du code (sinon la page ment).
- `lire`/`poser` (clé pointée), `pour_la_page` (secrets → `valeur: ""` + `defini`), `valider` (ValueError ; secret :
  "" = inchangé, None = effacé), `ecrire` (tomlkit importé à l'usage, commentaires gardés, remplacement atomique),
  `autorise(reglages, mdp, local)` (mot de passe du MJ s'il existe, exigé même en local ; sinon `localhost`
  seulement), `a_redemarrer` (port, HTTPS).
- `Contexte.appliquer_reglages` : nouveau dict, essaie d'abord ce qui peut échouer (moteur de voix), écrit
  `cfg.fichier` (`Config.fichier`, None en tests = en mémoire), puis reconstruit à chaud ce qui a changé (Moteurs,
  voix via `tts_charges`, Reconnaissance, portraits, `parametres()` : historique, intervention, phrases_max, style).
- Routes : `GET /api/reglages` → `{groupes, protege, local, fichier}` (suggestions `local.modele` = modèles
  d'Ollama s'il sert) ; `PUT {changements}` + en-tête `X-Mot-De-Passe-MJ` → 403 (après 1 s de pause si un mauvais
  mot de passe a été envoyé ; avec `mot_de_passe: true` si un mot de passe existe, `garde(…, demander=True)`, pour
  que `envoyer` de js/api.js le demande depuis la vue Partie) / 429 (frein) / 400 / 500 (écriture) / 200
  `{..., redemarrage: [libellés]}` ; `POST /api/reglages/verifier {mot_de_passe}` (même frein, sans
  `mot_de_passe` dans le refus : la page Options a son propre formulaire).

## Portraits (portraits.py, facultatif)
- `[portraits] moteur` : `aucun` (défaut, `Aucun`), `local` (`Local` : SD-Turbo via diffusers, option `portraits` hors
  de `tout`, chargé à la première génération, verrou, fp16 sur CUDA / fp32 au processeur) ou `en_ligne` (`EnLigne` :
  Pollinations, une adresse GET, image vérifiée par ses premiers octets, `type_image`). `PortraitIndisponible` :
  message pour l'utilisateur. Ollama ne génère pas d'images (Windows/Linux) : ne pas le proposer.
- `prompt_portrait(moteurs, npc, style)` → « style, description » (style en tête : il pèse plus). Le moteur de
  création traduit la fiche en anglais (`Moteurs.fiche`, schéma `{prompt}` ; consigne : âge en chiffres, vêtements
  d'époque couvrants, contre les biais des générateurs) ; repli sans modèle : « genre, métier, apparence ».
- Style : `STYLES` (portraits.py : peinture, manga, jdr80, photo, crayon → nom, résumé, prompt anglais, sans nom
  d'illustrateur), plus ceux de l'univers (`_styles.json`) ; choisi par le scénario (`style_portrait`,
  `style_valide(style, perso)`) ; prompt : `prompt_du_style(choix, perso, defaut)` (univers, puis prédéfini, puis
  `[portraits] style`), via `Contexte.style_portrait()`. Liste pour la page : `/api/styles`.
- Pollinations gratuit : une image / 45 s par IP (HTTP 402 `FREE_LIMIT`, Retry-After) → `attente_demandee`, une
  attente puis un nouvel essai si ≤ `attente_max` (60 s), sinon message « réessayez dans N s ».
- Stockage : `pnj/<id>.png|jpg|webp` à côté de la fiche (`Banque.portrait`, `enregistrer_portrait`,
  `supprimer_portrait`) ; supprimé avec le PNJ, par `vider` et quand une fiche importée remplace l'ancienne.
  Export : images incluses ; import (`lire_zip`, `importer`) : un portrait suit sa fiche (même nom, fiche renommée
  comprise), sans fiche ou illisible → `ignores`. `IMPORT_MAX_OCTETS` = 60 Mo.
- Intégrité (`banque.py`) : toutes les écritures passent par `_ecrire` (fichier temporaire du dossier puis `os.replace`,
  réessayé sous Windows ; lecture par `_lire`) ; un `RLock` couvre `importer`, `vider`, `supprimer` et les portraits.
  `importer` écrit d'abord (fiches passées par `normaliser_fiche`, aussi utilisée par `enregistrer_pnj` pour
  POST/PUT /api/bank) et ne supprime qu'ensuite les PNJ absents de l'import. `enregistrer_portrait` renvoie faux si
  la fiche a disparu (la route répond 404, pas de portrait orphelin). `Contexte.verrou_reglages` sérialise
  `appliquer_reglages` et `changer_tts` ; `reglages.ecrire` supprime son fichier temporaire en cas d'échec.
- Routes : `GET /api/bank/<id>/portrait` (lu en mémoire : sous Windows un fichier ouvert ne se remplace pas ;
  `?v=` → cache 1 jour), `POST` (corps facultatif = fiche à l'écran ; 400 moteur absent, 503
  `PortraitIndisponible` ; renvoie `{portrait: version, prompt}`), `DELETE`. `/api/config` : `portraits` = nom du
  moteur ou null.

## /api/npc/talk
- Prompt système = fiche + univers + lieux (dialogue.py). Le PNJ sait où il est, et s'il accompagne le voyageur
  hors de son lieu habituel.
- `history` : toute la scène, `[{speaker: nom du PNJ ou null pour le joueur, content}]`, salutations comprises,
  tronquée à `[dialogue] historique` (12) messages.
- Scène à plusieurs (`presents`, `[dialogue] pnj_max` PNJ en tout au plus, 3 par défaut) : chaque PNJ voit ses répliques en `assistant` et celles des
  autres en `user` préfixées par le nom de l'auteur, plus un rappel en fin de dernier message.
- Les petits modèles écrivent quand même la suite de la scène : séquences d'arrêt (`dialogue.arrets` :
  « Léonard : », « Voyageur: »… → `stop` d'Ollama, `stop_sequences` de Claude), puis en filet de sécurité
  `texte.sans_autres_locuteurs`, qui coupe le flux dès qu'une étiquette suit une fin de phrase ; la connexion au
  modèle est alors fermée.
- `longueur` : `short` (1 phrase), `normal` (`[dialogue] phrases_max`, 3), `long` (×2, 6 au moins) ;
  `texte.limiter_phrases` coupe au-delà (les descriptions entre parenthèses ne comptent pas).
- Réponse NDJSON : une ligne `{"phrase": ...}` par phrase complète, `{"usage": {input_tokens, output_tokens}}`,
  ou `{"error": ...}`.
- texte.py : sortie lue à voix haute, donc sans markdown/emoji/astérisques, nombres en lettres, « Nom : » retiré
  en tête ; une phrase de moins de `PHRASE_MIN` (40) caractères attend la suivante.
