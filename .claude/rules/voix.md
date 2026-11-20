---
paths:
  - "src/pnj_parlant/voix.py"
  - "src/pnj_parlant/stt.py"
  - "src/pnj_parlant/routes/voix.py"
  - "tests/test_voix.py"
  - "tests/test_moteurs_voix.py"
  - "tests/test_stt_systeme.py"
---

# Synthèse et reconnaissance vocales

## Routes (routes/voix.py)
- `POST /api/voice` (autre voix pour un PNJ, `eviter`) ; `GET /api/voices`, `GET|PUT /api/voice-engine` (page de
  création ; PUT sous `@mj`).
- `POST /api/tts {text, voice, narrateur, eviter}` : 503 en cas d'échec → le navigateur utilise `speechSynthesis`.
- `POST /api/stt` (audio webm/opus + `indice`) : 404 si la reconnaissance locale est indisponible ; taille
  `STT_MAX_OCTETS` (`serveur.md`). Micro côté navigateur : `partie.md`.

## Synthèse (voix.py)
- `[voix] moteur` : `pocket` (Pocket TTS, local, WAV, 1 à 3 s par phrase sur un processeur de PC), `piper` (local,
  WAV, très léger) ou `edge` (en ligne, MP3, service non officiel). `voix.MOTEURS` ; `PUT /api/voice-engine`
  change de moteur pour tout le serveur sans toucher à config.toml.
- Attribution : voix tirée parmi celles du genre du PNJ (`genres` par moteur, surchargeables dans
  `[voix.<moteur>.genres]`), réglée d'après `timbre` et `debit` (`length_scale` ; Edge en tire rate/pitch,
  Pocket n'applique ni l'un ni l'autre). `browser_pitch` / `browser_rate` servent au repli `speechSynthesis`.
- `voix.verifier` réattribue une voix stable (graine = nom du PNJ) si la sienne manque sur la machine ou vient
  d'un autre moteur. Deux PNJ d'une même scène n'ont jamais la même voix (`eviter`).
- Piper : catalogue des voix gardé tant que la date de modification du dossier ne change pas (`_voix_installees`) ;
  un `.onnx.json` illisible = une voix à un locuteur ; chargement des voix sous verrou (une seule fois par voix).
- Narrateur (texte entre parenthèses) : voix neutre, `narrateur` dans `[voix.<moteur>]`, jamais celle d'un PNJ
  de la scène.
- Pocket télécharge son modèle et ses voix au premier lancement ; une voix indisponible est signalée dans la
  console et n'est pas attribuée.

## Reconnaissance (stt.py)
- `[reconnaissance] moteur` : `local` (faster-whisper, modèle dans `<dossier>/<modele>`, `modeles-stt/small`)
  ou `navigateur` (Web Speech API, réseau). `appareil` cpu/cuda, `precision`, `beam_size`.
- Modèle chargé à la première requête ; l'indice (noms et métiers des PNJ) sert d'`initial_prompt`.
- `av>=11,<19` dans pyproject.toml : PyAV 19 casse faster-whisper 1.2.x.
