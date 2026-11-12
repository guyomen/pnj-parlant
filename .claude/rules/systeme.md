---
paths:
  - "lancer.bat"
  - "scripts/**"
  - "docker-compose.yml"
  - "pyproject.toml"
  - "uv.lock"
  - ".python-version"
  - "config.toml*"
  - "src/pnj_parlant/config.py"
  - "src/pnj_parlant/dependances.py"
  - "src/pnj_parlant/systeme.py"
  - "README.md"
  - "docs/**"
  - "tests/test_config_et_generer.py"
  - "tests/test_dependances.py"
---

# Installation, lancement, configuration, machine

## Paquet et dépendances
- `pyproject.toml` : options `voix`, `stt`, `tout`, `dev` ; commandes `pnj-parlant` et `pnj-banque`.
  `uv.lock` fige les versions, `.python-version` = 3.13 (`requires-python >= 3.11` pour tomllib) : les deux sont
  versionnés (installation reproductible, lancer.bat fait `uv sync`).
- `dependances.py` : lancé par lancer.bat comme simple fichier (bibliothèque standard seule), signale les paquets
  absents du `.venv` (présence, pas version) et un `.venv` qui ne s'importe plus ; code 1 si l'application ne
  peut pas démarrer. Il n'installe jamais rien.

## Configuration (config.py)
- `config.toml` du dossier courant, sinon `PNJ_CONFIG` ou `--config` ; `pnj/`, `voices/`, `modeles-stt/`,
  `certs/` sont relatifs au dossier de config.toml. config.toml (clé API) n'est pas versionné.
- Tout nouveau réglage se reporte, commenté, dans `config.toml.example`, et dans README.md si l'utilisateur doit
  le connaître.
- `python -m pnj_parlant.config` : code 0 si un moteur « local » attend Ollama sur ce PC, 1 sinon, 2 si
  config.toml est absent (utilisé par lancer.bat).
- `[serveur] https = true` : certificat auto-signé dans `certs/` (micro depuis un autre appareil).

## Lanceurs
- `lancer.bat` (Windows) : `.venv` existant utilisé tel quel, jamais modifié ; sinon créé avec uv (ou venv + pip).
  Ollama seulement si un moteur est local : Ollama Windows s'il est installé (démarré s'il ne répond pas), sinon
  Docker si carte NVIDIA, sinon message. Puis `python -m pnj_parlant`.
- `docker-compose.yml` : Ollama (image figée) dans le conteneur `pnj-ollama`, volume `ollama-modeles`,
  flash attention + cache KV q8_0, port lié à 127.0.0.1.
- `scripts/ecran.sh` (Linux) : coupe/rallume l'écran graphique pour libérer ~700 Mo de VRAM.
- `systeme.py` : état GPU (nvidia-smi) et Ollama pour `/api/etat`.

## Documentation
- README.md : Linux, fonctionnement, page de jeu, réglages, organisation du code. docs/installation-windows.md : pas à pas Windows
  (NVIDIA via Docker, AMD via Ollama Windows), pour un public non développeur.
- Modèles locaux testés : `qwen3:4b-instruct` + `contexte = 2048` sur 4 Go de VRAM (le tag `qwen3:4b` réfléchit
  toujours et lit son raisonnement), `qwen3:8b` au-delà.
