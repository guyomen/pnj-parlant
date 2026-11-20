---
paths:
  - "src/pnj_parlant/reglages.py"
  - "src/pnj_parlant/routes/options.py"
  - "src/pnj_parlant/static/js/options.js"
  - "tests/test_reglages.py"
  - "tests/test_reglages_a_chaud.py"
---

# Réglages à chaud et page Options

Tout nouveau réglage utile en partie va aussi dans le `CATALOGUE` (voir CLAUDE.md, conventions).

## Serveur (reglages.py)
- `CATALOGUE` : groupes (`id`, `titre`, `aide`, `si` = moteur de langage qui rend le groupe utile) de réglages
  `{cle "section.sous.cle", libelle, type (choix, texte, url, entier, nombre, booleen, secret), defaut, aide, choix,
  min/max/pas, suggestions, redemarrage}`. Les `defaut` doivent égaler ceux du code (sinon la page ment).
- `lire`/`poser` (clé pointée), `pour_la_page` (secrets → `valeur: ""` + `defini`), `valider` (ValueError ; secret :
  "" = inchangé, None = effacé), `ecrire` (tomlkit importé à l'usage, commentaires gardés, remplacement atomique ;
  fichier temporaire supprimé en cas d'échec), `autorise(reglages, mdp, local)` (mot de passe du MJ s'il existe,
  exigé même en local ; sinon `localhost` seulement), `a_redemarrer` (port, HTTPS).
- `Contexte.appliquer_reglages` : nouveau dict, essaie d'abord ce qui peut échouer (moteur de voix), écrit
  `cfg.fichier` (`Config.fichier`, None en tests = en mémoire), puis reconstruit à chaud ce qui a changé (Moteurs,
  voix via `tts_charges`, Reconnaissance, portraits, `parametres()` : historique, intervention, phrases_max, style).
  Sérialisé par `Contexte.verrou_reglages`.
- Routes : `GET /api/reglages` → `{groupes, protege, local, fichier}` (suggestions `local.modele` = modèles
  d'Ollama s'il sert) ; `PUT {changements}` + en-tête `X-Mot-De-Passe-MJ` → 403 (après 1 s de pause si un mauvais
  mot de passe a été envoyé ; avec `mot_de_passe: true` si un mot de passe existe, `garde(…, demander=True)`, pour
  que `envoyer` de js/api.js le demande depuis la vue Partie) / 429 (frein) / 400 / 500 (écriture) / 200
  `{..., redemarrage: [libellés]}` ; `POST /api/reglages/verifier {mot_de_passe}` (même frein, sans
  `mot_de_passe` dans le refus : la page Options a son propre formulaire).

## Page Options (index.html, `#options`, js/options.js)
- Rubriques (`#optionsNav`, construites par `construireNav` d'après les `section[id][data-titre]` de
  `.options-contenu`, intercalaires « Ce navigateur » / « Le serveur » / « État ») ; un clic fait défiler.
- « Cette partie » : réglages du navigateur (`OPTIONS` en localStorage), en lignes `.reglage` (libellé + aide |
  contrôle) avec interrupteurs (`input.interrupteur[role=switch]`, style.css) ; `#multiOpts` grisé et désactivé sans
  `optMulti` (dans `setBusy`).
- « Le serveur » : `ouvrirOptions()` à l'ouverture de la vue (`chargerReglages()` sauf modifications en attente,
  `refreshSys()`, `verifierSante()` ; différé par `queueMicrotask` depuis `afficherVue`), champs générés d'après le
  catalogue (`controle(r)`), `modifsReglages` (valeur revenue à l'origine = retirée ; secret : "" ignoré, « Effacer »
  = null), point `.modifie`, barre collante « N réglages modifiés » (`resumeModifs`), groupes des moteurs non choisis
  en retrait (`groupeUtile`, recalculé si `moteurs.*` change).
- Accès (`afficherAcces`) : déverrouillé / formulaire du mot de passe / modifiable depuis ce PC / lecture seule ; mot
  de passe gardé en sessionStorage `mdp-mj`, envoyé en `X-Mot-De-Passe-MJ`, oublié sur 403 (champs réaffichés
  verrouillés, modifications gardées). `controle(r)` affiche la valeur en attente s'il y en a une ; « Verrouiller »
  abandonne les modifications ; un nombre vidé reprend sa valeur en quittant le champ.
- Après enregistrement : message (fichier, réglages au redémarrage), `chargerConfig()` (la partie reprend les
  moteurs) et `refreshSys()`. `beforeunload` si des modifications attendent.
- « État » (`refreshSys`, toutes les 3 s seulement sur la vue Options) : moteurs (/api/config), Ollama, LM Studio, GPU.
- Fonctions pures (scene.js, testées) : `valeurReglage(type, champ)`, `groupeUtile(groupe, valeurs)`, `resumeModifs(n)`.
- Changement du modèle depuis la vue Partie (`#modeleSel`) : `partie.md`.
