---
paths:
  - "src/pnj_parlant/serveur.py"
  - "src/pnj_parlant/dialogue.py"
  - "src/pnj_parlant/texte.py"
  - "src/pnj_parlant/fiches.py"
  - "src/pnj_parlant/moteurs.py"
  - "src/pnj_parlant/banque.py"
  - "src/pnj_parlant/generer.py"
  - "src/pnj_parlant/exemples/**"
  - "src/pnj_parlant/static/**"
  - "tests/test_api.py"
  - "tests/test_dialogue.py"
  - "tests/test_texte.py"
  - "tests/test_fiches.py"
  - "tests/test_moteurs.py"
  - "tests/test_banque.py"
---

# Serveur Flask, routes et dialogue

`create_app(cfg, moteurs=, tts=, reconnaissance=)` (serveur.py) : les tests injectent leurs faux moteurs.
Serveur sans état : l'historique vit dans le navigateur.

## Moteurs de langage (moteurs.py)
- `[moteurs] creation` et `dialogue` : `"claude"` (`[claude] modele`, `claude-haiku-5-5`) ou `"local"` (Ollama,
  `[local] modele`). `MoteurIndisponible` : message destiné au joueur (réseau, Docker arrêté, modèle absent).
- Réponses en streaming pour les deux moteurs ; `usage` (tokens) renvoyé en fin de réplique.

## Routes
- `GET /api/config` : moteurs, moteur de voix (`tts`, null si aucune voix), `stt_local`, `modeles_locaux`,
  `modele_local`, `intervention`, `contexte_max`.
- `GET /api/etat` : GPU (`systeme.etat_gpu`) et Ollama si un moteur est local. `POST /api/model {modele}` :
  change le modèle local pour tout le serveur (sans toucher à config.toml).
- `POST /api/npc/generate {role, nom, genre, consignes, lieu}` : fiche JSON imposée par un schéma (nom, metier,
  apparence, personnalite, humeur, connaissances, secret, salutation, genre, timbre, debit, lieu). Humeur, trait et
  initiale du nom tirés au sort en Python pour varier les PNJ. Le serveur ajoute `voix` (voix du genre du PNJ +
  réglages, et pitch/rate pour le repli navigateur).
- `GET|PUT /api/scenario` : `monde` (connu de tous les PNJ, envoyé dans les dialogues), `notes_mj` (création
  seulement, jamais envoyées pendant les dialogues) et `theme` (thème graphique des pages, `banque.theme_valide` :
  id `[a-z0-9-]{1,40}` sinon `""` = défaut ; la liste des thèmes vit côté navigateur).
- `GET|PUT /api/lieux` (`pnj/_lieux.json`) : `{id, nom, description, notes_mj}`. Description connue de tous les PNJ
  et lue par le narrateur ; notes du MJ pour la création seulement.
- `DELETE /api/univers` → `Banque.vider()` : « Nouvelle table » de l'accueil, supprime tous les PNJ, vide le scénario
  (thème compris) et les lieux ; renvoie `{pnj: nombre supprimé}`.
- `GET /api/scenario/export` : zip à plat (`_scenario.json`, `_lieux.json`, fiches). `POST /api/scenario/import`
  (multipart `fichiers` : un zip ou les .json d'un dossier ; `remplacer` "0" garde les PNJ) → `Banque.importer` :
  tout est vérifié avant d'écrire (`lire_zip` : noms aplatis, taille et nombre limités ; fichier renommé à la main →
  nouvel identifiant). `GET /api/exemples`, `POST /api/exemples/<id> {remplacer}` : univers de
  `src/pnj_parlant/exemples/<id>/` (`_infos.json` = nom et résumé pour l'accueil, jamais importé).
- `GET|POST /api/bank`, `GET|PUT|DELETE /api/bank/<id>` ; `POST /api/voice` (autre voix pour un PNJ, `eviter`) ;
  `GET /api/voices`, `GET|PUT /api/voice-engine` (page de création ; voir la règle voix).
- `POST /api/tts {text, voice, narrateur, eviter}` : 503 en cas d'échec → le navigateur utilise `speechSynthesis`.
- `POST /api/stt` (audio webm/opus + `indice`) : 404 si la reconnaissance locale est indisponible.
- `POST /api/npc/talk {npc, presents, history, lieu, longueur}` : détaillé ci-dessous.

## /api/npc/talk
- Prompt système = fiche + univers + lieux (dialogue.py). Le PNJ sait où il est, et s'il accompagne le voyageur
  hors de son lieu habituel.
- `history` : toute la scène, `[{speaker: nom du PNJ ou null pour le joueur, content}]`, salutations comprises,
  tronquée à `[dialogue] historique` (12) messages.
- Scène à plusieurs (`presents`, 3 PNJ en tout au plus) : chaque PNJ voit ses répliques en `assistant` et celles des
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
