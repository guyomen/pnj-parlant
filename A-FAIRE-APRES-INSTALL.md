# À faire pour finir l'installation (modèle local sur la carte NVIDIA)

## Où on en est (5 novembre 2026)

- Ollama tourne dans le conteneur Docker `pnj-ollama`, pour l'instant **sur le processeur**.
  Il redémarre tout seul avec le PC (`--restart unless-stopped`).
- Modèle téléchargé : `qwen3:4b-instruct` (2,5 Go), dans le volume Docker `files_ollama-modeles`.
  Il est conservé au redémarrage et quand on recrée le conteneur.
- `config.toml` : `creation = "local"`, `dialogue = "local"`, `[local] modele = "qwen3:4b-instruct"`.
- Le tag `qwen3:4b` tout court réfléchit toujours, même avec `reflexion = false`, et lit son
  raisonnement à voix haute : gardez `qwen3:4b-instruct`.
- La carte graphique (NVIDIA T400, 4 Go) utilise encore le pilote libre `nouveau`, que Docker ne
  peut pas utiliser. D'où les étapes ci-dessous.

## 1. Installer le pilote NVIDIA

```bash
sudo ubuntu-drivers install
sudo reboot
```

Après le redémarrage, vérifiez que la carte est vue :

```bash
nvidia-smi
```

## 2. Donner la carte graphique à Docker

Le NVIDIA Container Toolkit est déjà installé ; il reste à le brancher sur Docker :

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

## 3. Recréer le conteneur Ollama avec la carte graphique

Le modèle téléchargé n'est pas perdu : il est dans le volume, pas dans le conteneur.

```bash
docker rm -f pnj-ollama
docker run -d --name pnj-ollama --restart unless-stopped --gpus all \
  -e OLLAMA_FLASH_ATTENTION=1 -e OLLAMA_KV_CACHE_TYPE=q8_0 \
  -p 127.0.0.1:11434:11434 -v files_ollama-modeles:/root/.ollama ollama/ollama:0.34.4
```

Vérifiez que la carte est utilisée (après une première réplique dans l'application) :

```bash
docker logs pnj-ollama 2>&1 | grep -i cuda
docker exec pnj-ollama ollama ps        # doit afficher 100% GPU
```

Pour être à 100 % GPU sur la T400 (4 Go), il faut aussi :
- `contexte = 2048` dans la section `[local]` de `config.toml` (déjà fait) ;
- libérer la mémoire prise par l'écran (environ 700 Mo) si on n'en a pas besoin, en SSH par exemple :
  `./ecran.sh couper` (jusqu'au prochain redémarrage ; `--permanent` pour toujours démarrer sans écran,
  `./ecran.sh rallumer` pour revenir en arrière). Voir le README, « Petite carte graphique ».

## 4. Relancer l'application

```bash
cd /workspace/ggabriel/TO_REMOVE/Agent_parlant/files
source .venv/bin/activate
pnj-parlant
```

Puis ouvrez https://localhost:7800 dans Chrome ou Edge.

## Facultatif

- **`docker compose`**, pour utiliser les commandes du README :

  ```bash
  sudo apt install docker-compose-v2
  docker rm -f pnj-ollama    # sinon conflit de nom avec le conteneur de docker-compose.yml
  docker compose up -d
  ```

  Attention : `docker compose` utilisera le volume `files_ollama-modeles`, le même qu'aujourd'hui,
  donc le modèle sera déjà là. Pensez à garder `modele = "qwen3:4b-instruct"` dans `config.toml`.
- **Meilleures fiches de PNJ** quand le réseau est là : `creation = "claude"` dans la section
  `[moteurs]` de `config.toml` (les dialogues restent en local).
- **Ménage** : un ancien conteneur `ollama` (jamais démarré) et un volume vide `ollama` traînent :

  ```bash
  docker rm ollama && docker volume rm ollama
  ```
