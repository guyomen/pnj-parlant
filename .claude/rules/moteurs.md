---
paths:
  - "src/pnj_parlant/moteurs.py"
  - "tests/test_moteurs.py"
  - "tests/test_moteurs_local.py"
  - "tests/test_cache.py"
---

# Moteurs de langage (moteurs.py) et caches de latence

## Moteurs
- `[moteurs] creation` et `dialogue` : `"claude"` (`[claude] modele`, `claude-haiku-5-5`), `"local"` (Ollama,
  `[local] modele`) ou `"lmstudio"` (`[lmstudio]` : API compatible OpenAI, `/v1/chat/completions` en SSE ; modèle vide
  = celui chargé, trouvé par `/api/v0/models` ; `<think>…</think>` retiré ; `contexte_max` = contexte du modèle
  chargé ; `etat_lmstudio()` pour la page Options). `MoteurIndisponible` : message destiné au joueur (réseau, Docker
  arrêté, LM Studio arrêté, modèle absent).
- Valeurs par défaut : une seule table `moteurs.DEFAUTS` (égale à `config.toml.example` et au `CATALOGUE` : création et
  dialogue `local`), fusionnée dans `Moteurs.__init__` (`avec_defauts`) : `Moteurs({})` fonctionne, un `config.toml`
  ancien aussi. Claude : délai `[claude] delai_max` (60 s, connexion 5 s), clé absente → `MoteurIndisponible`.
  Ollama / LM Studio : une ligne `{"error"}` ou un flux Ollama sans `done: true` = `MoteurIndisponible` ; délai dépassé
  = message distinct d'« injoignable ».
- Réponses en streaming pour les trois moteurs ; `usage` (tokens) renvoyé en fin de réplique.
- Séquences d'arrêt : `stop` d'Ollama, `stop_sequences` de Claude (liste fournie par `dialogue.arrets`, voir
  `dialogue.md`).

## Caches de latence (lot 6)
- Chaque cache a son invalidation ; tests dans `tests/test_cache.py`. Autres caches : `Contexte.problemes_recents()`
  (`serveur.md`), scénario/lieux/styles de la `Banque` (`univers.md`), catalogue Piper (`voix.md`).
- `Moteurs._en_cache` (`DUREE_CACHE` = 15 s) : liste des modèles d'Ollama (`modeles_locaux`, aussi quand Ollama est
  injoignable : c'est le délai de connexion qu'on évite) et de LM Studio (`/api/v0/models`, une erreur n'est pas
  gardée). Un modèle LM Studio fixé dans `config.toml` ne coûte aucun aller-retour avant la réplique. Vidé en
  reconstruisant `Moteurs` (`appliquer_reglages`) ou par `Moteurs.oublier()`.
