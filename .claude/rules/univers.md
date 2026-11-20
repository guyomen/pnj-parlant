---
paths:
  - "src/pnj_parlant/banque.py"
  - "src/pnj_parlant/routes/univers.py"
  - "src/pnj_parlant/routes/pnj.py"
  - "src/pnj_parlant/exemples/**"
  - "tests/test_banque.py"
  - "tests/test_exemples.py"
---

# Univers : banque, scénario, lieux, export/import (banque.py)

Accès (`@mj`, champs masqués `secret` / `notes_mj`) : `serveur.md`. Thèmes et styles (`/api/styles`) :
`apparence.md`. Aventuriers et portraits stockés dans la banque : `aventuriers.md`, `portraits.md`.

## Routes
- `GET|PUT /api/scenario` : `monde` (connu de tous les PNJ, envoyé dans les dialogues), `notes_mj` (création
  seulement, jamais envoyées pendant les dialogues), `theme` (thème graphique des pages, `banque.theme_valide` :
  id `[a-z0-9-]{1,40}` sinon `""` = défaut ; la liste des thèmes vit côté navigateur) et `style_portrait` (style de
  dessin, prédéfini ou de l'univers, sinon `""`). PUT remplace tout : envoyer tous les champs.
- `GET|PUT /api/lieux` (`pnj/_lieux.json`) : `{id, nom, description, notes_mj}`. Description connue de tous les PNJ
  et lue par le narrateur ; notes du MJ pour la création seulement.
- `GET|POST /api/bank`, `GET|PUT|DELETE /api/bank/<id>` (fiches passées par `normaliser_fiche`).
- `DELETE /api/univers` → `Banque.vider()` : « Nouvelle table » de l'accueil, supprime tous les PNJ, vide le scénario
  (thème compris) et les lieux ; renvoie `{pnj: nombre supprimé}`.
- `GET /api/scenario/export` : zip à plat (`_scenario.json`, `_lieux.json`, fiches). `POST /api/scenario/import`
  (multipart `fichiers` : un zip ou les .json d'un dossier ; `remplacer` "0" garde les PNJ) → `Banque.importer` :
  tout est vérifié avant d'écrire (`lire_zip` : noms aplatis, taille et nombre limités ; fichier renommé à la main →
  nouvel identifiant). `GET /api/exemples`, `POST /api/exemples/<id> {remplacer}` : univers de
  `src/pnj_parlant/exemples/<id>/` (`_infos.json` = nom et résumé pour l'accueil, jamais importé).

## Intégrité
- Toutes les écritures passent par `_ecrire` (fichier temporaire du dossier puis `os.replace`, réessayé sous
  Windows ; lecture par `_lire`) ; un `RLock` couvre `importer`, `vider`, `supprimer` et les portraits.
- `importer` écrit d'abord (fiches passées par `normaliser_fiche`, aussi utilisée par `enregistrer_pnj` pour
  POST/PUT /api/bank) et ne supprime qu'ensuite les PNJ absents de l'import.

## Cache (lot 6)
- `Banque` : scénario, lieux et styles gardés (`_en_cache`), invalidés par la signature du fichier (date, taille,
  inode : une modification à la main compte) et par chaque écriture de la banque (`Banque._ecrire` → `_invalider`) ;
  `scenario()` dépend aussi de `_styles.json`. Chaque appelant reçoit une copie.
