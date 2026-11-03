# Installer les PNJ parlants sur Windows

Ce guide installe l'application sur un PC Windows 10 ou 11 équipé d'une carte graphique NVIDIA, pour jouer **sans réseau** une fois l'installation faite.

Comptez environ une heure, avec une bonne connexion : il faut télécharger environ 10 Go (Docker, le modèle local, les voix).

Ce qui sera installé :

| Élément | Rôle |
|---|---|
| Python | fait tourner l'application (le serveur et les voix Piper) |
| Docker Desktop | fait tourner le modèle local dans un conteneur, sans rien installer d'autre sur la machine |
| Ollama (dans Docker) | sert le modèle de langage qui fait parler les PNJ |

Toutes les commandes se tapent dans **PowerShell** : menu Démarrer, tapez « PowerShell », puis Entrée.

---

## 1. Python

1. Installez Python 3.13 :

   ```powershell
   winget install Python.Python.3.13
   ```

   Sans `winget`, téléchargez l'installateur sur [python.org](https://www.python.org/downloads/windows/) et cochez **« Add python.exe to PATH »** sur le premier écran.
2. Fermez PowerShell, rouvrez-le, puis vérifiez :

   ```powershell
   py -3.13 --version
   ```

## 2. L'application

1. Copiez le dossier du projet sur le PC, par exemple dans `C:\PNJ`.
2. Placez-vous dedans et créez l'environnement Python :

   ```powershell
   cd C:\PNJ
   py -3.13 -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   Si PowerShell refuse d'exécuter `Activate.ps1` (« l'exécution de scripts est désactivée »), autorisez les scripts pour votre compte, puis recommencez :

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

   Si l'installation de `piper-tts` échoue, installez le reste avec `pip install flask anthropic pyopenssl` : l'application fonctionnera avec la voix du navigateur à la place de Piper.
3. Téléchargez les voix françaises :

   ```powershell
   mkdir voices
   cd voices
   python -m piper.download_voices fr_FR-siwis-medium fr_FR-tom-medium fr_FR-upmc-medium fr_FR-mls-medium
   cd ..
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
3. Enregistrez et fermez.

`config.toml` contient votre clé : ne le partagez pas. C'est `config.toml.example` qui se partage.

## 4. Docker et le modèle local

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
5. **Vérifiez que la carte graphique est utilisée** :

   ```powershell
   docker compose logs ollama
   ```

   Une ligne doit mentionner **CUDA** et le nom de votre carte. Si elle parle seulement de CPU, voir [Dépannage](#dépannage).

## 5. Lancer une partie

Double-cliquez sur **`lancer.bat`** dans le dossier du projet. Il démarre le modèle local, puis l'application.

Ouvrez ensuite **http://localhost:5000** dans Chrome ou Edge, sur ce PC. Si vous avez changé le `port` dans `config.toml`, remplacez 5000 par votre port.

Au premier dialogue, le modèle se charge sur la carte graphique : la première réplique peut prendre une dizaine de secondes, les suivantes sont rapides. Pour le vérifier, `docker compose exec ollama ollama ps` doit afficher **100% GPU**.

### Jouer depuis les téléphones des amis

Le navigateur n'autorise le micro qu'en HTTPS (ou sur `localhost`). Pour les autres appareils :

1. Dans `config.toml`, section `[serveur]`, mettez `https = true`, puis relancez `lancer.bat`.
2. Au premier lancement, Windows demande d'autoriser Python sur le réseau : acceptez pour les **réseaux privés**.
3. Trouvez l'adresse du PC avec `ipconfig` (ligne « Adresse IPv4 », par exemple `192.168.1.20`).
4. Sur les téléphones, ouvrez `https://192.168.1.20:5000` et acceptez l'avertissement de sécurité : il est normal avec un certificat créé sur le PC.

Sans internet, les appareils doivent quand même être sur le même Wi-Fi : un routeur ou une box suffit, même sans connexion.

## 6. Avant de partir sans réseau

Avec le réseau, vérifiez que tout est sur le PC :

- [ ] Les PNJ sont créés et enregistrés : page **http://localhost:5000/creation.html**, ou en lot avec `python generer_banque.py 20`. La création passe par Claude, donc demande le réseau.
- [ ] Le modèle local est téléchargé : `docker compose exec ollama ollama list` affiche `qwen3:8b`.
- [ ] Les voix Piper sont dans `voices\`.
- [ ] **Test complet en coupant le Wi-Fi ou le câble réseau** : lancez `lancer.bat`, jouez un PNJ et posez-lui une question.

**Important :** pour l'instant, la reconnaissance vocale du micro passe par les serveurs de Google, via Chrome. Sans réseau, **tapez les questions au clavier**. La reconnaissance vocale locale est la prochaine étape du projet.

---

## Dépannage

| Problème | Solution |
|---|---|
| `docker` n'est pas reconnu | Docker Desktop n'est pas lancé ou PowerShell a été ouvert avant l'installation : lancez Docker Desktop, puis rouvrez PowerShell. |
| `lancer.bat` dit « Docker ne répond pas » | Docker Desktop démarre encore : attendez que son icône indique « Engine running », puis relancez. |
| Les logs d'Ollama ne parlent que de CPU, ou les réponses sont très lentes | Mettez à jour le pilote NVIDIA, redémarrez le PC, puis `docker compose down` et `docker compose up -d`. Vérifiez aussi que Docker Desktop utilise WSL 2 (Settings > General > « Use the WSL 2 based engine »). |
| « Modèle local injoignable » dans l'application | Le conteneur est arrêté : `docker compose up -d`. |
| « Modèle local absent » | Le modèle n'est pas téléchargé : `docker compose exec ollama ollama pull qwen3:8b` (avec le réseau). |
| « Micro refusé » | Ouvrez la page sur `localhost`, ou en `https://` depuis un autre appareil, puis autorisez le micro dans le navigateur. |
| Pas de voix Piper, voix robotique du navigateur | Les voix ne sont pas dans `voices\` (voir étape 2.3), ou `piper-tts` ne s'est pas installé. |
| Changer de modèle | `docker compose exec ollama ollama pull gemma3:12b`, puis `modele = "gemma3:12b"` dans la section `[local]` de `config.toml`. |

**Désinstaller le modèle local** : `docker compose down -v` arrête Ollama et supprime les modèles téléchargés. Docker Desktop se désinstalle ensuite comme n'importe quel programme.
