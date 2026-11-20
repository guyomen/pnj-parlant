---
paths:
  - "src/pnj_parlant/portraits.py"
  - "src/pnj_parlant/routes/portraits.py"
  - "tests/test_portraits.py"
---

# Portraits des PNJ (portraits.py, facultatif)

## Moteurs et prompt
- `[portraits] moteur` : `aucun` (défaut, `Aucun`), `local` (`Local` : SD-Turbo via diffusers, option `portraits` hors
  de `tout`, chargé à la première génération, verrou, fp16 sur CUDA / fp32 au processeur) ou `en_ligne` (`EnLigne` :
  Pollinations, une adresse GET, image vérifiée par ses premiers octets, `type_image`). `PortraitIndisponible` :
  message pour l'utilisateur. Ollama ne génère pas d'images (Windows/Linux) : ne pas le proposer.
- `prompt_portrait(moteurs, npc, style)` → « style, description » (style en tête : il pèse plus). Le moteur de
  création traduit la fiche en anglais (`Moteurs.fiche`, schéma `{prompt}` ; consigne : âge en chiffres, vêtements
  d'époque couvrants, contre les biais des générateurs) ; repli sans modèle : « genre, métier, apparence ».
- Style : `STYLES` (portraits.py : peinture, manga, jdr80, photo, crayon → nom, résumé, prompt anglais, sans nom
  d'illustrateur), plus ceux de l'univers (`_styles.json`, voir `apparence.md`) ; choisi par le scénario
  (`style_portrait`, `style_valide(style, perso)`) ; prompt : `prompt_du_style(choix, perso, defaut)` (univers, puis
  prédéfini, puis `[portraits] style`), via `Contexte.style_portrait()`. Liste pour la page : `/api/styles`.
- Pollinations gratuit : une image / 45 s par IP (HTTP 402 `FREE_LIMIT`, Retry-After) → `attente_demandee`, une
  attente puis un nouvel essai si ≤ `attente_max` (60 s), sinon message « réessayez dans N s ».

## Stockage (banque.py)
- `pnj/<id>.png|jpg|webp` à côté de la fiche (`Banque.portrait`, `enregistrer_portrait`, `supprimer_portrait`) ;
  supprimé avec le PNJ, par `vider` et quand une fiche importée remplace l'ancienne. `enregistrer_portrait` renvoie
  faux si la fiche a disparu (la route répond 404, pas de portrait orphelin).
- Export : images incluses ; import (`lire_zip`, `importer`) : un portrait suit sa fiche (même nom, fiche renommée
  comprise), sans fiche ou illisible → `ignores`. `IMPORT_MAX_OCTETS` = 60 Mo.
- Les fiches lues (`GET /api/bank`, `/api/bank/<id>`) ont `portrait` = version de l'image (`Banque.version_portrait` :
  date en ms, 0 sans portrait) ; jamais écrit dans le JSON (`ecrire` le retire, comme `id`).

## Routes
- `GET /api/bank/<id>/portrait` (lu en mémoire : sous Windows un fichier ouvert ne se remplace pas ; `?v=` → cache
  1 jour), `POST` (corps facultatif = fiche à l'écran ; 400 moteur absent, 503 `PortraitIndisponible` ; renvoie
  `{portrait: version, prompt}`), `DELETE`. `/api/config` : `portraits` = nom du moteur ou null.

## Affichage (pages web)
- `adressePortrait(pnj)` (scene.js) = `/api/bank/<id>/portrait?v=<version>` ou "" ; partie : `img.portrait` en tête
  de `.pnj-card` (grand pour le premier, vignette flottante sinon) ; préparation : `figure#portraitBloc` à droite de
  l'identité (`majPortrait`, `peinture` pendant la génération, seulement pour un PNJ enregistré, visible si
  `/api/config` donne un moteur ou si le PNJ a déjà un portrait) et vignettes dans la banque (`vignette`). Import d'un
  dossier : `fichiersImportables` garde aussi png/jpg/webp.
- Style des portraits dans la préparation : `apparence.md`.
