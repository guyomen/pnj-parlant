# PNJ parlants (PoC)

Claude Haiku ou un modèle local invente un PNJ et joue son rôle, Piper lui donne une voix, et vous lui parlez au micro depuis le navigateur.

## Installation (PC ou Raspberry Pi)

Sous Windows, suivez plutôt le guide pas à pas [HOWTO.md](HOWTO.md).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.toml.example config.toml   # puis renseignez cle_api = "sk-ant-..."

# Voix françaises Piper (une ou plusieurs, elles seront tirées au sort)
mkdir -p voices && cd voices
python -m piper.download_voices fr_FR-siwis-medium fr_FR-tom-medium fr_FR-upmc-medium fr_FR-mls-medium
cd ..

python app.py
```

Ouvrez ensuite http://localhost:5000 dans Chrome ou Edge.

## Accès depuis une autre machine (ex. serveur sur le Raspberry Pi)

Le navigateur n'autorise le micro qu'en HTTPS ou sur `localhost`. Mettez donc `https = true` dans la section `[serveur]` de [`config.toml`](config.toml), relancez `python app.py`, puis ouvrez `https://<ip-du-pi>:5000` et acceptez l'avertissement de certificat.

## Comment ça marche

- `POST /api/npc/generate` : Haiku renvoie une fiche JSON (nom, métier, humeur, rumeurs, secret, salutation, timbre, débit). Humeur, trait et initiale du nom sont tirés au sort côté Python pour éviter les PNJ qui se ressemblent.
- `POST /api/npc/talk` : la fiche devient le prompt système, l'historique est renvoyé par le navigateur (serveur sans état).
- `POST /api/tts` : Piper synthétise la réplique avec une voix et un locuteur tirés au hasard parmi ceux du genre du PNJ (section `[voix.genres]` de `config.toml`). Sans voix Piper, le navigateur lit le texte lui-même (`speechSynthesis`), avec une hauteur adaptée au timbre.
- Saisie vocale : Web Speech API du navigateur, en français.

## Préparer le scénario et les PNJ (pour jouer sans réseau)

Ouvrez **http://localhost:5000/creation.html** (lien « Préparer les PNJ et le scénario » sur la page de jeu). La création passe par Claude : faites-la avant de partir, avec le réseau.

1. **Scénario**, en deux parties :
   - **Univers** : lieux, factions, personnages connus, événements. Connu de tous les PNJ, il est aussi transmis pendant les dialogues.
   - **Notes du MJ** : l'intrigue et ses secrets. Elles servent seulement à créer des PNJ cohérents et ne sont jamais transmises pendant les dialogues, pour qu'un PNJ ne révèle pas ce qu'il n'est pas censé savoir.
2. **Demander un PNJ** : métier, nom, genre (tous facultatifs) et son rôle dans le scénario. Claude propose une fiche qui ne cite que des noms présents dans le scénario ou vos consignes.
3. **Relire et ajuster** la fiche, écouter sa voix (bouton « Autre voix » si elle ne convient pas), puis l'**enregistrer dans la banque**. Les PNJ de la banque peuvent être modifiés ou supprimés.

Sur la page de jeu, choisissez un PNJ dans la banque et cliquez sur **Jouer**.

Tout est stocké dans `pnj/` : `_scenario.json` pour le scénario, puis un fichier JSON par PNJ, lisible et modifiable à la main. Copier ce dossier suffit pour emporter un scénario complet.

Pour remplir la banque en lot (le scénario est pris en compte) :

```bash
python generer_banque.py 20                       # 20 PNJ aux métiers tirés au sort
python generer_banque.py 5 --metier "aubergiste"  # 5 aubergistes
```

Si la voix Piper d'un PNJ n'existe pas sur la machine qui l'ouvre, une autre voix du même genre est choisie.

## Modèle local pour les dialogues (sans réseau)

Les répliques des PNJ peuvent venir d'un modèle qui tourne sur le PC, servi par [Ollama](https://ollama.com) dans un conteneur Docker. Le choix se fait dans la section `[moteurs]` de `config.toml`, séparément pour la création (`creation`) et pour les dialogues (`dialogue`).

**Installation, une fois, avec le réseau** (PC avec carte NVIDIA) :

1. Installez Docker, le plugin `docker compose` et le [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), qui donne au conteneur l'accès à la carte graphique.
2. Démarrez Ollama et téléchargez le modèle (environ 5 Go) :

   ```bash
   docker compose up -d
   docker compose exec ollama ollama pull qwen3:8b
   ```
3. Vérifiez que le modèle utilise bien la carte graphique : `docker compose exec ollama ollama ps` doit afficher `100% GPU` après une première réplique.

Le conteneur redémarre ensuite avec le PC. `docker compose down` l'arrête ; `docker compose down -v` supprime aussi les modèles téléchargés.

**Changer de modèle** : téléchargez-le (`ollama pull`), puis changez `modele` dans la section `[local]`. Avec 12 Go de mémoire vidéo, `qwen3:8b`, `gemma3:12b` et `mistral-nemo` tiennent sans problème. Comparez-les sur les mêmes PNJ : la qualité du français varie d'un modèle à l'autre.

**Avant de partir sans réseau**, vérifiez que tout est sur le PC : l'image Docker et le modèle (`docker compose exec ollama ollama list`), les voix Piper dans `voices/`, et la banque de PNJ dans `pnj/`.

## Configuration

Tous les réglages sont dans [`config.toml`](config.toml) : clé API, modèle, `max_tokens` et effort pour la génération et le dialogue, taille de l'historique, dossier des voix, hôte, port et HTTPS. Relancez `python app.py` après une modification.

`config.toml` est propre à chaque machine et ignoré par git (il contient la clé API). Le dépôt fournit le modèle [`config.toml.example`](config.toml.example) : copiez-le, puis renseignez `cle_api` (section `[claude]`). Si elle est vide, l'application lit la variable d'environnement `ANTHROPIC_API_KEY`. Pensez à reporter dans le modèle tout nouveau réglage.

## Pistes pour la suite

- Reconnaissance vocale 100 % locale avec `faster-whisper` (la Web Speech API de Chrome envoie l'audio aux serveurs de Google).
- Sauvegarder les PNJ créés (fichier JSON ou SQLite) pour les retrouver d'une session à l'autre.
- Donner au PNJ un inventaire et des prix fixes, ou un contexte commun (ville, actualité) partagé par tous les PNJ.
