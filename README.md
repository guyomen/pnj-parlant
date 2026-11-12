# PNJ parlants (PoC)

Claude Haiku ou un modèle local invente un PNJ et joue son rôle, Pocket TTS, Piper ou Edge lui donne une voix, et vous lui parlez au micro depuis le navigateur. faster-whisper reconnaît votre voix sur la machine, sans réseau.

## Installation (PC sous Linux)

Sous Windows, suivez plutôt le guide pas à pas [docs/installation-windows.md](docs/installation-windows.md).

```bash
uv sync --extra tout                 # .venv (Python 3.13) + le paquet pnj_parlant, avec voix et reconnaissance locales
source .venv/bin/activate            # sans uv : python3 -m venv .venv, activer, puis pip install -e ".[tout]"
cp config.toml.example config.toml   # puis renseignez cle_api = "sk-ant-..."

# Voix françaises Piper, si vous choisissez ce moteur de voix (une ou plusieurs, tirées au sort)
mkdir -p voices && cd voices
python -m piper.download_voices fr_FR-siwis-medium fr_FR-tom-medium fr_FR-upmc-medium fr_FR-mls-medium
cd ..

# Modèle Whisper pour la reconnaissance vocale (environ 500 Mo)
python -c "from faster_whisper import download_model; download_model('small', 'modeles-stt/small')"

pnj-parlant                          # ou : python -m pnj_parlant
```

Ouvrez ensuite http://localhost:5000 dans Chrome ou Edge.

## Accès depuis une autre machine (ex. le téléphone d'un joueur)

Le navigateur n'autorise le micro qu'en HTTPS ou sur `localhost`. Mettez donc `https = true` dans la section `[serveur]` de [`config.toml`](config.toml), relancez `pnj-parlant`, puis ouvrez `https://<ip-du-pc>:5000` et acceptez l'avertissement de certificat.

## Comment ça marche

- `POST /api/npc/generate` : Haiku renvoie une fiche JSON (nom, métier, humeur, rumeurs, secret, salutation, timbre, débit). Humeur, trait et initiale du nom sont tirés au sort côté Python pour éviter les PNJ qui se ressemblent.
- `POST /api/npc/talk` : la fiche devient le prompt système, l'historique est renvoyé par le navigateur (serveur sans état). La réplique arrive en streaming, avec Claude comme avec le modèle local : le serveur la découpe en phrases et envoie chacune dès qu'elle est complète (une ligne JSON par phrase). Le navigateur affiche et fait lire la première phrase pendant que le modèle écrit la suite, et prépare la voix de la phrase suivante pendant la lecture.
- Scène à plusieurs PNJ : chaque PNJ reçoit toute la conversation, ses propres répliques d'un côté, celles des autres préfixées par leur nom. Des séquences d'arrêt empêchent un petit modèle d'écrire aussi les répliques des autres.
- `POST /api/tts` : le moteur de voix choisi (voir [Synthèse vocale](#synthèse-vocale)) lit la phrase avec la voix attribuée au PNJ, tirée parmi celles de son genre. Le texte entre parenthèses (« (Il se gratte la tête.) ») est lu par une voix neutre de narrateur et affiché en italique. En cas d'échec, le navigateur lit le texte lui-même (`speechSynthesis`), avec une hauteur adaptée au timbre.
- `POST /api/stt` : faster-whisper transcrit l'enregistrement du micro (webm/opus envoyé par le navigateur), en français, avec le nom et le métier du PNJ comme indice de vocabulaire. Le navigateur coupe l'enregistrement après une seconde de silence.

## Jouer

L'**accueil** (http://localhost:5000) propose trois entrées :

- **Charger un univers** : un exemple fourni en un clic (voir [Pré-Novice](#univers-dexemple--pré-novice)), ou un univers exporté (fichier zip, ou son dossier décompressé). Le chargement remplace l'univers, les lieux et les PNJ de la banque, sauf si « Garder les PNJ actuels » est cochée.
- **Discuter avec un PNJ** : un PNJ de l'univers au hasard, ou un PNJ inventé par le modèle d'après un métier.
- **Créer son univers** : la page de préparation (voir plus bas).

La barre du haut mène à l'accueil, à la **partie**, aux **options** et à la préparation. La conversation en cours est gardée dans le navigateur : on la retrouve en revenant de l'accueil, des options ou de la préparation, et même après avoir rechargé la page ou relancé le serveur.

Dans la partie, **Créer un PNJ** en invente un d'après son métier ; ou choisissez un PNJ de la banque et cliquez sur **Jouer**. Parlez-lui avec **Parler** (ou la barre d'espace), ou tapez votre question.

- **Stop** (ou Échap) fait taire le PNJ ; il ne se souvient que de ce qu'il a eu le temps de dire.
- **Longueur des réponses** : **Courte** (une phrase), **Normale** (`phrases_max` de `config.toml`) ou **Détaillée**.
- **Exporter la conversation** l'enregistre dans un fichier texte lisible ; **Importer une conversation** la reprend là où elle s'était arrêtée (même lieu, mêmes PNJ). Un PNJ absent de la banque est recréé par le modèle d'après ce qu'il a dit.
- Sous la discussion : l'utilisation du contexte (barre de progression si sa limite est connue) et le cumul des tokens de la scène. Ollama utilise `[local] contexte` ; pour Claude, définissez `contexte` dans `[claude]` selon la fenêtre du modèle.

La page **Options** (mémorisées par le navigateur) règle aussi le modèle local, qu'on peut changer en cours de partie, et affiche l'état d'Ollama et de la carte graphique :

| Option | Effet |
|---|---|
| « Parler » interrompt le PNJ | Pendant qu'il parle, **Parler** lui coupe la parole et vous écoute aussitôt. Décochée : il faut attendre la fin ou cliquer sur Stop. |
| Couper le PNJ dès que vous parlez | Désactivée par défaut. Le micro reste ouvert pendant que le PNJ parle : dès que vous parlez, il se tait et votre phrase devient la question. Prenez un casque : avec des haut-parleurs, la voix du PNJ peut le couper elle-même (surtout la voix de secours du navigateur). |
| Plusieurs PNJ dans la scène | Jusqu'à 3 PNJ (**Ajouter à la scène**). Répond le PNJ que vous nommez (nom ou métier), sinon le dernier à avoir parlé ; un PNJ à qui un autre pose une question lui répond. **Laissez-les discuter** fait répondre un autre PNJ. |
| Interventions spontanées | À plusieurs : un autre PNJ réagit parfois de lui-même (probabilité `intervention` dans `[dialogue]`). |
| Faire entrer un PNJ | À plusieurs : le modèle invente un nouveau venu d'après la conversation (« la fille de l'aubergiste »), ou au hasard si le champ est vide. |

## Préparer le scénario et les PNJ (pour jouer sans réseau)

Ouvrez **http://localhost:5000/creation.html** (« Préparer l'univers » dans la barre du haut, ou « Créer son univers » sur l'accueil). La création passe par Claude : faites-la avant de partir, avec le réseau.

1. **Scénario**, en deux parties :
   - **Univers** : lieux, factions, personnages connus, événements. Connu de tous les PNJ, il est aussi transmis pendant les dialogues.
   - **Notes du MJ** : l'intrigue et ses secrets. Elles servent seulement à créer des PNJ cohérents et ne sont jamais transmises pendant les dialogues, pour qu'un PNJ ne révèle pas ce qu'il n'est pas censé savoir.
2. **Demander un PNJ** : métier, nom, genre (tous facultatifs) et son rôle dans le scénario. Claude propose une fiche qui ne cite que des noms présents dans le scénario ou vos consignes.
3. **Relire et ajuster** la fiche, écouter sa voix (bouton « Autre voix » si elle ne convient pas), puis l'**enregistrer dans la banque**. Les PNJ de la banque peuvent être modifiés ou supprimés.

Sur la page de jeu, choisissez un PNJ dans la banque et cliquez sur **Jouer** (voir [Jouer](#jouer)).

### Lieux

Dans la page de préparation, le panneau **Lieux** décrit les endroits du scénario (auberge, forge, porte nord…) :
un nom, une **description** (lue par le narrateur quand on y arrive, et connue de tous les PNJ) et des **notes
du MJ** (secrets du lieu : elles servent seulement à créer des PNJ cohérents, jamais pendant les dialogues).
Chaque PNJ peut avoir un **lieu habituel**, choisi dans sa fiche ou dans la demande de création.

En jeu, le menu **Lieu** indique où se passe la scène. Les PNJ qui s'y trouvent apparaissent dessous :
**Aborder** les fait entrer dans la scène. Pour changer de lieu, choisissez-le dans le menu, ou dites-le
(« allons à la forge ») : la page propose d'y aller. Les PNJ de la scène restent sur place, sauf ceux dont la
case « Vous accompagne » est cochée ; on les retrouve là où on les a laissés. Chaque PNJ sait où il se trouve
et connaît les lieux du scénario.

Tout est stocké dans `pnj/` : `_scenario.json` pour le scénario, `_lieux.json` pour les lieux, puis un fichier JSON par PNJ, lisible et modifiable à la main.

### Partager un univers

Dans la page de préparation, **Exporter l'univers** télécharge un zip (scénario, lieux et PNJ de la banque). **Importer un zip** ou **Importer un dossier** (le même, décompressé) le recharge, ici ou sur un autre PC ; l'accueil fait de même avec « Charger un univers ». L'import remplace l'univers, les lieux et les PNJ en place (exportez-les d'abord pour les garder), sauf si « Garder les PNJ actuels » est cochée : les PNJ importés s'ajoutent alors à la banque.

### Univers d'exemple : Pré-Novice

Pour essayer sans rien préparer, l'accueil propose **Exemple : Pré-Novice**, un univers comique prêt à jouer : une ville d'aventuriers débutants fauchés, Lyse, la déesse du Feu que personne ne croit (ses miracles servent surtout à nettoyer les fours, d'où leur nom de pyro-Lyse), et un général du Roi Démon qui voudrait surtout dormir. Il comprend 3 lieux (la guilde, le temple, le fort de la colline) et 5 PNJ, sans voix enregistrée : chaque PNJ reçoit une voix de son genre, toujours la même, selon le moteur de voix de la machine. Les notes du MJ, dans la page de préparation, donnent l'intrigue et ses solutions.

Les exemples sont dans [`src/pnj_parlant/exemples/`](src/pnj_parlant/exemples/), un dossier par univers au format de `pnj/`, plus un `_infos.json` (nom et résumé affichés sur l'accueil).

Pour remplir la banque en lot (le scénario est pris en compte) :

```bash
pnj-banque 20                       # 20 PNJ aux métiers tirés au sort
pnj-banque 5 --metier "aubergiste"  # 5 aubergistes
```

Si la voix d'un PNJ n'existe pas sur la machine qui l'ouvre, ou vient d'un autre moteur de voix, une autre voix du même genre est choisie, toujours la même pour ce PNJ.

## Modèle local pour les dialogues (sans réseau)

Les répliques des PNJ peuvent venir d'un modèle qui tourne sur le PC, servi par [Ollama](https://ollama.com) dans un conteneur Docker. Le choix se fait dans la section `[moteurs]` de `config.toml`, séparément pour la création (`creation`) et pour les dialogues (`dialogue`).

**Installation, une fois, avec le réseau** (PC avec carte NVIDIA) :

1. Installez Docker, le plugin `docker compose` et le [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), qui donne au conteneur l'accès à la carte graphique. Sous Ubuntu :

   ```bash
   sudo ubuntu-drivers install && sudo reboot   # pilote NVIDIA (Docker ne sait pas utiliser le pilote libre « nouveau »)
   nvidia-smi                                   # après le redémarrage : doit afficher la carte
   sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
   ```
2. Démarrez Ollama et téléchargez le modèle (environ 5 Go) :

   ```bash
   docker compose up -d
   docker compose exec ollama ollama pull qwen3:8b
   ```
3. Vérifiez que le modèle utilise bien la carte graphique : `docker compose exec ollama ollama ps` doit afficher `100% GPU` après une première réplique.

Le conteneur redémarre ensuite avec le PC. `docker compose down` l'arrête ; `docker compose down -v` supprime aussi les modèles téléchargés.

**Petite carte graphique (4 Go, ex. NVIDIA T400)** : `qwen3:8b` ne tient pas. Réglages testés pour que le modèle tourne à 100 % sur le GPU (environ 21 tokens/s, une réplique en 3 à 5 s) :

- Modèle `qwen3:4b-instruct` (2,5 Go) : `docker compose exec ollama ollama pull qwen3:4b-instruct`, puis `modele = "qwen3:4b-instruct"` dans `[local]`. Évitez le tag `qwen3:4b` tout court : il réfléchit toujours, même avec `reflexion = false`, et lit son raisonnement à voix haute.
- `contexte = 2048` dans `[local]`. Ça suffit : une création de PNJ demande au plus environ 1900 tokens, un dialogue avec 12 messages d'historique environ 1200. Un long univers de scénario s'ajoute à chaque requête : passez alors à 3072, au prix d'environ 10 % du modèle sur le processeur.
- La *flash attention* et la mémoire de conversation compressée (`OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`) sont déjà réglées dans [docker-compose.yml](docker-compose.yml).
- Le bureau Linux occupe environ 700 Mo de mémoire vidéo. Si l'écran du PC ne sert pas (accès en SSH), coupez-le avec [scripts/ecran.sh](scripts/ecran.sh) :

  ```bash
  ./scripts/ecran.sh couper                 # jusqu'au prochain redémarrage
  ./scripts/ecran.sh couper --permanent     # le PC démarrera aussi sans écran graphique
  ./scripts/ecran.sh rallumer [--permanent] # inverse
  ./scripts/ecran.sh etat                   # mémoire vidéo utilisée, et répartition CPU/GPU du modèle
  ```

  Sans cela, une partie du modèle reste sur le processeur et les répliques sont plus lentes (14 tokens/s mesurés avec l'écran allumé, 21 sans).

**Changer de modèle** : téléchargez-le (`ollama pull`), puis changez `modele` dans la section `[local]`. Avec 12 Go de mémoire vidéo, `qwen3:8b`, `gemma3:12b` et `mistral-nemo` tiennent sans problème. Comparez-les sur les mêmes PNJ : la qualité du français varie d'un modèle à l'autre.

**Avant de partir sans réseau**, vérifiez que tout est sur le PC : l'image Docker et le modèle (`docker compose exec ollama ollama list`), les voix (lancez l'application une fois avec le réseau pour Pocket TTS ; `voices/` pour Piper), et la banque de PNJ dans `pnj/`.

## Synthèse vocale

Trois moteurs, au choix dans la section `[voix]` de `config.toml` (`moteur = ...`) :

| Moteur | Où | Qualité en français | Matériel | Voix |
|---|---|---|---|---|
| `pocket` ([Pocket TTS](https://github.com/kyutai-labs/pocket-tts), Kyutai) | local, sans réseau | naturelle | processeur d'un PC ; une phrase prend 1 à 3 s | 22 (12 féminines, 10 masculines) |
| `piper` ([Piper](https://github.com/OHF-Voice/piper1-gpl)) | local, sans réseau | correcte, un peu mécanique | très léger, le plus rapide sur un petit processeur | celles téléchargées dans `voices/` |
| `edge` ([edge-tts](https://github.com/rany2/edge-tts)) | serveurs de Microsoft | la plus naturelle | aucun, mais **réseau obligatoire** | 8 (France, Belgique, Suisse) |

- **Pocket TTS** télécharge son modèle (environ 250 Mo) et ses voix au premier lancement : lancez l'application une fois avec le réseau, et attendez que la console n'affiche plus rien. Une voix qui n'a pas pu être téléchargée est signalée dans la console et n'est pas attribuée. Le débit du PNJ (`lent`, `rapide`) n'est pas appliqué, ni le timbre.
- **Edge** applique le débit et le timbre du PNJ. Sans réseau, c'est la voix du navigateur qui prend le relais. Le service est gratuit mais non officiel : Microsoft peut le changer ou le couper.
- Les genres des voix Pocket et Edge sont fixés dans [voix.py](src/pnj_parlant/voix.py) ; on peut les remplacer dans `config.toml` (voir les commentaires de `config.toml.example`).
- La page de préparation permet d'essayer un autre moteur sans toucher à `config.toml` : le changement vaut pour tout le serveur, jusqu'à son redémarrage.

Les répliques sont lues phrase par phrase, une phrase étant regroupée avec la suivante tant qu'elle fait moins de 40 caractères (« Ah ! »), pour éviter des blancs entre deux sons trop courts.

## Reconnaissance vocale locale

Avec `moteur = "local"` dans la section `[reconnaissance]` de `config.toml`, votre voix est transcrite sur la machine par [faster-whisper](https://github.com/SYSTRAN/faster-whisper) : rien ne part sur internet. Avec `moteur = "navigateur"`, ou si le modèle n'est pas téléchargé, la page utilise la Web Speech API de Chrome ou Edge, qui envoie l'audio à Google ou Microsoft et ne marche donc pas sans réseau.

Le modèle se télécharge une fois, avec le réseau, dans `modeles-stt/` :

```bash
python -c "from faster_whisper import download_model; download_model('small', 'modeles-stt/small')"
```

Pour un autre modèle, remplacez `small` aux deux endroits de la commande et dans `modele`. Sur le processeur d'un PC récent, `small` transcrit une phrase en 1 à 3 secondes ; `base` est deux à trois fois plus rapide mais se trompe plus souvent, ce qui convient mieux à un PC peu puissant. Avec une carte NVIDIA, `appareil = "cuda"` permet `medium` ou `large-v3-turbo`, à condition d'installer CUDA 12 et cuDNN 9.

## Configuration

Tous les réglages sont dans [`config.toml`](config.toml) : clé API, modèle, `max_tokens` et effort pour la génération et le dialogue, taille de l'historique, moteur et voix de synthèse, reconnaissance vocale, hôte, port et HTTPS. Relancez `pnj-parlant` après une modification.

`config.toml` est propre à chaque machine et ignoré par git (il contient la clé API). Le dépôt fournit le modèle [`config.toml.example`](config.toml.example) : copiez-le, puis renseignez `cle_api` (section `[claude]`). Si elle est vide, l'application lit la variable d'environnement `ANTHROPIC_API_KEY`. Pensez à reporter dans le modèle tout nouveau réglage.

## Organisation du code et tests

L'application est un paquet Python, `pnj_parlant`, installé par `uv sync --extra tout` ou `pip install -e ".[tout]"` (mode éditable :
les modifications du code sont prises en compte sans réinstaller). Les commandes `pnj-parlant` et `pnj-banque`
cherchent `config.toml` dans le dossier courant ; `--config chemin/vers/config.toml` en désigne un autre.
Les dossiers `pnj/`, `voices/`, `modeles-stt/` et `certs/` sont pris à côté de `config.toml`.

```
pyproject.toml              paquet, dépendances (options : voix, stt, tout, dev), commandes
src/pnj_parlant/
  serveur.py                application Flask (routes) et lancement
  config.py                 lecture de config.toml
  dependances.py            dépendances manquantes dans .venv (lancer.bat)
  fiches.py                 création des fiches de PNJ
  dialogue.py               consignes du PNJ, mise en scène de la conversation à un ou plusieurs PNJ
  texte.py                  nettoyage du texte, nombres en lettres, découpage en phrases
  moteurs.py                modèles de langage : Claude ou Ollama
  voix.py                   synthèse vocale (Pocket TTS, Piper, Edge) et attribution des voix
  stt.py                    reconnaissance vocale (faster-whisper)
  banque.py                 banque de PNJ et scénario (fichiers JSON)
  systeme.py                état de la carte graphique et d'Ollama
  generer.py                remplissage de la banque en lot (pnj-banque)
  static/                   pages web : index.html (accueil, partie, options), creation.html, js/scene.js, js/univers.js
  exemples/                 univers d'exemple proposés sur l'accueil
tests/                      tests Python (pytest) et tests/js/ (Node)
docs/                       installation-windows.md : guide pas à pas Windows
scripts/ecran.sh            libère la mémoire vidéo sous Linux
lancer.bat                  lanceur Windows (double-clic)
```

Les tests n'ont besoin ni de réseau, ni de modèle, ni de carte graphique : de faux moteurs remplacent
le modèle de langage, la synthèse et la reconnaissance vocales (voir `tests/conftest.py`).

```bash
uv sync --extra tout --extra dev   # ou : pip install -e ".[dev]"
pytest                      # tests Python
node --test tests/js/       # fonctions de la page de jeu (Node 22 ou plus récent)
python tests/e2e/lancer.py  # parcours complet dans Edge ou Chrome sans écran (lieux, compagnons, import, interruption, accueil, reprise)
```

## Pistes pour la suite

- Contexte de monde plus riche (ville, rumeurs du jour), et inventaire et prix fixes pour les marchands.
- Mesurer la latence et la charge sur le PC de référence.
