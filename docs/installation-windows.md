# Installer les PNJ parlants sur Windows

Ce guide installe l'application sur un PC Windows 10 ou 11 équipé d'une carte graphique NVIDIA ou AMD, pour jouer **sans réseau** une fois l'installation faite.

Comptez environ une heure, avec une bonne connexion : il faut télécharger environ 10 Go (Docker, le modèle local, les voix).

Ce qui sera installé :

| Élément | Rôle |
|---|---|
| uv (et Python, qu'il installe lui-même) | fait tourner l'application (le serveur, les voix, la reconnaissance vocale) |
| Ollama | sert le modèle de langage qui fait parler les PNJ |
| Docker Desktop (carte NVIDIA seulement) | fait tourner Ollama dans un conteneur, sans rien installer d'autre sur la machine |

Sous Windows, Docker ne sait pas utiliser une carte AMD : avec une carte AMD, Ollama s'installe directement sur le PC, sans Docker. Pour connaître votre carte : Gestionnaire des tâches > Performance > GPU.

Toutes les commandes se tapent dans **PowerShell** : menu Démarrer, tapez « PowerShell », puis Entrée.

---

## 1. uv (gestionnaire Python)

[uv](https://docs.astral.sh/uv/) installe Python 3.13 et les dépendances de l'application, bien plus vite que `pip`.

1. Installez uv :

   ```powershell
   winget install astral-sh.uv
   ```

   Sans `winget` : `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
2. Fermez PowerShell, rouvrez-le, puis vérifiez :

   ```powershell
   uv --version
   ```

Sans uv, installez Python 3.13 (`winget install Python.Python.3.13`, ou [python.org](https://www.python.org/downloads/windows/) en cochant **« Add python.exe to PATH »**) : `lancer.bat` passera alors par `pip`, plus lentement.

## 2. L'application

1. Copiez le dossier du projet sur le PC, par exemple dans `C:\PNJ`.
2. Placez-vous dedans et créez l'environnement Python (`lancer.bat` le fait aussi s'il n'existe pas ; un `.venv` existant n'est jamais modifié, le lanceur signale seulement les dépendances manquantes) :

   ```powershell
   cd C:\PNJ
   uv sync --extra tout
   .venv\Scripts\Activate.ps1
   ```

   Sans uv : `py -3.13 -m venv .venv`, `.venv\Scripts\Activate.ps1`, puis `pip install -e ".[tout]"`.

   Si PowerShell refuse d'exécuter `Activate.ps1` (« l'exécution de scripts est désactivée »), autorisez les scripts pour votre compte, puis recommencez :

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

   Si l'installation des voix (`piper-tts`, `pocket-tts`) échoue, installez le reste avec `uv sync --extra stt` : l'application fonctionnera avec la voix du navigateur.
3. Si vous choisissez les voix Piper (voir l'étape 3), téléchargez-les :

   ```powershell
   mkdir voices
   cd voices
   python -m piper.download_voices fr_FR-siwis-medium fr_FR-tom-medium fr_FR-upmc-medium fr_FR-mls-medium
   cd ..
   ```
4. Téléchargez le modèle de reconnaissance vocale (environ 500 Mo), qui comprend ce que vous dites au micro sans passer par internet :

   ```powershell
   python -c "from faster_whisper import download_model; download_model('small', 'modeles-stt/small')"
   ```

## 3. La configuration

1. Créez votre fichier de configuration à partir du modèle :

   ```powershell
   copy config.toml.example config.toml
   notepad config.toml
   ```
2. Dans le Bloc-notes :
   - `cle_api` (section `[claude]`) : votre clé API Anthropic, entre guillemets. Elle sert à créer les PNJ quand vous avez le réseau.
   - `dialogue = "local"` (section `[moteurs]`) : les PNJ parleront avec le modèle local, sans réseau.
   - `moteur` (section `[voix]`) : `"pocket"` (le plus naturel sans réseau, conseillé), `"piper"` (plus léger) ou `"edge"` (le plus naturel, mais seulement avec le réseau). Le comparatif est dans le [README](../README.md#synthèse-vocale).
3. Enregistrez et fermez.

`config.toml` contient votre clé : ne le partagez pas. C'est `config.toml.example` qui se partage.

## 4. Le modèle local

Suivez **4A** pour une carte NVIDIA, **4B** pour une carte AMD.

### 4A. Carte NVIDIA : Ollama dans Docker

1. **Mettez à jour le pilote NVIDIA** depuis [nvidia.com/drivers](https://www.nvidia.com/drivers) ou l'application NVIDIA. Sous Windows, c'est tout ce qu'il faut pour que Docker accède à la carte graphique : rien à installer en plus.
2. **Installez WSL 2**, dont Docker a besoin. Ouvrez PowerShell **en administrateur** (clic droit sur PowerShell, « Exécuter en tant qu'administrateur ») :

   ```powershell
   wsl --install
   ```

   Redémarrez le PC quand c'est demandé.
3. **Installez Docker Desktop** :

   ```powershell
   winget install Docker.DockerDesktop
   ```

   Ou téléchargez-le sur [docker.com](https://www.docker.com/products/docker-desktop/). Lancez-le une première fois et acceptez les conditions. Dans **Settings > General**, cochez **« Start Docker Desktop when you sign in »** : le modèle local sera disponible dès l'ouverture de la session.
4. **Démarrez Ollama et téléchargez le modèle** (environ 5 Go), depuis le dossier du projet :

   ```powershell
   cd C:\PNJ
   docker compose up -d
   docker compose exec ollama ollama pull qwen3:8b
   ```

   Avec une carte de 4 Go (ex. NVIDIA T400), `qwen3:8b` ne tient pas : prenez `qwen3:4b-instruct` et `contexte = 2048`, voir le [README](../README.md#modèle-local-pour-les-dialogues-sans-réseau), « Petite carte graphique ».
5. **Vérifiez que la carte graphique est utilisée** :

   ```powershell
   docker compose logs ollama
   ```

   Une ligne doit mentionner **CUDA** et le nom de votre carte. Si elle parle seulement de CPU, voir [Dépannage](#dépannage).

### 4B. Carte AMD : Ollama installé sur le PC

N'installez pas Docker : il ne servirait à rien ici, et un Ollama dans Docker prendrait le même port que celui installé sur le PC.

Ollama gère sous Windows les cartes Radeon récentes (RX 6000, 7000 et 9000, et certaines Radeon PRO) ; la liste exacte est sur [docs.ollama.com/gpu](https://docs.ollama.com/gpu). Pour une carte plus ancienne ou une puce graphique intégrée, voir [Dépannage](#dépannage).

1. **Mettez à jour le pilote AMD** (AMD Software: Adrenalin Edition) depuis [amd.com/support](https://www.amd.com/fr/support/download/drivers.html), puis redémarrez le PC.
2. **Installez Ollama** :

   ```powershell
   winget install Ollama.Ollama
   ```

   Ou téléchargez-le sur [ollama.com/download](https://ollama.com/download). Ollama démarre ensuite tout seul à l'ouverture de la session (icône de lama près de l'horloge).
3. **Fermez PowerShell, rouvrez-le, puis téléchargez le modèle** (environ 5 Go) :

   ```powershell
   ollama pull qwen3:8b
   ```
4. **Vérifiez que la carte graphique est utilisée** : ouvrez le journal d'Ollama.

   ```powershell
   notepad $env:LOCALAPPDATA\Ollama\server.log
   ```

   Une ligne doit mentionner **ROCm** et le nom de votre carte. Si elle parle seulement de CPU, voir [Dépannage](#dépannage).

Dans la suite de ce guide, remplacez `docker compose exec ollama ollama` par `ollama` tout court : par exemple `ollama ps` au lieu de `docker compose exec ollama ollama ps`.

## 5. Lancer une partie

Double-cliquez sur **`lancer.bat`** dans le dossier du projet. Il prépare le modèle local seulement si `config.toml` en utilise un (`"local"` dans `[moteurs]`) : il prend Ollama installé sous Windows s'il existe (carte AMD), et le démarre s'il ne répond pas ; sinon, avec une carte NVIDIA, il démarre Ollama dans Docker. Il lance ensuite l'application. En tout-Claude, Docker et Ollama sont inutiles.

Ouvrez ensuite **http://localhost:5000** dans Chrome ou Edge, sur ce PC. Si vous avez changé le `port` dans `config.toml`, remplacez 5000 par votre port.

Au premier dialogue, le modèle se charge sur la carte graphique : la première réplique peut prendre une dizaine de secondes, les suivantes sont rapides. Pour le vérifier, `docker compose exec ollama ollama ps` doit afficher **100% GPU**.

**Premier essai** : sur l'accueil, cliquez sur **Exemple : Pré-Novice** pour charger un univers prêt à jouer (3 lieux, 5 PNJ), puis sur **Un PNJ de l'univers au hasard**.

L'accueil, la partie, les options (couper la parole au PNJ, scène à plusieurs PNJ…) et le partage d'un univers en zip sont décrits dans le [README](../README.md#jouer). Pour couper le PNJ simplement en parlant, prenez un casque.

### Jouer depuis les téléphones des amis

Le navigateur n'autorise le micro qu'en HTTPS (ou sur `localhost`). Pour les autres appareils :

1. Dans `config.toml`, section `[serveur]`, mettez `https = true`, puis relancez `lancer.bat`.
2. Au premier lancement, Windows demande d'autoriser Python sur le réseau : acceptez pour les **réseaux privés**.
3. Trouvez l'adresse du PC avec `ipconfig` (ligne « Adresse IPv4 », par exemple `192.168.1.20`).
4. Sur les téléphones, ouvrez `https://192.168.1.20:5000` et acceptez l'avertissement de sécurité : il est normal avec un certificat créé sur le PC.

Sans internet, les appareils doivent quand même être sur le même Wi-Fi : un routeur ou une box suffit, même sans connexion.

## 6. Avant de partir sans réseau

Avec le réseau, vérifiez que tout est sur le PC :

- [ ] Les PNJ sont créés et enregistrés : page **http://localhost:5000/creation.html**, ou en lot avec `pnj-banque 20`. La création passe par Claude, donc demande le réseau. Pour un premier essai, chargez plutôt l'univers d'exemple depuis l'accueil (voir [Lancer une partie](#5-lancer-une-partie)).
- [ ] Le modèle local est téléchargé : `docker compose exec ollama ollama list` (carte AMD : `ollama list`) affiche `qwen3:8b`.
- [ ] Les voix sont téléchargées : avec `moteur = "pocket"`, l'application a été lancée une fois avec le réseau et la fenêtre n'affiche aucune « voix indisponible » ; avec `moteur = "piper"`, les voix sont dans `voices\`. Le moteur `edge` ne marche pas sans réseau.
- [ ] Le modèle de reconnaissance vocale est dans `modeles-stt\small\` (étape 2.4), et `config.toml` contient la section `[reconnaissance]` avec `moteur = "local"`.
- [ ] **Test complet en coupant le Wi-Fi ou le câble réseau** : lancez `lancer.bat`, jouez un PNJ et posez-lui une question.

Au lancement, si la fenêtre affiche « modèle Whisper absent », la reconnaissance vocale passe par les serveurs de Google (Chrome) ou Microsoft (Edge) et ne marchera pas sans réseau : téléchargez le modèle (étape 2.4).

---

## Dépannage

| Problème | Solution |
|---|---|
| `docker` n'est pas reconnu | Docker Desktop n'est pas lancé ou PowerShell a été ouvert avant l'installation : lancez Docker Desktop, puis rouvrez PowerShell. |
| `lancer.bat` dit « Docker ne répond pas » | Docker Desktop démarre encore : attendez que son icône indique « Engine running », puis relancez. |
| Les logs d'Ollama ne parlent que de CPU, ou les réponses sont très lentes | Mettez à jour le pilote NVIDIA, redémarrez le PC, puis `docker compose down` et `docker compose up -d`. Vérifiez aussi que Docker Desktop utilise WSL 2 (Settings > General > « Use the WSL 2 based engine »). |
| Carte AMD : le journal d'Ollama ne parle que de CPU, ou les réponses sont très lentes | Mettez à jour le pilote AMD et redémarrez le PC. Si votre carte n'est pas dans la [liste d'Ollama](https://docs.ollama.com/gpu) (RX 5000 ou plus ancienne, puce intégrée), essayez le mode Vulkan, encore expérimental : `setx OLLAMA_VULKAN 1`, puis quittez Ollama (clic droit sur l'icône du lama, « Quit Ollama ») et relancez-le depuis le menu Démarrer. |
| « Modèle local injoignable » dans l'application | Le conteneur est arrêté : `docker compose up -d`. Carte AMD : Ollama n'est pas lancé, démarrez-le depuis le menu Démarrer. |
| « Modèle local absent » | Le modèle n'est pas téléchargé : `docker compose exec ollama ollama pull qwen3:8b` (carte AMD : `ollama pull qwen3:8b`), avec le réseau. |
| « Modèle Whisper absent » au lancement | Le modèle de reconnaissance vocale n'est pas téléchargé (étape 2.4), ou `modele` dans la section `[reconnaissance]` de `config.toml` ne correspond pas au dossier de `modeles-stt\`. |
| `POST /api/stt` échoue avec `metadata_errors` | Environnement `.venv` créé avant que `pyproject.toml` n'écarte PyAV 19, incompatible avec faster-whisper (`lancer.bat` ne modifie jamais un `.venv` existant). Depuis le dossier du projet, exécutez `uv pip install "av<19"` (sans uv : `.venv\Scripts\python.exe -m pip install "av<19"`), puis relancez l'application. |
| « Micro refusé » | Ouvrez la page sur `localhost`, ou en `https://` depuis un autre appareil, puis autorisez le micro dans le navigateur. |
| Voix robotique du navigateur à la place de celle du PNJ | Pocket TTS : lancez l'application une fois avec le réseau pour télécharger le modèle et les voix. Piper : les voix ne sont pas dans `voices\` (étape 2.3). Edge : le réseau est coupé. |
| « Pocket TTS : voix … indisponible » au lancement | Cette voix n'a pas encore été téléchargée : relancez l'application avec le réseau. |
| Changer de modèle | `docker compose exec ollama ollama pull gemma3:12b`, puis `modele = "gemma3:12b"` dans la section `[local]` de `config.toml`. |

**Désinstaller le modèle local** : `docker compose down -v` arrête Ollama et supprime les modèles téléchargés. Docker Desktop se désinstalle ensuite comme n'importe quel programme. Carte AMD : `ollama rm qwen3:8b` supprime le modèle, puis Ollama se désinstalle comme n'importe quel programme.
