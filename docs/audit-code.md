# Audit du code — PNJ parlants (version 1.0.0, commit 47a7693)

Audit du 14 novembre 2026, en lecture seule : aucun fichier du dépôt n'a été modifié.
Ce document est écrit pour être confié tel quel à un modèle (Opus ou Sonnet) chargé de corriger,
un lot à la fois.

## Mode d'emploi pour le modèle qui corrige

- Lis d'abord `.claude/CLAUDE.md` et les règles de `.claude/rules/` des fichiers que tu touches.
- Traite **un seul lot** par session (voir « Lots de travail »). Ne déborde pas sur les autres.
- Chaque constat donne un fichier et une ligne au commit 47a7693 : relis le code avant de corriger,
  les lignes ont pu bouger. Si un constat ne se vérifie plus, dis-le au lieu de forcer une correction.
- Conventions du projet : tout en français ; un test par changement de logique ; fonction JS testable
  dans `static/js/` ; nouveau réglage dans `config.toml.example`, README.md et le `CATALOGUE` de
  `reglages.py` ; couleurs uniquement par variables de thème ; fichiers en CRLF dans la copie de travail
  (modifier avec Edit) ; README, guide Windows et `.claude/rules/` à jour quand le comportement change.
- Fin de lot : `pytest && node --test tests/js/` doivent passer (206 et 22 tests aujourd'hui).
- Les lots marqués « décision » dépendent d'un choix du MJ (section suivante) : ne tranche pas à sa place.
- Respecte la liste « À ne pas casser » en fin de document.

## État mesuré

| Mesure | Résultat |
|---|---|
| `pytest` | 206 réussis en 3,8 s, sans réseau ni modèle |
| `node --test tests/js/` | 22 réussis |
| e2e (`tests/e2e/lancer.py`) | non lancé pendant l'audit |
| Couverture (pytest-cov, environnement éphémère) | 80 % au total ; `stt.py` 30 %, `systeme.py` 29 %, `voix.py` 46 %, `generer.py` 58 %, `dependances.py` 59 %, `moteurs.py` 75 %, `serveur.py` 82 %, `portraits.py` 83 % |
| `ruff check` (règles déjà présentes sur le poste) | 21 alertes, toutes mineures (8 imports non triés, 2 imports inutiles, 2 `except Exception`) |
| mypy, pytest-cov, CI | absents du projet |
| Taille | 2 400 lignes de Python, 2 700 lignes de JS en ligne dans deux pages HTML, 475 lignes de JS en modules |

Niveau de preuve de chaque constat :
- **[exécuté]** : reproduit pendant l'audit (client de test Flask, faux moteurs, dossier temporaire).
- **[lu]** : établi par lecture du code, non reproduit.
- **[à vérifier]** : plausible, à confirmer avant de corriger (souvent sur un vrai appareil).

Aucune faille critique trouvée : pas de fuite de la clé API, pas de traversée de chemins, pas d'injection
HTML exploitable, pas de mode debug. Le sujet le plus sérieux est l'absence de contrôle sur les routes
d'écriture (lot 2).

## Décisions à prendre par le MJ avant certains lots

| N° | Question | Lots concernés |
|---|---|---|
| D1 | La page « Préparer l'univers » doit-elle rester utilisable sans mot de passe depuis un autre appareil que le PC ? Aujourd'hui tout téléphone du Wi-Fi peut vider ou remplacer l'univers et lire les secrets des PNJ et les notes du MJ. | 2 |
| D2 | Combien de PNJ en scène au plus : 3 (documentation, interface) ou 5 (ce que le serveur accepte) ? | 1 |
| D3 | `config.toml.example` crée les fiches avec le moteur `local`, alors que le README et le guide Windows disent « la création passe par Claude ». Lequel est voulu ? | 9 |
| D4 | Quelle licence pour le projet ? (Piper est sous GPL, les polices sous OFL.) | 9 |
| D5 | Une partie restaurée doit-elle relire les fiches modifiées en préparation ? Un import d'univers doit-il vider la partie en cours ? | 4 |

---

## Lots de travail

Ordre conseillé : 0, 1, 3, 4, puis 2 (après D1), 6, 7, 5, 9, et 8 en dernier (remaniement).

| Lot | Sujet | Modèle conseillé | Taille |
|---|---|---|---|
| 0 | Dépôt et outillage | Sonnet | petite |
| 1 | Erreurs 500 et pannes des moteurs | Sonnet | moyenne |
| 2 | Contrôle d'accès et limites de taille (décision D1) | Opus | moyenne |
| 3 | Intégrité des données sur disque | Sonnet | moyenne |
| 4 | Bugs de l'interface | Opus | moyenne |
| 5 | Accessibilité, thèmes, mobile | Sonnet | moyenne |
| 6 | Latence et caches | Sonnet | petite |
| 7 | Tests manquants | Sonnet | moyenne |
| 8 | Remaniement (serveur.py, JS en ligne) | Opus | grande |
| 9 | Documentation, lanceur, dépendances | Sonnet | petite |

---

## Lot 0 — Dépôt et outillage

**0.1 L'e2e ne peut pas tourner sur un clone neuf.** [exécuté]
`.gitignore:2` contient `config.toml` sans ancrage : `git check-ignore -v tests/e2e/donnees/config.toml`
répond `.gitignore:2`. Ce fichier n'a jamais été suivi, or `tests/e2e/lancer.py:52-57` lance le serveur
dans une copie de `donnees/`, qui sort alors en `ConfigIntrouvable`.
Correction : écrire `/config.toml` dans `.gitignore`, puis suivre `tests/e2e/donnees/config.toml`.
Avant de le suivre, **vérifier que sa `cle_api` est une fausse clé** (sinon la remplacer par `"sk-ant-test"`).

**0.2 `pnj/` (banque du MJ) n'est pas dans `.gitignore`.** [exécuté]
Le dossier n'est ignoré que par un `pnj/.gitignore` local non suivi (`*`), qu'aucun code ne crée.
Sur un clone neuf, fiches, notes du MJ et portraits partent au premier `git add .`.
Correction : ajouter `/pnj/`, ainsi que `.coverage`, `htmlcov/`, `dist/`, `.ruff_cache/`, `.mypy_cache/`,
`.config-*.toml` (fichier temporaire de `reglages.ecrire`, qui contient la clé API) et
`.claude/settings.local.json`.

**0.3 Aucun linter, aucune couverture, aucune CI versionnés.** [lu]
`pyproject.toml:43` : `dev = ["pytest>=8"]`. `pyproject.toml:59-60` configure pylint, qui n'est pas installé.
Correction dans `pyproject.toml` :
```toml
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.6"]

[tool.ruff]
line-length = 120
target-version = "py311"
[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
[tool.ruff.lint.per-file-ignores]
"tests/e2e/faux_ollama.py" = ["E401", "E701", "E702"]

[tool.coverage.run]
source = ["pnj_parlant"]
branch = true
```
Supprimer `[tool.pylint.format]`. Corriger ce que ruff signale (33 lignes de plus de 120 caractères,
5 lambdas assignées en `serveur.py:112,152` et `voix.py:94,149,266`, imports inutiles en
`tests/conftest.py:11` et `tests/test_styles.py:3`).
Ajouter `.github/workflows/tests.yml` : push et pull_request ; matrice `ubuntu-latest` et `windows-latest`,
Python 3.11 et 3.13 ; `astral-sh/setup-uv`, `uv sync --extra dev` (sans `tout`), `uv run ruff check .`,
`uv run pytest --cov`, `actions/setup-node` en 22, `node --test tests/js/`.
Le typage (mypy ou pyright) apporterait peu aujourd'hui : le code n'a presque aucune annotation.

**0.4 `.gitattributes` incomplet.** [lu]
Seuls `*.bat` et un fichier de test sont couverts. Ajouter `* text=auto`, `*.sh text eol=lf`,
`*.woff2 binary`, `*.png binary` (sinon `scripts/ecran.sh` peut sortir en CRLF d'un clone Windows).

**0.5 Pas de `package.json`.** [lu]
Ni `npm test` ni version de Node déclarée. Un `package.json` minimal (`"type": "module"`, `engines`,
script `test`) suffit.

---

## Lot 1 — Erreurs 500 et pannes des moteurs

But : qu'aucune entrée ni panne prévisible ne donne une erreur 500 ou un silence ; toujours un message
lisible par le joueur (`MoteurIndisponible`, 400, ligne `{"error"}` dans le flux).

**1.1 Configuration incomplète : `KeyError`.** [exécuté]
`moteurs.py:26` (`config["claude"]`), `:35`, `:72-76`, `:87-93`, `:178`, `:191`.
`Moteurs({})` lève `KeyError: 'claude'` ; un moteur `lmstudio` ou `local` sans `[…dialogue] max_tokens`
lève `KeyError: 'dialogue'` à chaque réplique. Scénario réel : un `config.toml` antérieur à LM Studio,
puis choix de LM Studio dans la page Options (qui n'écrit que la clé changée).
La page Options affiche des défauts (`reglages.py:42-52`) que `moteurs.py` n'applique pas, ce que la règle
`serveur.md` interdit. `serveur.py:606` ne rattrape pas `KeyError` au démarrage.
Correction : une seule table de défauts (url, modèle, `max_tokens` de création et de dialogue, effort),
fusionnée dans `Moteurs.__init__`, alignée sur `config.toml.example` et le `CATALOGUE`.
Tests : `Moteurs({})` ; chaque moteur avec une configuration minimale et `urlopen` simulé.

**1.2 `reflexion` absent : la page affiche « désactivé », rien n'est envoyé.** [lu]
`moteurs.py:189-190` et `:289-290` : `cfg.get("reflexion")` sans défaut, alors que le catalogue annonce `False`.
Un modèle comme Qwen 3 garde alors son raisonnement (latence). Correction : `cfg.get("reflexion", False)`
ou la table de 1.1.

**1.3 Clé API Claude absente : `TypeError` non rattrapée.** [exécuté]
`moteurs.py:98-104` et `:111-118` ne rattrapent que `APIConnectionError` et `APIStatusError`. Sans clé, le
SDK lève `TypeError("Could not resolve authentication method…")` : 500 sur `/api/npc/talk` et
`/api/npc/generate`. `portraits.py:107` rattrape déjà ce cas.
Correction : `except TypeError` → `MoteurIndisponible("Clé API Claude absente : …")`, et `anthropic.APIError`
plutôt que deux sous-classes.

**1.4 Coupure réseau pendant le flux Claude.** [lu]
`moteurs.py:136-137` ne rattrape que `anthropic.APIError` ; les erreurs `httpx` (lecture interrompue, délai)
traversent. `lignes()` (`serveur.py:548`) ne rattrape que `MoteurIndisponible` : le flux s'arrête sans
ligne `{"error"}`.
Correction : `except (anthropic.APIError, httpx.HTTPError)` ; dans `lignes()`, un filet `except Exception`
qui journalise et émet `{"error": "…"}`.

**1.5 Erreur d'Ollama ou de LM Studio en cours de flux : réplique vide.** [exécuté pour Ollama]
`moteurs.py:159-167` et `:230-238`. Une ligne `{"error": "…"}` (mémoire vidéo pleine, modèle déchargé)
donne une réplique vide sans message ; un flux coupé net passe pour une réplique complète.
Correction : lever `MoteurIndisponible` sur `data.get("error")` dans les deux flux, et pour Ollama si le
flux finit sans `done: true`. Le format exact de l'erreur LM Studio est [à vérifier].

**1.6 Aucun délai raisonnable sur Claude.** [exécuté : valeurs du SDK lues]
`moteurs.py:30` : défauts du SDK, lecture 600 s et 2 reprises. Réseau qui pend : jusqu'à 10 minutes
d'attente. Correction : `timeout=httpx.Timeout(delai, connect=5)`, `max_retries=1` (0 pour le dialogue),
réglage `delai_max` documenté comme pour Ollama.

**1.7 Entrées client non validées : une dizaine de routes répondent 500.** [exécuté]
`serveur.py` fait 9 fois `request.json or {}` puis `.get(…)`. Cas reproduits : corps JSON = liste sur
`/api/npc/talk`, `/api/bank`, `/api/scenario` ; `npc` = chaîne ; `npc.nom` = entier ;
`connaissances: null` ; `/api/npc/generate {"role": null}` ; `/api/tts {"text": 12}`.
Par lecture : `length_scale: 0` ou `"abc"` lève hors du `try` dans `voix.py:165` et `:278` (500 au lieu du
503 qui déclenche le repli sur la voix du navigateur).
Correction : un utilitaire `corps()` (`get_json(silent=True)`, 400 si ce n'est pas un objet) utilisé par
toutes les routes ; conversion en `str` et en liste de chaînes à l'entrée de `talk()` ; `float()` dans le
`try` et `length_scale` borné (0,5 à 2).
Tests : une classe `TestEntreesInvalides` paramétrée par route, attendant 400.

**1.8 Fiche abîmée sur disque.** [exécuté]
`banque.py:200` : `lire` ne rattrape pas `ValueError` (500 sur `GET /api/bank/<id>`).
`banque.py:188-191` : `liste()` fait `npc.get` sur ce qui n'est pas un objet ; une seule fiche `[1]`
bloque toute la liste, alors que le commentaire dit « on l'ignore ».

**1.9 `reglages.valider` accepte NaN, plante sur l'infini.** [exécuté]
`reglages.py:175-182` : `{"local.temperature": NaN}` passe les bornes et est écrit dans `config.toml` ;
`1e999` lève `OverflowError` (500) ; `["a"]` est accepté comme texte (`str()` de la liste).
Correction : `math.isfinite`, `OverflowError` dans l'`except`, `isinstance(valeur, str)` pour texte et url.

**1.10 `[dialogue] historique = 0` désactive la limite.** [exécuté]
`dialogue.py:75` : `[-0:]` renvoie toute la liste. `serveur.py:101` ne borne pas la valeur d'un
`config.toml` édité à la main. Correction : `max(2, int(…))`.

**1.11 Limite de PNJ incohérente (décision D2).** [lu]
`serveur.py:524` : `presents[:4]`, soit 5 PNJ avec celui qui parle ; `index.html:401` (`MAX_PNJ = 3`),
README et `serveur.md` disent 3 en tout.

**1.12 `nettoyer` laisse passer un astérisque isolé et certains emojis.** [exécuté]
`texte.py:13-15` : `nettoyer("Il rit * et part ⭐ ⏳ 👍🏽 ok")` rend `'Il rit * et part ⭐ ⏳ ok'`.
Correction : retirer les `*` restants après les paires ; élargir la classe (U+2300-23FF, U+2B00-2BFF,
U+FE0F, U+200D).

**1.13 Création de fiche locale : lectures non protégées.** [lu]
`moteurs.py:146-148`, `:206-207` : `r.read()` et `["choices"][0]` peuvent lever `OSError`, `KeyError`,
`IndexError`, non convertis. Un délai dépassé (`:201`) affiche « injoignable : lancez docker compose »,
trompeur quand le modèle est seulement lent : message distinct pour `TimeoutError`.

**1.14 Mémoire vidéo insuffisante pour un portrait local.** [à vérifier]
`portraits.py:237-245` ne convertit que `OSError` ; un `RuntimeError` de CUDA donne 500. Plausible sur une
carte de 4 Go avec Ollama chargé.

**1.15 Identifiants : `$` accepte un saut de ligne final.** [exécuté]
`banque.py:22-23` : `NPC_ID.match("abc\n")` est vrai. Sans exploitation connue. Correction : `fullmatch`.

---

## Lot 2 — Contrôle d'accès et limites de taille (décision D1)

**2.1 Routes d'écriture et de suppression ouvertes à tout le Wi-Fi.** [lu, vérifié dans `serveur.py`]
Seules `/api/reglages` et `/api/reglages/verifier` appellent `reglages.autorise` (`serveur.py:294`, `:302`).
Sont ouvertes : `DELETE /api/univers` (`:370`), `POST /api/scenario/import` (`:352`),
`POST /api/exemples/<id>` (`:379`, remplace par défaut), `PUT /api/scenario` (`:329`), `PUT /api/styles`
(`:337`), `PUT /api/lieux` (`:392`), `POST`/`PUT`/`DELETE /api/bank…` (`:408-424`), les portraits
(`:441`, `:459`). En lecture, tout client obtient `notes_mj` (`GET /api/scenario`, `/api/lieux`) et le
`secret` de chaque PNJ (`GET /api/bank/<id>`).
Aggravant : `POST /api/exemples/<id>` (sans corps) et l'import en multipart sont des requêtes « simples »,
sans pré-vérification CORS : une page web ouverte sur un appareil du réseau peut les déclencher.
Correction selon D1 : un décorateur `@mj` (réutilisant `reglages.autorise` et `depuis_le_serveur()`) sur
les routes d'écriture ; masquer `notes_mj` et `secret` aux clients non autorisés ; au minimum, exiger un
en-tête personnalisé sur les `POST` sans JSON. L'interface doit alors envoyer `X-Mot-De-Passe-MJ` depuis
`creation.html`. Tests avec une adresse distante sur chaque route.

**2.2 `PUT /api/voice-engine` contourne le mot de passe du MJ.** [exécuté]
`serveur.py:489-496` : `voix.moteur` est protégé dans `/api/reglages`, mais cette route fait la même
bascule sans contrôle (passage à `edge`, donc répliques envoyées en ligne, ou chargement de Pocket TTS en
pleine partie). Correction : même garde, ou suppression de la route.

**2.3 Aucune limite de taille des requêtes.** [exécuté : `MAX_CONTENT_LENGTH` vaut `None`]
`/api/stt` (`serveur.py:563`) lit l'audio entier en mémoire ; les corps JSON sont illimités ; l'import
limite chaque fichier à 60 Mo, mais ni le nombre de fichiers hors zip ni le total.
Correction : `app.config["MAX_CONTENT_LENGTH"]` global, plafond de quelques Mo pour `/api/stt`, cumul et
compte des fichiers dans `scenario_import`.

**2.4 Mot de passe du MJ : essais en parallèle non freinés.** [lu]
`serveur.py:273-279` : `time.sleep(1)` par requête, mais le serveur est multi-fil. La comparaison
(`hmac.compare_digest`) est correcte. Correction : compteur d'échecs par adresse avec délai croissant.

**2.5 Écoute sur toutes les interfaces par défaut.** [lu]
`config.toml.example:126` (`hote = "0.0.0.0"`), serveur de développement Flask (`serveur.py:617`).
Voulu pour les téléphones ; documenter que `127.0.0.1` suffit pour jouer seul.

---

## Lot 3 — Intégrité des données sur disque

**3.1 Écritures non atomiques.** [lu, vérifié]
`banque.py:116`, `:152`, `:167`, `:208`, `:243` : `write_text` tronque puis écrit. Une lecture
concurrente (chaque réplique lit scénario et lieux) voit un fichier vide ; les lecteurs avalent l'erreur :
le PNJ répond sans univers, sans signal. Un plantage pendant l'écriture perd le fichier.
`reglages.ecrire` fait déjà le remplacement atomique (`reglages.py:210`).
Correction : une fonction `_ecrire(chemin, octets)` (fichier temporaire dans le même dossier puis
`os.replace`) pour toutes les écritures de `Banque`, et un `threading.RLock` autour des opérations
composées (`importer`, `vider`, `enregistrer_portrait`).

**3.2 Import en mode remplacer : suppression avant écriture.** [lu]
`banque.py:316-329` : tous les PNJ sont supprimés avant la première écriture ; une `OSError` ensuite laisse
une banque à moitié vide. Le contenu des fiches importées n'est ni typé ni borné (seul `nom` est testé).
Correction : écrire d'abord, supprimer ensuite ce qui n'est plus dans l'import ; une fonction
`normaliser_fiche` (textes bornés, `connaissances` = liste de chaînes, énumérations), partagée avec
`bank_save` et `bank_update`.

**3.3 `reglages.ecrire` : fichier temporaire laissé en cas d'échec.** [lu]
`reglages.py:207-210` : si `os.replace` échoue (fichier ouvert dans un éditeur sous Windows),
`.config-xxxx.toml`, qui contient la clé API, reste dans le dossier. Correction : `try/finally` avec
`os.unlink`. `serveur.py:105-140` : `appliquer_reglages` et `changer_tts` sans verrou (deux `PUT`
simultanés : le fichier reçoit les deux changements, la mémoire un seul).

**3.4 Portrait orphelin.** [lu]
`serveur.py:445-456` : si le PNJ est supprimé pendant la génération (jusqu'à 60 s), le `.png` est écrit
sans fiche et part dans l'export. Correction : revérifier `banque.existe(npc_id)` avant d'enregistrer.

---

## Lot 4 — Bugs de l'interface

Fichiers : `src/pnj_parlant/static/index.html`, `creation.html`, `js/univers.js`.

**4.1 `generate()` sans garde `busy`.** [lu, vérifié]
`index.html:878` et `:1409` : Entrée dans le champ « Métier » lance une création pendant qu'un PNJ parle ;
`npcs` et `history` sont remplacés en plein tour, l'ancien son continue et « Stop » ne l'atteint plus.
Correction : `if (busy) return;` en tête de `generate()` et de `loadFromBank` ; dans `debutParole`,
appeler `stopNpc()` si une parole existe déjà.

**4.2 La barre d'espace agit sur toutes les vues.** [lu, vérifié]
`index.html:1236-1243` : aucun test de la vue ; sur Accueil et Options, Espace ne fait plus défiler la
page et peut ouvrir le micro alors que la table est cachée.
Correction : ajouter `document.body.dataset.vue === "jeu"` à la condition.

**4.3 Double écoute au micro.** [lu]
`index.html:1125-1169`, `:1228-1234` : `aria-pressed` ne change qu'après `await getUserMedia` ; un double
clic démarre deux `listenLocal`, le second écrase la globale `stopListening`, le premier enregistreur ne
s'arrête jamais (piste micro ouverte, minuterie sans fin).
Correction : un drapeau posé avant le `await` ; la minuterie appelle un arrêt local, pas la globale ;
`try` autour de `recognition.start()` (`:669`, `:1233`).

**4.4 Pas de `try/finally` autour des prises de parole.** [lu]
`index.html:1037-1060` (`jouerTours`), `:756-766` (`saluer`), `:816-842` (`changerLieu`) : une exception
laisse tous les contrôles désactivés jusqu'au rechargement. `send()` et `discuter()` sont appelés sans
`catch` (`:1408`, `:1255`, `:1194`, `:1224`).

**4.5 Sauvegarde de partie sans version ni validation.** [lu]
`index.html:1287-1304` : un JSON valide mais de forme inattendue fait lever la restauration à chaque
chargement, puisque la clé reste en place. La clé `pnj-partie` est unique : après un changement d'univers
fait ailleurs, les téléphones restaurent des PNJ de l'ancien univers. Si le serveur est injoignable au
chargement, la sauvegarde est réécrite sans le lieu.
Correction : `version: 1` ; une fonction pure `partieValide(p)` dans `scene.js`, testée ; `try/catch` qui
supprime la clé en cas d'échec ; ne pas sauver avant la lecture réussie des lieux et de la banque.

**4.6 Fiches périmées après une modification en préparation (décision D5).** [lu]
`index.html:1292-1293`, `:852` : la partie restaurée et « Aborder » utilisent la copie du `localStorage`,
pas la banque. Correction possible : relire `/api/bank/<id>` après la restauration.

**4.7 Import d'univers depuis l'accueil : partie non remise à zéro (décision D5).** [lu]
`index.html:1379-1390`, à comparer à « Nouvelle table » (`:1364-1368`).

**4.8 `chargerTheme` ne vérifie pas `r.ok`.** [lu]
`js/univers.js:106-109` : une erreur 500 passagère applique et mémorise le thème par défaut.

**4.9 Requêtes hors de `requete`.** [lu]
`index.html:1187` (`/api/stt`, sans `signal` : Échap n'annule pas la transcription), `:1593`,
`js/univers.js:154`, `:158`, `creation.html:1032` : une panne affiche « Failed to fetch » en anglais.
Trois fonctions presque identiques (`api` d'`index.html:444`, `api` de `creation.html:414`, `reponse` de
`js/univers.js:144`) à réunir dans un module `js/api.js`.

**4.10 `apiStream` : lecteur jamais annulé.** [lu]
`index.html:461-471` : le découpage des lignes est correct, mais une erreur laisse le lecteur verrouillé et
une ligne invalide affiche « Unexpected token… ». Correction : `finally { reader.cancel() }`, analyse JSON
protégée, découpage extrait en fonction pure testée.

**4.11 Écoute d'une voix en préparation.** [lu]
`creation.html:1026-1041`, `:502` : `fetch` et `play()` sans `catch`, URL d'objet non révoquée en fin de
lecture.

**4.12 Divers.** [lu]
- `index.html:1329` : la liste des exemples est mémorisée vide après un échec.
- `index.html:731` : lecture audio refusée par le navigateur = échec silencieux [à vérifier sur téléphone].
- `index.html:1223-1224`, `:1012` : question dictée perdue sans message quand `send` refuse.
- `index.html:972-979` : import de conversation, état à moitié modifié si `/api/voice` échoue.
- `index.html:606` : `sauverPartie` exécuté à chaque `setBusy(false)` ; quota dépassé muet.
- `index.html:1571`, `:1553-1557`, `:1596` : page Options, modifications en attente incohérentes après un
  champ vidé, un verrouillage ou un 403.
- `index.html:663-668`, `:1136` : en coupure automatique, l'enregistreur démarre après la détection de la
  voix ; les premières syllabes manquent [à vérifier à l'oreille].

**4.13 Échappement manquant (défense en profondeur).** [lu, vérifié pour le premier]
- `creation.html:477-478` : options de voix insérées sans `esc()` (seul endroit où une donnée du serveur
  atteint `innerHTML` sans échappement ; il faudrait un fichier de voix au nom piégé).
- `creation.html:593-606`, `:732` : identifiants de thème et de style dans des gabarits et des sélecteurs
  (protégés aujourd'hui par `banque.py`) : `esc()` et `CSS.escape()`.
- `js/univers.js:43` : `cssThemes` ne valide pas les couleurs (le serveur le fait).

---

## Lot 5 — Accessibilité, thèmes, mobile

**5.1 Contrastes insuffisants non détectés.** [lu, calcul manuel à refaire avec `contraste()`]
`index.html:76` (nom du 3ᵉ PNJ) et `style.css:139` (anneau de focus) utilisent `--verdigris` sur `--bg` :
environ 2,2:1 en thème clair. `PAIRES` (`js/univers.js:68-69`) ne vérifie que 4 couples.
Correction : compléter `PAIRES` avec les couples réellement utilisés (`--wax` sur `--surface`, `--glass`
et `--muted` sur `--bg`, seuil de 3:1 pour le focus) ; nom du 3ᵉ PNJ en `--ink` avec un autre repère.

**5.2 Champs `number`, `url`, `password` hors thème.** [lu, vérifié]
`style.css:122-128` ne cible que `input[type=text]` ; la page Options génère les trois autres types
(`index.html:1488-1495`, `:1535`).

**5.3 Zones `aria-live` relues en boucle.** [lu]
`index.html:377` (`#sys`, réécrit toutes les 3 s) et `:244` (`section.npc`, toutes les fiches).
À l'inverse `#status` (`:256`) n'a ni `role="status"` ni `aria-live`.

**5.4 Couleurs en dur, contraires à la convention.** [lu]
`index.html:181-185`, `style.css:82-83` (`white`, `black` dans `color-mix`), `style.css:160`,
`style.css:6,13,64` et `js/univers.js:44-45` (ombres en `rgb`).

**5.5 Mobile.** [à vérifier sur téléphone]
- Cibles tactiles de 25 à 30 px (`.petit`, `.suppr`, `.fermer`), sous les 44 px conseillés.
- `scrollIntoView({ block: "end" })` (`index.html:500`, `:763`, `:1074`) peut pousser le bouton
  « Parler » hors de l'écran : `.controls { position: sticky; bottom: 0 }`.
- `100vh` à remplacer par `100dvh` (`index.html:34`, `creation.html:114`).
- Onglets défilants sans indice visuel (`style.css:84`).
- `index.html:586` : en HTTP sur un téléphone, le micro échoue seulement au clic ; tester
  `window.isSecureContext` au chargement.

**5.6 Divers.** [lu]
Point « modifié » sans texte (`creation.html:190-193`) ; focus et titre de page inchangés au changement de
vue (`index.html:1309-1323`) ; `role="alert"` réécrit en entier à chaque alerte (`js/bandeau.js:19`) ;
`onsubmit="return false"` en ligne (`index.html:279`).

---

## Lot 6 — Latence et caches

**6.1 LM Studio : un aller-retour HTTP de plus avant chaque réplique.** [lu]
`moteurs.py:252-263`, `:275` : `/api/v0/models` est appelé avant même de regarder si `modele` est
renseigné. Correction : pas de réseau quand le modèle est configuré ; sinon cache de 10 à 30 s ;
`m.get("id")`.

**6.2 `/api/sante` et `/api/config` bloquent sur des appels en série.** [lu]
`serveur.py:147-191`, `:241-249` : délais de 2, 3 et 5 s enchaînés ; `/api/config` est chargé à chaque
ouverture de page. Avec un moteur injoignable, chaque page attend 3 à 10 s.
Correction : cache de 10 à 20 s, invalidé par `appliquer_reglages`.

**6.3 Piper : catalogue relu sur disque à chaque phrase.** [lu]
`voix.py:126-137` : un `glob` et la lecture de chaque `.onnx.json` à chaque synthèse, trois fois par
phrase du narrateur. Un `.onnx.json` illisible donne 500 sur `/api/config`.
Correction : cache invalidé par la date de modification du dossier.

**6.4 `scenario()` relit `_styles.json` à chaque réplique.** [lu]
`banque.py:109`, `serveur.py:533-535` : 3 fichiers lus par réplique. Gain faible ; à faire avec 3.1.

**6.5 Piper : cache des voix sans verrou.** [à vérifier]
`voix.py:162-168` : double chargement possible ; sûreté de `PiperVoice` entre fils non établie.

---

## Lot 7 — Tests manquants

Les tests injectent toujours de faux moteurs : plusieurs branches réelles ne tournent jamais.

**7.1 Application à chaud des réglages.** `serveur.py:105-140` : les gardes `not self.injectes[…]` sont
toujours fausses dans les tests. À écrire (avec `monkeypatch` sur `serveur.Moteurs`, `serveur.voix.charger`,
`serveur.Reconnaissance`) : changement de `claude.modele` ; `voix.moteur` vers un catalogue vide (400,
`config.toml` inchangé) ; `reconnaissance.moteur` ; `reglages.ecrire` qui lève `OSError` (500, mémoire
inchangée) ; tomlkit absent (400).

**7.2 Modules et routes sans test.**
| Cible | Test à écrire |
|---|---|
| `stt.py` (30 %) | `Reconnaissance` avec et sans `model.bin`, `charger` remplacé par un faux modèle |
| `POST /api/stt` (`serveur.py:554-563`) | 400 sans audio, 200 avec texte, indice tronqué à 200 |
| `systeme.py` (29 %), `GET /api/etat` | `subprocess.run` et `urlopen` simulés |
| `GET`/`PUT /api/voice-engine`, `changer_tts` | `voix.charger` remplacé par un faux moteur |
| `POST /api/scenario/import` : 413 | `IMPORT_MAX_OCTETS` abaissé par `monkeypatch` |
| `voix.Piper`, `Pocket`, `Edge` (46 %) | faux `.onnx` dans `tmp_path` ; calcul `rate`/`pitch` d'Edge ; voix inconnue |
| `moteurs._local`, 404 « modèle absent », `modeles_locaux` | même montage `urlopen` que `test_moteurs.py` |
| `portraits.Local` | faux `torch` et `diffusers` dans `sys.modules` |
| `serveur.main`, `generer.main`, `dependances.main`, `python -m pnj_parlant.config` (codes 0, 1, 2 dont dépend `lancer.bat:62-63`) | `SystemExit`, `subprocess.run` |
| `/api/reglages` vu depuis `::1` | `environ_base={"REMOTE_ADDR": "::1"}` |
| `static/js/bandeau.js` | importer ses 5 exports dans `tests/js/` |

**7.3 Fragilités.**
- `tests/test_reglages.py:134-139` dort réellement 1 s (le quart de la durée totale) : déplacer le
  `monkeypatch` de `time.sleep` dans la fixture.
- `tests/e2e/lancer.py` : sorties vers `DEVNULL` (aucun diagnostic), `attendre()` ne vérifie pas `poll()`
  (peut tourner contre un ancien serveur), ports fixes 5917, 5918, 9333.
- `from conftest import …` dans trois fichiers de test : préférer un module `tests/faux.py`.

---

## Lot 8 — Remaniement (à faire en dernier)

**8.1 `create_app` monolithique.** `serveur.py:226-565` : 340 lignes, 40 routes en fermetures.
Découpage en `Blueprint` par domaine (réglages, banque et scénario, portraits, voix, dialogue) recevant
`ctx`, à coupler avec le décorateur `@mj` (2.1) et l'utilitaire `corps()` (1.7).

**8.2 JS en ligne.** `index.html:383-1650` (1 270 lignes, une trentaine de `let` globaux ; `history` et
`status` masquent ceux de `window`) et `creation.html:401-1067` (670 lignes). Fonctions à extraire vers
`static/js/` et à tester, par ordre d'intérêt :
1. découpage NDJSON d'`apiStream` ;
2. sérialisation et validation de la partie ;
3. ordre des tours de `jouerTours` (`index.html:1041-1053`), hasard injecté ;
4. `corriger()` de `tourDe` (`:1104-1108`) ;
5. calcul d'état de `setBusy` (`:580-605`), qui mélange état, DOM, attentes et sauvegarde ;
6. détection de fin de parole de `listenLocal` (`:1153-1166`) et niveau RMS ;
7. transitions de `changerLieu`, `startScene`, `joinScene` ;
8. `api()` commun dans `js/api.js`.

**8.3 Duplications.** Script du `<head>` et en-tête identiques dans les deux pages ; éditeurs de thème et
de style jumeaux (`creation.html:651-715` et `:753-814`) ; calcul RMS et `getUserMedia`
(`index.html:649-663` et `:1128-1159`) ; CSS en ligne répété (`button.petit`, `.status`, `.theme-choix`)
à remonter dans `style.css`.

**8.4 Cohérence.** `print` et `logging` mélangés (`moteurs.py:106,133,209,236`, `voix.py:224`) ;
`banque.py:95-96` recode des noms de fichiers qui ont des constantes ligne 24 ; noms de routes mêlant
anglais et français.

---

## Lot 9 — Documentation, lanceur, dépendances

**9.1 Moteur de création : le modèle de configuration contredit la documentation (décision D3).**
[lu, vérifié] `config.toml.example:6` : `creation = "local"` ; `README.md:76` et
`docs/installation-windows.md:187` : « La création passe par Claude » ; le défaut du code est `claude`.

**9.2 `lancer.bat` : après une installation ratée, relancer ne répare rien.** [lu, vérifié]
`lancer.bat:37-42` puis `:15`, `:44-45` : le `.venv` existe déjà, la relance saute l'installation, alors
que le message dit « relancez ce fichier ». Aussi : `goto activer` même sans `.venv` (le `python` du
système est alors utilisé) ; le repli `python -m venv` peut prendre un Python antérieur à 3.11.
Correction : supprimer `.venv` après un échec ou afficher la commande manuelle ; appeler
`.venv\Scripts\python.exe` explicitement ; vérifier la version.
Détails : `:67` (`'AMD^|Radeon'` entre guillemets doubles, [à vérifier en exécutant la ligne]) ; `:89`
(adresse d'Ollama en dur) ; `:92-93` (attente fixe de 3 s) ; pas de `setlocal`.

**9.3 Dépendances.** [lu, vérifié pour pyopenssl]
`pyproject.toml:15` : `pyopenssl` n'est importé nulle part (Werkzeug utilise `cryptography`) : le remplacer
par `cryptography`. Seul `av` a une borne haute, et le chemin sans uv (`pip install -e ".[tout]"`) ignore
`uv.lock` : borner les versions majeures, ou fournir un `requirements.txt` produit par `uv export`.

**9.4 Portraits locaux « sur carte NVIDIA » sous Windows.** [exécuté sur ce poste]
`torch` installé depuis PyPI est en version processeur (`2.15.0+cpu`, CUDA indisponible) : avec
`appareil = "auto"`, `portraits.py:219-220` retombe toujours sur le processeur. Rien ne dit comment
obtenir une roue CUDA. Même doute pour Whisper : `stt.py:62` ne précharge que des `.so` (Linux), alors que
la page Options propose CUDA 12 [à vérifier].
Correction : index PyTorch CUDA dans `[tool.uv.sources]`, ou documentation corrigée.

**9.5 Documentation et commentaires périmés.** [lu]
- `PNJ_CONFIG` (`config.py:35`) absent du README et du guide Windows ; non documentés dans le README :
  `garder_en_memoire`, `delai_max`, `precision`, `beam_size`, `[portraits.en_ligne] url`.
- `config.py:61` cite `lancerAMD.bat`, qui n'existe pas.
- `__init__.py:4,14` et la docstring de `_ollama` ignorent LM Studio ; la liste des modules omet
  `reglages` et `dependances`.
- `.claude/rules/voix.md` parle d'`ensure_voice` : la fonction s'appelle `voix.verifier` (`voix.py:77`).
- `serveur.py:449`, `portraits.py:134` : le message renvoie à `config.toml` alors que le réglage est dans
  la page Options.
- `systeme.py:1` : « page de jeu » au lieu de « page Options ».

**9.6 Licence (décision D4).** [lu]
Aucun fichier `LICENSE` ; `pyproject.toml` sans `license` ni `authors`. `static/fonts/` redistribue des
polices sous OFL sans le texte de la licence (`OFL.txt` à joindre).

**9.7 Scripts annexes.** [lu]
- `scripts/ecran.sh:24-29` : avec `set -euo pipefail`, un `nvidia-smi` en échec interrompt sans message ;
  `:49` ignore un argument inconnu.
- `docker-compose.yml` : sain (port sur 127.0.0.1, image figée) ; ajouter un `healthcheck`.
- `.claude/settings.json:8` : le hook appelle `python`, qui peut ne pas exister sur la machine Linux
  (`python3`) [à vérifier].

---

## Écarté après vérification (ne pas « corriger »)

- Fuite de la clé API : `pour_la_page` masque les secrets, aucune route ne les renvoie, `config.toml`
  n'est pas servi.
- Traversée de chemins : `NPC_ID` avant tout chemin, noms de fichiers et zip aplatis, voix vérifiées
  contre le catalogue.
- Archive piégée : tailles plafonnées, lecture bornée.
- CSRF sur `/api/reglages` : le JSON exige une pré-vérification CORS.
- Injection HTML : `esc()` ou `formatLine()` partout, sauf les points de 4.13.
- Client qui se déconnecte pendant une réplique : la connexion au modèle est bien fermée.
- Mode debug de Flask : absent.

## À ne pas casser

- Injection des moteurs dans `create_app` et `Contexte` (`injectes`) : c'est ce qui rend les tests rapides
  et sans réseau.
- Chaîne du flux de dialogue : `sans_autres_locuteurs` → `limiter_phrases` → `phrases` → `nettoyer`, avec
  séquences d'arrêt et fermeture de la connexion au modèle dès la coupure.
- Erreur de connexion levée avant de renvoyer le générateur : `talk()` peut répondre 503 proprement.
- `reglages.py` : secrets jamais renvoyés, `hmac.compare_digest`, écriture atomique avec tomlkit
  (commentaires gardés), réglage refusé = rien ne change.
- `valider_styles` : couleurs par expression régulière stricte.
- Verrous de chargement paresseux (`Pocket`, `Reconnaissance`, `portraits.Local`).
- Replis vers le navigateur (503 pour la synthèse, 404 pour la reconnaissance).
- Côté navigateur : `AbortController` partagé par la réplique et les synthèses, répliques interrompues
  raccourcies dans l'historique, file audio enchaînée par promesses avec `revokeObjectURL`, délégation
  d'événements sur les conteneurs réécrits, thème posé dans le `<head>` sans flash, `localStorage` sous
  `try/catch`.
- Tests de cohérence existants : version, défauts du catalogue, exemples, palettes JS égales à `style.css`.
