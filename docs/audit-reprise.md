# Reprise des corrections de l'audit — état au 15 novembre 2026

Branche `audit-corrections`, créée depuis `master` (47a7693). Rien n'est poussé, `master` n'a pas bougé.
Plan complet : [audit-code.md](audit-code.md) ; décisions et prompts : [audit-actions.md](audit-actions.md).

## Fait

| Lot | Commit | Modèle | Résultat |
|---|---|---|---|
| — | 73eb399 | — | Documents d'audit |
| 0 — Dépôt et outillage | e32e141 | Sonnet | ruff, pytest-cov, CI GitHub, `.gitignore`, `.gitattributes`, `package.json`, config e2e suivie |
| 1 — Erreurs 500 et moteurs | 3d65f06 | Sonnet | 1.1 à 1.15 ; `pnj_max` réglable (3 par défaut, D2) ; 112 tests dans `tests/test_robustesse.py` |
| 3 — Données sur disque | 00543c7 | Sonnet | Écritures atomiques, verrou, import sûr, `normaliser_fiche` |
| 4 — Bugs de l'interface | 2243dc7 | Opus | 4.1 à 4.13, D5, `js/api.js` commun, e2e réparé |

Vérifié en fin de session sur la branche : **pytest 329 réussis, node 27 réussis, ruff sans alerte.**

## Reste à faire

Dans cet ordre (le lot 2 avait démarré quand la session a été arrêtée, mais n'avait rien modifié) :

| Lot | Sujet | Modèle | Remarque |
|---|---|---|---|
| 2 | Contrôle d'accès et limites de taille | Opus | Décision D1 prise ; voir la consigne ci-dessous |
| 6 | Latence et caches | Sonnet | |
| 7 | Tests manquants | Sonnet | Une partie est déjà couverte par `test_robustesse.py` : ne pas dupliquer |
| 5 | Accessibilité, thèmes, mobile | Sonnet | |
| 9 | Documentation, lanceur, dépendances | Sonnet | Inclut D3 côté doc (README et guide Windows disent encore « la création passe par Claude ») et la licence GPL-3.0 (D4) |
| 8 | Remaniement | Opus | Reporté à une session à part, après relecture du reste |

Point important pour le lot 2 : `/api/npc/talk` doit relire le `secret` du PNJ dans la banque (par son id)
au lieu de dépendre de la fiche envoyée par le navigateur, sinon un PNJ perdrait son secret chez les joueurs
une fois les secrets masqués.

### Reliquats des lots faits (laissés volontairement)

- **1.6** : le dialogue Claude garde 1 reprise (le SDK ne permet `max_retries=0` que par appel, ce qui casse
  les tests qui remplacent `client.messages.create`).
- **4.12** : premières syllabes perdues en coupure automatique du micro, non corrigé (risque d'écho envoyé
  à Whisper) : à vérifier à l'oreille avant de décider.
- **4.12** : `sauverPartie` tourne encore à chaque `setBusy(false)` (coût négligeable, relève du lot 8).
- **4.9** : le `fetch` de `/api/tts` dans `prepareSegment` ne passe pas par `requete` (il a son repli).
- **4.5** : après un changement d'univers fait sur un autre appareil, un téléphone restaure encore les PNJ
  de l'ancien univers ; il faudrait un identifiant d'univers côté serveur.
- Fichiers temporaires `.tmp-xxxx` d'une écriture interrompue par un plantage : pas de nettoyage au démarrage.

### Demande du MJ (hors audit)

- **Choix du modèle local depuis la vue Partie** : rendre le choix du modèle (IA locale) accessible dans la
  colonne de droite de la vue Partie, avec « Nouveau PNJ » et « Banque de PNJ », pour en changer en cours de
  partie sans passer par la page Options. À faire après le lot 2 : ce changement passe par `/api/reglages`
  et doit respecter le mot de passe du MJ quand on n'est pas sur le PC.

## À vérifier par vous

**Sur l'autre machine (e2e) :**
```bash
python tests/e2e/lancer.py
```
Le lot 4 l'a fait passer ici (44/44, trois fois) après avoir corrigé `tests/e2e/faux_ollama.py` (il
n'envoyait pas `done: true`, que le serveur exige depuis le lot 1) et ajouté une attente dans le parcours.

**À la main dans le navigateur :**
- Avec `pnj_max = 4` ou plus : le message d'information apparaît à l'ajout du 4ᵉ PNJ.
- Double clic sur « Parler » en reconnaissance locale (faster-whisper) ; Échap pendant « Je transcris… ».
- Sur téléphone : message « Le navigateur a bloqué le son ».
- Page Options en réseau : mauvais mot de passe puis Enregistrer, les champs se verrouillent en gardant les
  modifications.
- Import ou changement d'univers depuis l'accueil pendant une partie : la confirmation apparaît.

**Choix faits par les agents, à valider :**
- D5 : le nom d'un PNJ restauré reste celui de la sauvegarde (le journal le cite) ; une voix changée dans la
  banque est reprise sauf si elle se confond avec celle d'un PNJ déjà en scène ; une fiche supprimée de la
  banque reste dans la partie telle quelle.
- `normaliser_fiche` : genre, timbre et débit hors énumération sont retirés (la voix est réattribuée) ;
  plafonds nom 80, métier 120, humeur 120, secret 1 500, textes longs 600, 30 connaissances de 600 caractères.
- Sous Windows, `os.replace` est refusé quand un lecteur a le fichier ouvert : `_ecrire` et `_lire`
  réessaient 20 fois toutes les 10 ms.

**Divers :**
- La CI GitHub (`.github/workflows/tests.yml`) est écrite mais n'a jamais tourné.
- `package.json` déclare Node ≥ 20, alors que la CI et la doc visent Node 22.
- Le SDK `anthropic` installé repose sur `httpx2` : `moteurs.py` importe `httpx2 as httpx`, avec repli sur
  `httpx`. À garder en tête si une autre version du SDK est fixée (lot 9).
- Fins de ligne mélangées dans la copie de travail (JS et HTML en LF, quelques `.md` et `.mjs` en CRLF) ;
  le dépôt est en LF grâce à `.gitattributes`.
- Format exact des erreurs de flux de LM Studio à confirmer sur un vrai serveur.

## Comment reprendre

Option 1, une session par lot : ouvrir une session Claude Code sur la branche `audit-corrections` et coller
le prompt du lot depuis [audit-actions.md](audit-actions.md) (les décisions y sont déjà notées).

Option 2, multi-agent : demander « reprends la session multi-agent de l'audit à partir du lot 2 » ; le script
de la session précédente enchaîne les lots 2, 6, 7, 5 et 9 avec le bon modèle et un commit par lot.

Avant de fusionner dans `master` : relire les commits un par un (`git log -p master..audit-corrections`),
lancer l'e2e sur l'autre machine, puis fusionner.
