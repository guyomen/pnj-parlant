# PNJ parlants — contexte du projet

## Objectif
Générateur de PNJ (personnages non-joueurs) aléatoires pour jeu de rôle médiéval-fantastique,
avec voix de synthèse. Le joueur parle au PNJ au micro depuis un navigateur, le PNJ répond
dans son personnage, à voix haute. Langue : français.

## Contraintes
- Serveur Python, destiné à tourner sur un PC ou un Raspberry Pi ; client = navigateur web.
- Solutions gratuites / open source privilégiées pour la voix.
- LLM : Claude Haiku via l'API Anthropic (`claude-haiku-5-5`, configurable via `NPC_MODEL`).
  Haiku suffit car le contexte de chaque PNJ est court ; la latence faible compte pour la voix.

## Architecture actuelle (PoC)
```
pnj-vocal/
├── app.py              # Flask : API + service de la page
├── requirements.txt    # flask, anthropic, piper-tts, pyopenssl
├── voices/             # modèles Piper .onnx + .onnx.json (à télécharger)
└── static/index.html   # interface (HTML/CSS/JS vanilla, aucun build)
```
- `GET /api/config` : modèle utilisé + voix Piper détectées dans `voices/`.
- `POST /api/npc/generate {role}` : Haiku renvoie une fiche JSON (nom, metier, apparence,
  personnalite, tic_de_langage, humeur, connaissances[3], secret, salutation, timbre, debit).
  Humeur/trait/initiale du nom sont tirés au sort en Python pour varier les PNJ.
  Le serveur ajoute `voix` (voix Piper + speaker_id + length_scale, et pitch/rate pour le repli navigateur).
- `POST /api/npc/talk {npc, history, message}` : la fiche devient le prompt système ;
  serveur sans état, l'historique est conservé côté navigateur (12 derniers messages).
  Les réponses doivent rester courtes (1-3 phrases), sans markdown/emoji/astérisques, car lues à voix haute.
- `POST /api/tts {text, voice}` : synthèse Piper → WAV. Sans voix Piper, le navigateur
  utilise `speechSynthesis`.
- Reconnaissance vocale du joueur : Web Speech API (Chrome/Edge uniquement, fr-FR).
  Le micro exige `localhost` ou HTTPS → `NPC_HTTPS=1` active un certificat auto-signé.

## Lancement
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
cd voices && python -m piper.download_voices fr_FR-siwis-medium fr_FR-tom-medium && cd ..
python app.py   # http://localhost:5000  (PORT pour changer le port)
```
API Piper utilisée : `PiperVoice.load(path)`, `voice.synthesize_wav(text, wav_file, syn_config=SynthesisConfig(speaker_id=..., length_scale=...))`.

## État / problème en cours
Premier lancement : le serveur démarre mais `/` renvoie « Not Found », et aucun log de
requête n'apparaît côté Python. Pistes : `index.html` pas dans `static/` ; autre processus
sur le port 5000 (ancienne instance, AirPlay sur macOS). À diagnostiquer en premier.

## Pistes pour la suite
- STT 100 % local avec faster-whisper (alternative à la Web Speech API de Chrome).
- Persistance des PNJ créés (JSON ou SQLite).
- Contexte de monde partagé (ville, rumeurs du jour) et inventaire/prix pour les marchands.
- Vérifier la latence et la charge sur Raspberry Pi.
