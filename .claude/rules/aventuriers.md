---
paths:
  - "src/pnj_parlant/aventuriers.py"
  - "src/pnj_parlant/routes/aventuriers.py"
  - "src/pnj_parlant/static/js/aventurier.js"
  - "tests/test_aventuriers.py"
  - "tests/js/aventurier.test.mjs"
---

# Aventuriers et jets de dés (facultatifs)

Personnages des joueurs ; sans eux (ou sans `aventurier` dans /api/npc/talk), tout reste comme avant : le joueur est
« le voyageur » (test `test_dialogue_sans_aventurier_inchange`). Leur place dans le prompt : `dialogue.md`.

## Serveur (aventuriers.py, routes/aventuriers.py)
- Fiche `normaliser(av)` : `nom`, `classe` (texte libre), `apparence`, `genre`, `systeme` ("" | `dnd5` | `cof2`),
  `niveau`, `caracteristiques`, `maitrises` (D&D : 1 maîtrise, 2 expertise), `superieures` et `capacites`
  `[{nom, carac, bonus}]` (COF) ; valeurs bornées par `SYSTEMES`, champs inconnus retirés (id, portrait, jets).
  D&D 5e : scores, modificateur `(s - 10) // 2`, `bonus_de_maitrise(niveau)`, 18 compétences ; COF 2e (guide officiel
  du système) : 7 caractéristiques (AGI CON FOR PER CHA INT VOL) = bonus direct au d20, supérieure = dé bonus.
- `jets(av)` → `[{id (car:/comp:/cap:), nom, groupe, carac, bonus, avantage}]` : bonus calculés au serveur (le
  navigateur ne fait que lancer le dé ; `apercuBonus` de js/aventurier.js n'est qu'un aperçu dans la fiche).
- `portrait_pour_le_pnj(av)` : ce que perçoit le PNJ, jamais de chiffre : apparence, classe, allure (`ALLURE`,
  modificateur ≤ -1 ou ≥ 3), talents sociaux (compétences `sociales` de D&D et capacités de COF : doué ≥ 5,
  remarquable ≥ 8, piètre < 0), et son nom avec consigne de ne s'en servir qu'une fois présenté. `mots(av)` :
  « Voyageur / le voyageur / un voyageur », au féminin pour une aventurière.
- Stockage (banque.py) : `pnj/_aventurier-<id>.json` + portrait `_aventurier-<id>.png` (préfixe `AVENTURIER` : le
  « _ » les tient hors de `liste()`, et une ancienne version les ignore à l'import) ; `aventuriers()`,
  `lire_aventurier`, `ecrire_aventurier`, `ajouter_aventurier` (`AVENTURIERS_MAX` = 50), `supprimer_aventurier` ;
  méthodes de portrait avec `prefixe=AVENTURIER`. Exportés, importés (fichier renommé → nouvel id, portrait qui
  suit sa fiche, `remplacer` supprime les absents, résultat `aventuriers`), supprimés par `vider`.
- Routes : `GET /api/systemes` (catalogue pour le formulaire), `GET|POST /api/aventuriers` (liste avec `jets`),
  `GET|PUT|DELETE /api/aventuriers/<id>`, `GET|POST|DELETE /api/aventuriers/<id>/portrait` (prompt d'après genre,
  classe en guise de métier, apparence). Écritures sous `@mj`, lectures ouvertes (rien de secret).

## Préparation (creation.html, onglet Aventuriers `#aventuriers`)
- Liste `#avListe`, fiche `av-*` : identité, portrait `#avPortraitBloc` comme celui d'un PNJ, système de jeu de
  /api/systemes, `#avStats` construit par `renderStats` : caractéristiques, compétences D&D (maîtrise/expertise) ou
  capacités COF, bonus en aperçu `majBonus` → `apercuBonus` ; `lireAv` lit la fiche ; changer de système repart des
  valeurs par défaut. Point de modification de l'onglet : `avDirty` (voir `web.md`).

## Partie (index.html, js/jeu.js)
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
