---
paths:
  - "src/pnj_parlant/serveur.py"
  - "src/pnj_parlant/routes/__init__.py"
  - "src/pnj_parlant/routes/entrees.py"
  - "src/pnj_parlant/routes/acces.py"
  - "src/pnj_parlant/routes/options.py"
  - "tests/test_api.py"
  - "tests/test_acces.py"
  - "tests/test_sante.py"
---

# Serveur Flask : organisation, accès, santé

Le reste du serveur a sa règle : `moteurs.md` (moteurs de langage, caches), `univers.md` (banque, scénario, lieux,
export/import), `dialogue.md` (/api/npc/generate et /api/npc/talk), `aventuriers.md`, `portraits.md`,
`reglages.md` (réglages à chaud), `voix.md` (synthèse, reconnaissance).

`create_app(cfg, moteurs=, tts=, reconnaissance=, portraits=)` (serveur.py) : les tests injectent leurs faux moteurs
(`Contexte.injectes` : jamais remplacés quand les réglages changent).
Serveur sans état : l'historique vit dans le navigateur.

## Organisation (lot 8)
- serveur.py : `Contexte` (reste ici : les tests remplacent `serveur.Moteurs`, `serveur.Reconnaissance`,
  `serveur.paquet_installe`), `create_app` (`plafond` avant chaque requête, erreurs `EntreeInvalide` et 413 en JSON,
  page `/`, `routes.enregistrer(app)`), lancement (`main`, `certificat`, `arreter`).
- `routes/` : un Blueprint par domaine, au niveau du module (`bp`), liste dans `routes/__init__.py` (`BLUEPRINTS`) :
  `options` (config, etat, sante, acces, reglages), `univers` (scenario, styles, lieux, export, import, univers,
  exemples ; `exemples()`, `EXEMPLES`), `pnj` (bank), `portraits`, `aventuriers` (systemes, aventuriers et leur
  portrait), `voix` (voice, voices, voice-engine, tts, stt),
  `dialogue` (npc/generate, npc/talk). Chaque route lit le contexte par `entrees.contexte()`
  (`current_app.extensions["pnj"]`).
- `routes/entrees.py` : `contexte`, `erreur`, `EntreeInvalide`, `corps`, `chaine`, `fiche_recue`, `masquer`,
  `mot_de_passe_recu`, et les tailles `CORPS_MAX`, `STT_MAX_OCTETS`, `MARGE_MULTIPART` (lues comme attributs du module :
  un `monkeypatch` de `entrees` vaut pour `plafond` et pour /api/stt). `routes/acces.py` : `depuis_le_serveur`,
  `protege`, `droits`, `est_mj`, `garde`, `refus`, `trop_d_essais`, décorateur `mj`, `EN_TETE_MDP`.
- Nouvelle route : dans le Blueprint de son domaine ; écriture de l'univers sous `@mj`. `tests/test_api.py` fige la
  liste des routes et celles gardées par `@mj` (à mettre à jour avec elles). URL inchangées (anglais et français
  mêlés : changer une URL changerait l'API des pages).
- Entrées (routes/entrees.py) : `corps(dict|list)` (400 si le JSON n'a pas le bon type), `chaine`, `fiche_recue` :
  aucune route ne répond 500 sur un corps mal formé (tests : `TestEntreesInvalides`).
- Journal : `logging.getLogger(__name__)` dans chaque module (pas de `print`, sauf la console de `main`) ;
  `main` affiche les messages du paquet en `[nom du module] message`. Les routes `dialogue` et `voix` gardent le nom
  `pnj_parlant.serveur`.

## Accès à l'univers (décision D1) et tailles
- Depuis le PC du serveur (`depuis_le_serveur()` de routes/acces.py : 127.0.0.1, ::1), rien n'est demandé. Ailleurs,
  toute écriture de l'univers (décorateur `@mj` : PUT scénario, styles, lieux ; POST/PUT/DELETE banque et
  aventuriers ; POST/DELETE portrait (PNJ et aventurier) ; import ; export (il contient les secrets) ; exemples ;
  DELETE /api/univers ; PUT /api/voice-engine) demande le mot de passe du MJ dans l'en-tête `X-Mot-De-Passe-MJ`
  (encodé par `encodeURIComponent`, décodé par `mot_de_passe_recu`). Refus : 403 avec `mot_de_passe: true` si un mot
  de passe existe (la page peut le demander), sinon message « depuis le PC du serveur ». Lectures et partie restent
  ouvertes (generate, talk, voice, tts, stt, config).
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

## Routes du Blueprint options
- `GET /api/config` : moteurs, moteur de voix (`tts`, null si aucune voix), `stt_local`, `modeles_locaux`,
  `modele_local`, `intervention`, `pnj_max`, `contexte_max`, `portraits` (nom du moteur ou null), `modele_dialogue`
  (liste « Modèle de l'IA » de la vue Partie : null avec Claude, sinon
  `{moteur, cle: "local.modele"|"lmstudio.modele", valeur, modeles, modifiable}` ; modèles d'Ollama, ou
  `Moteurs.modeles_lmstudio()` = identifiants llm/vlm de LM Studio, liste gardée, vide s'il est injoignable ;
  `modifiable` = mot de passe du MJ défini ou PC du serveur).
- `GET /api/etat` : GPU (`systeme.etat_gpu` : NVIDIA, AMD, Intel ; mesures inconnues à null, voir `systeme.md`), Ollama si un moteur est `local`, LM Studio s'il est choisi.
- `GET|PUT /api/reglages`, `POST /api/reglages/verifier` : voir `reglages.md`.
- `GET /api/sante` → `{problemes: [{cle, niveau, message}]}` (`Contexte.problemes`, aussi affiché dans la console au
  démarrage) : tomlkit absent (erreur), voix sans catalogue (avertissement : paquet absent ou aucune voix),
  reconnaissance locale choisie mais indisponible (avertissement : faster-whisper ou modèle absent), portraits locaux
  sans l'option (erreur), clé Claude absente (config ni ANTHROPIC_API_KEY ; erreur), Ollama injoignable ou modèle non
  installé, LM Studio injoignable (erreurs). Paquets testés par `paquet_installe` (find_spec, sans importer). Un
  nouveau cas « dépendance absente mais le serveur démarre » va ici, avec un conseil (commande à lancer).
- Cache : `Contexte.problemes_recents()` (`SANTE_DUREE` = 15 s) sert `/api/sante` ; vidé par `appliquer_reglages`
  (même en cas d'échec) et `changer_tts`. `problemes()` reste sans cache (console au démarrage, tests).
- Concurrence : `Contexte.verrou_reglages` sérialise `appliquer_reglages` et `changer_tts`.
