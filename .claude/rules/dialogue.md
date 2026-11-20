---
paths:
  - "src/pnj_parlant/dialogue.py"
  - "src/pnj_parlant/texte.py"
  - "src/pnj_parlant/fiches.py"
  - "src/pnj_parlant/generer.py"
  - "src/pnj_parlant/routes/dialogue.py"
  - "tests/test_dialogue.py"
  - "tests/test_texte.py"
  - "tests/test_fiches.py"
---

# Création des PNJ et dialogue côté serveur

Le dialogue côté navigateur (qui répond, tours, voix) est dans `partie.md` ; les moteurs dans `moteurs.md`.

## POST /api/npc/generate (fiches.py)
- `{role, nom, genre, consignes, lieu}` : fiche JSON imposée par un schéma (nom, metier, apparence, personnalite,
  humeur, connaissances, secret, salutation, genre, timbre, debit, lieu). Humeur, trait et initiale du nom tirés au
  sort en Python pour varier les PNJ. Le serveur ajoute `voix` (voix du genre du PNJ + réglages, et pitch/rate pour le
  repli navigateur).

## POST /api/npc/talk {npc, presents, history, lieu, longueur, aventurier}
- Prompt système = fiche + univers + lieux (dialogue.py). Le PNJ sait où il est, et s'il accompagne le voyageur
  hors de son lieu habituel. Le `secret` est relu dans la banque (voir `serveur.md`, accès).
- `history` : toute la scène, `[{speaker: nom du PNJ ou null pour le joueur, content}]`, salutations comprises,
  tronquée à `[dialogue] historique` (12) messages.
- Scène à plusieurs (`presents`, `[dialogue] pnj_max` PNJ en tout au plus, 3 par défaut) : chaque PNJ voit ses
  répliques en `assistant` et celles des autres en `user` préfixées par le nom de l'auteur, plus un rappel en fin de
  dernier message.
- Les petits modèles écrivent quand même la suite de la scène : séquences d'arrêt (`dialogue.arrets` :
  « Léonard : », « Voyageur: »… → `stop` d'Ollama, `stop_sequences` de Claude), puis en filet de sécurité
  `texte.sans_autres_locuteurs`, qui coupe le flux dès qu'une étiquette suit une fin de phrase ; la connexion au
  modèle est alors fermée.
- `aventurier` (fiche du navigateur, passée par `normaliser` ; ignorée sans nom) : `consignes(…, aventurier, des)`
  ajoute `portrait_pour_le_pnj` et dit « la voyageuse » si besoin ; `messages` et `arrets`/`repliques` (le nom de
  l'aventurier devient une étiquette d'un autre locuteur) le reçoivent aussi. Jets de dés : une ligne du joueur
  `(Jet de … : appréciation.)` ou `(Jet d'…)` dans `history` ; `a_des_jets(history)` ajoute `REGLE_DES` aux consignes.
  Détails dans `aventuriers.md`.
- `longueur` : `short` (1 phrase), `normal` (`[dialogue] phrases_max`, 3), `long` (×2, 6 au moins) ;
  `texte.limiter_phrases` coupe au-delà (les descriptions entre parenthèses ne comptent pas).
- Réponse NDJSON : une ligne `{"phrase": ...}` par phrase complète, `{"usage": {input_tokens, output_tokens}}`,
  ou `{"error": ...}`.

## texte.py
- Sortie lue à voix haute, donc sans markdown/emoji/astérisques, nombres en lettres, « Nom : » retiré en tête ; une
  phrase de moins de `PHRASE_MIN` (40) caractères attend la suivante.
