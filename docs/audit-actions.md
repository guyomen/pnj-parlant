# Actions de l'audit — à lancer une par une

Chaque action ci-dessous est un prompt prêt à coller dans une nouvelle session Claude Code ouverte à la
racine du dépôt. Le détail des constats est dans [audit-code.md](audit-code.md).

Règles communes (déjà rappelées dans chaque prompt) : un seul lot par session, relire le code avant de
corriger (les lignes ont pu bouger), tests verts à la fin (`pytest && node --test tests/js/`), ne rien
commiter sans accord.

## Avant de commencer : décisions du MJ

Décisions prises le 15 novembre 2026 (à recopier à la place de `<décision>` dans les prompts) :

- [x] **D1** (lot 2) — Hors du PC, toute écriture (PNJ, scénario, lieux, styles, import, vider l'univers,
  portraits, moteur de voix) exige le mot de passe du MJ, et les `secret` des PNJ et `notes_mj` sont
  masqués aux clients non autorisés. Depuis le PC lui-même, rien ne change.
- [x] **D2** (lot 1) — Nombre maximal de PNJ en scène **configurable**, 3 par défaut (réglage dans
  `config.toml.example`, README et `CATALOGUE` de la page Options ; l'interface lit la valeur du serveur).
  Au-delà de 3, un message d'information prévient que les petits modèles locaux suivent mal une scène
  chargée (réponses plus lentes, PNJ qui se confondent).
- [x] **D3** (lot 9) — Création des fiches par défaut : `local` dans `config.toml.example` ; corriger le
  README et le guide Windows (« la création passe par le moteur `[moteurs] creation` ») ; aligner les
  défauts du code et du `CATALOGUE` sur `local`.
- [x] **D4** (lot 9) — Licence GPL-3.0 (fichier `LICENSE`, champ `license` du pyproject), plus
  `static/fonts/OFL.txt`.
- [x] **D5** (lot 4) — Une partie restaurée relit les fiches sur le serveur (garde le journal, qui suit qui
  et la voix réattribuée ; ignore une fiche supprimée). Importer ou changer d'univers depuis l'accueil avec
  une partie en cours demande confirmation pour vider la partie ; refuser la garde.

Livraison : branche `audit-corrections`, un commit par lot, rien n'est poussé. Lot 8 reporté à une session
à part.

## Ordre et suivi

| Fait | Lot | Sujet | Modèle | Dépend de |
|---|---|---|---|---|
| [x] | 0 | Dépôt et outillage | Sonnet | — |
| [x] | 1 | Erreurs 500 et pannes des moteurs | Sonnet | D2 |
| [x] | 3 | Intégrité des données sur disque | Sonnet | — |
| [x] | 4 | Bugs de l'interface | Opus | D5 |
| [ ] | 2 | Contrôle d'accès et limites de taille | Opus | D1 |
| [ ] | 6 | Latence et caches | Sonnet | lot 3 (6.4) |
| [ ] | 7 | Tests manquants | Sonnet | lots 1 et 2 |
| [ ] | 5 | Accessibilité, thèmes, mobile | Sonnet | — |
| [ ] | 9 | Documentation, lanceur, dépendances | Sonnet | D3, D4 |
| [ ] | 8 | Remaniement (serveur.py, JS en ligne) | Opus | tous les autres |

---

## Prompts

### Lot 0 — Sonnet

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 0 — Dépôt et outillage ») et traite uniquement
le lot 0. Avant de suivre tests/e2e/donnees/config.toml dans git, montre-moi sa ligne cle_api masquée et
demande-moi si c'est une fausse clé. Relis chaque fichier avant de le modifier : si un constat ne se
vérifie plus, dis-le. À la fin : uv sync --extra dev, ruff check, pytest et node --test tests/js/ doivent
passer. Ne commite pas ; résume ce qui a changé et ce qui reste.
```

### Lot 1 — Sonnet

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 1 — Erreurs 500 et pannes des moteurs ») et
traite uniquement le lot 1. Décision D2 (PNJ en scène au plus) : <décision>. Écris un test pour chaque
correction (une classe TestEntreesInvalides paramétrée pour 1.7). Relis le code avant de corriger : si un
constat ne se vérifie plus, dis-le. Mets à jour config.toml.example, README.md et .claude/rules/ si un
défaut ou un message change. À la fin, pytest et node --test tests/js/ doivent passer. Ne commite pas.
```

### Lot 3 — Sonnet

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 3 — Intégrité des données sur disque ») et
traite uniquement le lot 3. Écritures atomiques pour toute la classe Banque, verrou autour des opérations
composées, import qui écrit avant de supprimer, normaliser_fiche partagée avec bank_save et bank_update.
Teste chaque point (y compris une OSError simulée pendant l'import). À la fin, pytest et
node --test tests/js/ doivent passer. Ne commite pas.
```

### Lot 4 — Opus

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 4 — Bugs de l'interface ») et traite uniquement
le lot 4. Décision D5 : <décision>. Toute fonction pure nouvelle (partieValide, découpage NDJSON…) va dans
static/js/ avec un test dans tests/js/. Ne remanie pas au-delà de ce que demande chaque constat (le
remaniement est le lot 8). Vérifie dans le navigateur (preview) les parcours touchés : création pendant
une réplique, barre d'espace hors de la vue jeu, double clic sur Parler, restauration d'une sauvegarde
abîmée. À la fin, pytest, node --test tests/js/ et si possible python tests/e2e/lancer.py. Ne commite pas.
```

### Lot 2 — Opus

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 2 — Contrôle d'accès et limites de taille ») et
traite uniquement le lot 2. Décision D1 : <décision>. Propose-moi d'abord, en quelques lignes, la liste
des routes protégées et ce que verra un joueur sans mot de passe, puis attends mon accord avant de coder.
Ensuite : décorateur @mj, en-tête envoyé par creation.html, MAX_CONTENT_LENGTH, garde sur
PUT /api/voice-engine, frein aux essais de mot de passe. Teste chaque route depuis une adresse distante.
Mets à jour README.md, docs/installation-windows.md et .claude/rules/serveur.md. Ne commite pas.
```

### Lot 6 — Sonnet

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 6 — Latence et caches ») et traite uniquement le
lot 6. Chaque cache doit être invalidé (par appliquer_reglages ou par date de modification) et testé, y
compris l'invalidation. Ne change rien au comportement visible hors latence. À la fin, pytest et
node --test tests/js/ doivent passer. Ne commite pas.
```

### Lot 7 — Sonnet

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 7 — Tests manquants ») et traite uniquement le
lot 7 : écris les tests listés, sans modifier le code applicatif. Si un test révèle un bug, ne le corrige
pas : marque le test xfail avec la raison et signale-le-moi. Mesure la couverture avant et après
(uv run pytest --cov). Ne commite pas.
```

### Lot 5 — Sonnet

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 5 — Accessibilité, thèmes, mobile ») et traite
uniquement le lot 5. Couleurs seulement par variables de thème ; complète PAIRES dans js/univers.js et son
test plutôt que de calculer les contrastes à la main. Vérifie dans le navigateur (preview) en largeur
375 px et en thème clair et sombre. À la fin, pytest et node --test tests/js/ doivent passer. Ne commite pas.
```

### Lot 9 — Sonnet

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 9 — Documentation, lanceur, dépendances ») et
traite uniquement le lot 9. Décision D3 (moteur de création par défaut) : <décision>. Décision D4
(licence) : <décision>. Pour lancer.bat, garde les fins de ligne CRLF et les messages en ASCII ; tu ne
peux pas l'exécuter : explique-moi comment le tester. Pour PyTorch CUDA sous Windows, propose avant de
modifier pyproject.toml et uv.lock. À la fin, pytest doit passer. Ne commite pas.
```

### Lot 8 — Opus

```
Lis docs/audit-code.md (mode d'emploi en tête, puis « Lot 8 — Remaniement ») et traite uniquement le
lot 8, sans changer le comportement. Commence par me proposer le découpage (Blueprints de serveur.py,
modules JS extraits d'index.html et de creation.html) et attends mon accord. Procède ensuite par petites
étapes, tests verts à chaque étape ; chaque fonction JS extraite reçoit un test dans tests/js/. Lance
l'e2e (python tests/e2e/lancer.py) à la fin. Mets à jour l'arborescence dans .claude/CLAUDE.md et
README.md. Ne commite pas.
```
