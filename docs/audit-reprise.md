# Reprise des corrections de l'audit — état au 15 novembre 2026

Branche `audit-corrections`, créée depuis `master` (47a7693). Rien n'est poussé, `master` n'a pas bougé.
Plan complet : [audit-code.md](audit-code.md) ; décisions et prompts : [audit-actions.md](audit-actions.md).

## Fait

| Étape | Commit | Modèle | Résultat |
|---|---|---|---|
| Documents d'audit | 73eb399 | — | |
| 0 — Dépôt et outillage | e32e141 | Sonnet | ruff, pytest-cov, CI GitHub, `.gitignore`, `.gitattributes`, `package.json`, config e2e suivie |
| 1 — Erreurs 500 et moteurs | 3d65f06 | Sonnet | 1.1 à 1.15 ; `pnj_max` réglable (3 par défaut, D2) |
| 3 — Données sur disque | 00543c7 | Sonnet | Écritures atomiques, verrou, import sûr, `normaliser_fiche` |
| 4 — Bugs de l'interface | 2243dc7 | Opus | 4.1 à 4.13, D5, `js/api.js` commun, e2e réparé |
| 2 — Contrôle d'accès | ca0e6ec | Opus | D1 : `@mj` sur les écritures, secrets masqués, frein aux essais, limites de taille, fenêtre de mot de passe |
| 6 — Latence et caches | 2d0fa94 | Sonnet | LM Studio sans aller-retour, caches de 15 s, catalogue Piper et fichiers de la banque en cache |
| 7 — Tests manquants | a597f91 | Sonnet | Couverture de 85 à 97 %, `tests/faux.py`, e2e plus robuste (journaux, ports libres) |
| 5 — Accessibilité, thèmes, mobile | 1567afe | Sonnet | Contrôle des contrastes élargi, champs thémés, cibles tactiles, `100dvh`, barre « Parler » collée |
| 9 — Documentation, lanceur, dépendances | d5f35a1 | Sonnet | D3 et D4 (GPL-3.0, OFL), `cryptography` au lieu de `pyopenssl`, versions bornées, `lancer.bat` |
| Demande du MJ : modèle dans la vue Partie | 1f523be | Opus | Liste « Modèle de l'IA » dans la colonne de droite (Ollama ou LM Studio), à chaud, avec mot de passe hors du PC |

Vérifié sur la branche après le dernier commit : **pytest 559 réussis, node 49 réussis, ruff sans alerte.**
Au total depuis `master` : 71 fichiers, +6 987 / −717 lignes.

**e2e** : passé sur la machine avec Ollama après les lots 0, 1, 3 et 4. À **relancer** : les lots 7 et
« modèle dans la vue Partie » ont modifié `tests/e2e/` (ports par variables d'environnement, nouvelles
vérifications), et le lot 2 change le chargement de `creation.html` et l'export.
```bash
python tests/e2e/lancer.py
```

## Reste à faire

- **Lot 8 — Remaniement** (Opus) : fait sur la branche `remaniement-lot8`, à relire et commiter. Sans changement
  de comportement : `serveur.py` 888 → 328 lignes, routes dans `routes/` (six Blueprints, `acces.py`, `entrees.py`) ;
  plus de JS en ligne (`js/jeu.js`, `js/options.js`, `js/creation.js`, `js/tete.js`) ; logique extraite et testée
  dans `js/partie.js`, `tours.js`, `controles.js`, `micro.js`, `fiche.js`, `apparence.js`, `apiStream` dans `api.js` ;
  `print` → `logging` ; `.status` et `button.petit` dans `style.css`. pytest 561, node 102, ruff sans alerte, e2e
  46/46 identique à avant, texte et styles calculés des pages identiques à `master`. URL de l'API non renommées.

### Reliquats laissés volontairement

- **1.6** : le dialogue Claude garde 1 reprise (le SDK ne permet `max_retries=0` que par appel).
- **4.12** : premières syllabes perdues en coupure automatique du micro (risque d'écho envoyé à Whisper) : à
  juger à l'oreille avant de décider.
- **4.12** : `sauverPartie` tourne encore à chaque `setBusy(false)` : le lot 8 l'a isolé dans `setBusy`
  (calcul des contrôles à part, `etatControles`) sans changer quand il tourne.
- **4.9** : le `fetch` de `/api/tts` dans `prepareSegment` ne passe pas par `requete` (il a son repli).
- **4.5** : après un changement d'univers fait sur un autre appareil, un téléphone restaure encore les PNJ
  de l'ancien univers ; il faudrait un identifiant d'univers côté serveur.
- **5.6** : le bandeau d'alertes (`role="alert"`) est encore réécrit en entier à chaque nouvelle alerte.
- **6.5** : la synthèse Piper n'est pas sérialisée entre fils ; ajouter un verrou par voix si un son se
  corrompt avec deux PNJ de même voix.
- **9.2** : l'adresse d'Ollama reste en dur dans `lancer.bat`.
- **9.4** : pas de source PyTorch CUDA dans `pyproject.toml` (procédure documentée seulement) ; le
  préchargement CUDA de `stt.py` ne couvre que Linux.
- Fichiers `.tmp-xxxx` d'une écriture interrompue par un plantage : pas de nettoyage au démarrage.
- `authors` absent de `pyproject.toml`.

## À vérifier par vous

**Décisions à confirmer :**
- Licence écrite `GPL-3.0-or-later` (« ou ultérieure ») ; D4 disait GPL-3.0 : passer à `GPL-3.0-only` si
  vous préférez.
- `static/fonts/OFL.txt` : les lignes de copyright (Alegreya Sans, IM Fell English) ont été écrites de
  mémoire : à comparer aux fichiers OFL de Google Fonts.
- Index PyTorch CUDA `cu128` dans la doc : à adapter au pilote du poste.

**Conséquences du lot 2 (D1), à valider à l'usage :**
- Sans mot de passe défini, un téléphone ne peut plus enregistrer un PNJ inventé, importer, charger un
  exemple ni lancer « Nouvelle table » depuis l'accueil.
- Après 5 mauvais mots de passe, l'appareil est bloqué 5 s, puis le double à chaque échec (5 min au plus).
- `PUT /api/voice-engine` reste libre sur le PC, alors que `voix.moteur` dans les Options demande le mot de
  passe même sur le PC s'il est défini (conséquence de « depuis le PC, rien ne change »).
- Le mot de passe est envoyé encodé (`encodeURIComponent`) : les mots de passe accentués marchent
  désormais.
- Plafonds : 5 Mo pour l'audio, 2 Mo pour le JSON, 60 Mo et 500 fichiers pour l'import.

**Choix faits par les agents :**
- D5 : un PNJ restauré garde le nom de la sauvegarde ; une voix changée en banque est reprise sauf conflit
  avec un PNJ déjà en scène ; une fiche supprimée de la banque reste dans la partie.
- `normaliser_fiche` : plafonds nom 80, métier 120, humeur 120, secret 1 500, textes longs 600,
  30 connaissances.
- Modèle dans la vue Partie : avec Ollama, `local.modele` sert aussi à la création des fiches (une
  infobulle le dit) ; hors du PC sans mot de passe, la liste est grisée, pas cachée.
- Caches de 15 s : après `ollama pull`, la liste des modèles et le bandeau mettent jusqu'à 15 s à suivre.
- Thèmes clairs : verdigris éclairci, textes en cire un peu plus sombres, repères ● et ◆ devant les noms
  du 2ᵉ et du 3ᵉ PNJ : à regarder à l'œil.

**Sur le poste Windows (192.168.1.21:5000), après relance du serveur** (le code Python a changé, et
`uv sync --extra tout` est nécessaire : dépendances modifiées) :
- Depuis un téléphone, avec un mot de passe défini : fenêtre de mot de passe en préparation, changement de
  modèle dans la vue Partie, lecture seule après « Annuler ».
- Sur téléphone : bouton « Parler » toujours visible, cibles tactiles, avertissement du micro en HTTP,
  message « Le navigateur a bloqué le son ».
- Double clic sur « Parler » en reconnaissance locale ; Échap pendant « Je transcris… ».
- Import ou changement d'univers pendant une partie : la confirmation apparaît.

**`lancer.bat`** (non exécuté) : 1) sans `.venv` et sans réseau, l'installation échoue, affiche la commande
manuelle et supprime `.venv` ; 2) avec réseau, `.venv` est recréé ; 3) `.venv` complet : démarrage normal ;
4) `.venv` en Python < 3.11 : message et arrêt ; 5) Ollama installé mais arrêté : il démarre (attente de
15 s au plus) ; 6) carte AMD bien détectée.

**Divers :**
- La CI GitHub (`.github/workflows/tests.yml`) n'a jamais tourné : elle partira au premier push.
- Le hook de documentation (`.claude/settings.json`) choisit maintenant `python3` ou `python` : à vérifier
  sur la machine Linux.
- Healthcheck Docker (`ollama list`) ajouté mais non exécuté.
- Format exact des erreurs de flux de LM Studio à confirmer sur un vrai serveur.
- Les nouveaux tests importent leurs faux objets depuis `tests/faux.py` (plus `from conftest`).

## Avant de fusionner dans `master`

1. `uv sync --extra tout --extra dev` (dépendances modifiées au lot 9).
2. `pytest && node --test tests/js/`, puis l'e2e sur la machine avec Ollama.
3. Relire les commits un par un : `git log -p master..audit-corrections`.
4. Les vérifications à la main ci-dessus sur le poste Windows et un téléphone.
5. Fusionner, puis lancer le lot 8 dans une nouvelle session.
