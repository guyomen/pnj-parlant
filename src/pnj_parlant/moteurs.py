"""
Moteurs de langage : Claude (API Anthropic), modèle local (Ollama, dans Docker)
ou modèle local servi par LM Studio (API compatible OpenAI).

Le choix se fait dans la section [moteurs] de config.toml, séparément pour la création
des fiches et pour les dialogues :
    creation = "claude"     # meilleure inventivité, demande le réseau
    dialogue = "local"      # fonctionne sans réseau (Ollama)
    dialogue = "lmstudio"   # fonctionne sans réseau (LM Studio, sans Docker)
"""
import copy
import json
import re
import threading
import time
import urllib.error
import urllib.request

import anthropic

try:  # le SDK Anthropic 2.x repose sur httpx2 (ses erreurs réseau en viennent), les versions précédentes sur httpx
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx


DUREE_CACHE = 15  # secondes : liste des modèles d'Ollama et de LM Studio


class MoteurIndisponible(Exception):
    """Le moteur ne répond pas (réseau, Docker arrêté, modèle absent…). Le message est pour le joueur."""


# Valeurs par défaut des moteurs, appliquées quand config.toml ne les donne pas (ancien fichier, section absente).
# Elles reprennent config.toml.example et le CATALOGUE de reglages.py : les trois doivent rester d'accord.
DEFAUTS = {
    "moteurs": {"creation": "local", "dialogue": "local"},
    "claude": {"cle_api": "", "modele": "claude-haiku-5-5", "delai_max": 60,
               "generation": {"max_tokens": 2000, "effort": "low"},
               "dialogue": {"max_tokens": 250, "effort": "low"}},
    "local": {"url": "http://localhost:11434", "modele": "qwen3:8b", "reflexion": False, "contexte": 8192,
              "temperature": 0.8, "garder_en_memoire": "2h", "delai_max": 180,
              "generation": {"max_tokens": 1500}, "dialogue": {"max_tokens": 200}},
    "lmstudio": {"url": "http://localhost:1234", "modele": "", "reflexion": False, "temperature": 0.8,
                 "delai_max": 180, "generation": {"max_tokens": 1500}, "dialogue": {"max_tokens": 200}},
}


def avec_defauts(config, defauts=DEFAUTS):
    """Copie de `config` complétée par `defauts`, section par section (une section qui n'est pas une table
    est remplacée par les défauts)."""
    resultat = copy.deepcopy(defauts)
    for cle, valeur in (config.items() if isinstance(config, dict) else ()):
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = avec_defauts(valeur, resultat[cle])
        elif cle not in resultat or not isinstance(resultat[cle], dict):
            resultat[cle] = valeur
    return resultat


MESSAGE_SANS_CLE = ("Clé API Claude absente : renseignez-la dans la page Options (ou la variable "
                    "ANTHROPIC_API_KEY), ou choisissez un moteur local.")


class Moteurs:
    def __init__(self, config):
        config = avec_defauts(config)
        self.choix = config["moteurs"]
        self.claude_cfg = config["claude"]
        self.local_cfg = config["local"]
        self.lmstudio_cfg = config["lmstudio"]
        # Réponses des serveurs de modèles gardées quelques secondes : {clé: (échéance, valeur)}. Le cache vit avec
        # l'instance : changer de réglages reconstruit les moteurs (Contexte.appliquer_reglages) et le vide.
        self._cache = {}
        self._verrou_cache = threading.Lock()
        # Clé de config.toml ; si elle est vide, le SDK lit ANTHROPIC_API_KEY dans l'environnement.
        # Délai de lecture borné (le SDK attend 10 minutes par défaut) ; la connexion doit s'établir en 5 s.
        delai = self._delai(self.claude_cfg)
        self.client = anthropic.Anthropic(api_key=self.claude_cfg.get("cle_api") or None,
                                          timeout=httpx.Timeout(delai, connect=5), max_retries=1)

    def _en_cache(self, cle, calculer):
        """Valeur de `calculer()` gardée DUREE_CACHE secondes (un serveur injoignable aussi : c'est le délai de
        connexion qu'on évite de payer à chaque page). Une exception (MoteurIndisponible) n'est pas gardée."""
        with self._verrou_cache:
            trouve = self._cache.get(cle)
        if trouve and trouve[0] > time.monotonic():
            return copy.deepcopy(trouve[1])
        valeur = calculer()
        with self._verrou_cache:
            self._cache[cle] = (time.monotonic() + DUREE_CACHE, valeur)
        return copy.deepcopy(valeur)

    def oublier(self):
        """Vide le cache des modèles (après un `ollama pull`, ou à la demande)."""
        with self._verrou_cache:
            self._cache.clear()

    @staticmethod
    def _delai(cfg):
        try:
            delai = float(cfg.get("delai_max", 60))
        except (TypeError, ValueError):
            return 60.0
        return delai if delai > 0 else 60.0

    def description(self):
        def nom(m):
            if m == "claude":
                return self.claude_cfg["modele"]
            if m == "lmstudio":
                return f"LM Studio : {self.lmstudio_cfg.get('modele') or 'modèle chargé'}"
            return f"local : {self.local_cfg.get('modele')}"
        return {"creation": nom(self.choix["creation"]), "dialogue": nom(self.choix["dialogue"])}

    def contexte_max(self):
        """Taille connue de la fenêtre de contexte du moteur de dialogue, en tokens."""
        if self.choix["dialogue"] == "lmstudio":
            try:
                limite = self._lmstudio_modele().get("loaded_context_length")
            except MoteurIndisponible:
                limite = None
        else:
            limite = (self.local_cfg.get("contexte", 8192) if self.choix["dialogue"] == "local"
                      else self.claude_cfg.get("contexte"))
        return limite if type(limite) is int and limite > 0 else None

    def modeles_locaux(self):
        """Modèles installés dans Ollama : [{"nom": ..., "taille": octets}]. Vide si Ollama ne répond pas.
        Gardé quelques secondes (chaque ouverture de page le demande)."""
        return self._en_cache(("ollama", self.local_cfg.get("url")), self._lire_modeles_locaux)

    def _lire_modeles_locaux(self):
        url = f"{self.local_cfg.get('url', 'http://localhost:11434').rstrip('/')}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return [{"nom": x["name"], "taille": x.get("size", 0)} for x in json.loads(r.read())["models"]]
        except (OSError, ValueError, KeyError):
            return []

    def modele_local_installe(self, installes):
        """Nom du modèle configuré tel qu'Ollama le liste (« mistral-nemo » → « mistral-nemo:latest »)."""
        nom = self.local_cfg.get("modele", "")
        return next((x["nom"] for x in installes if x["nom"] in (nom, f"{nom}:latest")), nom)

    # --- Points d'entrée ------------------------------------------------------
    def fiche(self, system, demande, schema):
        """Texte JSON de la fiche d'un PNJ, conforme à `schema`."""
        messages = [{"role": "user", "content": demande}]
        if self.choix["creation"] == "local":
            return self._local(system, messages, self.local_cfg["generation"]["max_tokens"], schema)
        if self.choix["creation"] == "lmstudio":
            return self._lmstudio(system, messages, self.lmstudio_cfg["generation"]["max_tokens"], schema)
        cfg = self.claude_cfg["generation"]
        return self._claude(system, messages, cfg["max_tokens"],
                            {"effort": cfg["effort"], "format": {"type": "json_schema", "schema": schema}})

    def replique(self, system, messages, arrets=(), on_usage=None, longueur="normal"):
        """Réplique du PNJ dans le dialogue, morceau de texte par morceau de texte (générateur),
        pour commencer à la lire avant qu'elle soit finie. `arrets` : textes qui arrêtent net la génération
        (ex. « Léonard : », quand le modèle se met à écrire la réplique d'un autre).
        Lève MoteurIndisponible dès l'appel si le moteur ne répond pas ; pendant la lecture du
        générateur si la connexion se coupe en cours de route."""
        multiplicateur = {"short": 0.5, "normal": 1, "long": 2}[longueur]
        if self.choix["dialogue"] == "local":
            maximum = max(64, round(self.local_cfg["dialogue"]["max_tokens"] * multiplicateur))
            return self._local_flux(system, messages, maximum, arrets, on_usage)
        if self.choix["dialogue"] == "lmstudio":
            maximum = max(64, round(self.lmstudio_cfg["dialogue"]["max_tokens"] * multiplicateur))
            return self._lmstudio_flux(system, messages, maximum, arrets, on_usage)
        cfg = self.claude_cfg["dialogue"]
        maximum = max(64, round(cfg["max_tokens"] * multiplicateur))
        return self._claude_flux(system, messages, maximum, {"effort": cfg["effort"]}, arrets, on_usage)

    # --- Claude ---------------------------------------------------------------
    def _claude(self, system, messages, max_tokens, output_config):
        try:
            msg = self.client.messages.create(model=self.claude_cfg["modele"], max_tokens=max_tokens,
                                              system=system, messages=messages, output_config=output_config)
        except TypeError as e:  # le SDK refuse de partir sans clé API
            raise MoteurIndisponible(MESSAGE_SANS_CLE) from e
        except anthropic.APIConnectionError as e:
            raise MoteurIndisponible("Pas de connexion à Claude.") from e
        except anthropic.APIStatusError as e:
            raise MoteurIndisponible(f"Claude a refusé la requête ({e.status_code}).") from e
        except (anthropic.APIError, httpx.HTTPError) as e:
            raise MoteurIndisponible("La connexion à Claude s'est interrompue.") from e
        if msg.stop_reason == "max_tokens":
            print(f"[claude] réponse coupée à max_tokens={max_tokens}")
        return "".join(b.text for b in msg.content if b.type == "text")

    def _claude_flux(self, system, messages, max_tokens, output_config, arrets=(), on_usage=None):
        options = {"stop_sequences": list(arrets)} if arrets else {}
        try:  # la requête part ici : une erreur de connexion est levée avant de renvoyer le générateur
            flux = self.client.messages.create(model=self.claude_cfg["modele"], max_tokens=max_tokens,
                                               system=system, messages=messages, output_config=output_config,
                                               stream=True, **options)
        except TypeError as e:  # le SDK refuse de partir sans clé API
            raise MoteurIndisponible(MESSAGE_SANS_CLE) from e
        except anthropic.APIConnectionError as e:
            raise MoteurIndisponible("Pas de connexion à Claude.") from e
        except anthropic.APIStatusError as e:
            raise MoteurIndisponible(f"Claude a refusé la requête ({e.status_code}).") from e
        except (anthropic.APIError, httpx.HTTPError) as e:
            raise MoteurIndisponible("La connexion à Claude s'est interrompue.") from e

        def morceaux():
            usage = {}
            try:
                for event in flux:
                    if event.type == "message_start":
                        compteurs = event.message.usage
                        usage["input_tokens"] = sum(
                            getattr(compteurs, cle, 0) or 0
                            for cle in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                    elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield event.delta.text
                    elif event.type == "message_delta":
                        if event.delta.stop_reason == "max_tokens":
                            print(f"[claude] réponse coupée à max_tokens={max_tokens}")
                        if event.usage and hasattr(event.usage, "output_tokens"):
                            usage["output_tokens"] = event.usage.output_tokens
            except (anthropic.APIError, httpx.HTTPError) as e:
                raise MoteurIndisponible("La connexion à Claude s'est interrompue.") from e
            finally:
                flux.close()  # réponse abandonnée en route (Stop, filtre) : Claude arrête d'écrire
            if on_usage and {"input_tokens", "output_tokens"} <= usage.keys():
                on_usage(usage)
        return morceaux()

    # --- Modèle local (API d'Ollama) ------------------------------------------
    def _local(self, system, messages, max_tokens, schema=None):
        try:
            with self._ollama(system, messages, max_tokens, schema, stream=False) as r:
                data = json.loads(r.read())
        except (OSError, ValueError) as e:  # délai dépassé en lisant, connexion coupée, réponse illisible
            raise MoteurIndisponible(self._message_lecture("Le modèle local", e)) from e
        if isinstance(data, dict) and data.get("error"):
            raise MoteurIndisponible(f"Le modèle local a renvoyé une erreur : {str(data['error'])[:200]}")
        return data.get("message", {}).get("content", "") if isinstance(data, dict) else ""

    @staticmethod
    def _delai_depasse(erreur):
        return isinstance(erreur, TimeoutError) or isinstance(getattr(erreur, "reason", None), TimeoutError)

    @staticmethod
    def _message_lecture(nom, erreur):
        if isinstance(erreur, TimeoutError):
            return f"{nom} met trop de temps à répondre : patientez, ou augmentez delai_max dans config.toml."
        return f"{nom} s'est interrompu."

    def _local_flux(self, system, messages, max_tokens, arrets=(), on_usage=None):
        r = self._ollama(system, messages, max_tokens, stream=True, arrets=arrets)

        def morceaux():
            # Ollama envoie une ligne JSON par morceau de texte, jusqu'à "done": true.
            # Réponse abandonnée en route (Stop, filtre) : fermer la connexion arrête la génération.
            usage = {}
            termine = False
            try:
                with r:
                    for ligne in r:
                        if ligne.strip():
                            data = json.loads(ligne)
                            if data.get("error"):  # mémoire vidéo pleine, modèle déchargé…
                                raise MoteurIndisponible(
                                    f"Le modèle local a renvoyé une erreur : {str(data['error'])[:200]}")
                            if data.get("done"):
                                termine = True
                                if data.get("prompt_eval_count") is not None:
                                    usage["input_tokens"] = data["prompt_eval_count"]
                                if data.get("eval_count") is not None:
                                    usage["output_tokens"] = data["eval_count"]
                            yield data.get("message", {}).get("content", "")
            except (OSError, ValueError) as e:  # coupure réseau, délai dépassé, ligne illisible
                raise MoteurIndisponible(self._message_lecture("Le modèle local", e)) from e
            if not termine:  # flux coupé net : la réplique n'est pas complète
                raise MoteurIndisponible("Le modèle local s'est interrompu.")
            if on_usage and {"input_tokens", "output_tokens"} <= usage.keys():
                on_usage(usage)
        return morceaux()

    def _ollama(self, system, messages, max_tokens, schema=None, stream=False, arrets=()):
        """Envoie la requête à Ollama et renvoie la réponse HTTP ouverte."""
        cfg = self.local_cfg
        body = {
            "model": cfg["modele"],
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": stream,
            "keep_alive": cfg.get("garder_en_memoire", "2h"),  # évite de recharger le modèle à chaque réplique
            "options": {"num_predict": max_tokens, "num_ctx": cfg.get("contexte", 8192),
                        "temperature": cfg.get("temperature", 0.8)},
        }
        if schema:
            body["format"] = schema  # Ollama contraint la sortie à ce schéma JSON
        if arrets:
            body["options"]["stop"] = list(arrets)  # la génération s'arrête net sur l'un de ces textes
        if cfg.get("reflexion") is not None:
            body["think"] = bool(cfg["reflexion"])  # false : coupe le mode réflexion (Qwen 3…), plus rapide
        req = urllib.request.Request(f"{cfg['url'].rstrip('/')}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=cfg.get("delai_max", 180))
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 404:
                raise MoteurIndisponible(f"Modèle local « {cfg['modele']} » absent : téléchargez-le "
                                         f"(docker compose exec ollama ollama pull {cfg['modele']}).") from e
            raise MoteurIndisponible(f"Le modèle local a renvoyé une erreur : {detail[:200]}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if self._delai_depasse(e):  # le modèle répond, mais lentement (chargement, carte saturée)
                raise MoteurIndisponible(self._message_lecture("Le modèle local", TimeoutError())) from e
            raise MoteurIndisponible("Modèle local injoignable : lancez-le avec « docker compose up -d ».") from e

    # --- Modèle local (LM Studio, API compatible OpenAI) ----------------------
    def _lmstudio(self, system, messages, max_tokens, schema=None):
        try:
            with self._lmstudio_requete(system, messages, max_tokens, schema) as r:
                data = json.loads(r.read())
            if isinstance(data, dict) and data.get("error"):
                raise MoteurIndisponible(f"LM Studio a renvoyé une erreur : {self._detail_erreur(data['error'])}")
            choix = data["choices"][0]
            texte = choix["message"].get("content") or ""
        except (OSError, ValueError) as e:  # délai dépassé en lisant, connexion coupée, réponse illisible
            raise MoteurIndisponible(self._message_lecture("LM Studio", e)) from e
        except (KeyError, IndexError, TypeError, AttributeError) as e:  # réponse d'un autre format que prévu
            raise MoteurIndisponible("LM Studio a renvoyé une réponse inattendue.") from e
        if choix.get("finish_reason") == "length":
            print(f"[lmstudio] réponse coupée à max_tokens={max_tokens}")
        # Les modèles à réflexion (Qwen 3…) peuvent laisser leur raisonnement dans <think>…</think>
        return re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL).strip()

    @staticmethod
    def _detail_erreur(erreur):
        """Texte d'une erreur de LM Studio : chaîne, ou objet {"message": ...} au format OpenAI."""
        if isinstance(erreur, dict):
            erreur = erreur.get("message") or json.dumps(erreur, ensure_ascii=False)
        return str(erreur)[:200]

    def _lmstudio_flux(self, system, messages, max_tokens, arrets=(), on_usage=None):
        r = self._lmstudio_requete(system, messages, max_tokens, stream=True, arrets=arrets)

        def morceaux():
            # Flux SSE au format OpenAI : « data: {...} » par morceau de texte, jusqu'à « data: [DONE] ».
            # Réponse abandonnée en route (Stop, filtre) : fermer la connexion arrête la génération.
            usage = {}
            try:
                with r:
                    for ligne in r:
                        ligne = ligne.decode("utf-8").strip()
                        if not ligne.startswith("data:"):
                            continue
                        ligne = ligne[5:].strip()
                        if ligne == "[DONE]":
                            break
                        data = json.loads(ligne)
                        if data.get("error"):
                            raise MoteurIndisponible(
                                f"LM Studio a renvoyé une erreur : {self._detail_erreur(data['error'])}")
                        if data.get("usage"):
                            usage["input_tokens"] = data["usage"].get("prompt_tokens")
                            usage["output_tokens"] = data["usage"].get("completion_tokens")
                        for choix in data.get("choices", []):
                            if choix.get("finish_reason") == "length":
                                print(f"[lmstudio] réponse coupée à max_tokens={max_tokens}")
                            if choix.get("delta", {}).get("content"):
                                yield choix["delta"]["content"]
            except (OSError, ValueError) as e:  # coupure réseau, délai dépassé, ligne illisible
                raise MoteurIndisponible(self._message_lecture("LM Studio", e)) from e
            if on_usage and usage and None not in usage.values():
                on_usage(usage)
        return morceaux()

    def etat_lmstudio(self):
        """Pour la page Options : {"ok": True, "modele": id} ou {"ok": False, "message": raison}."""
        try:
            return {"ok": True, "modele": self._lmstudio_modele().get("id", "")}
        except MoteurIndisponible as e:
            return {"ok": False, "message": str(e)}

    def modeles_lmstudio(self):
        """Modèles de langage connus de LM Studio (identifiants), pour le choix du modèle dans la partie. Vide si
        LM Studio ne répond pas."""
        try:
            modeles = self._en_cache(("lmstudio", self.lmstudio_cfg.get("url")), self._lire_modeles_lmstudio)
        except MoteurIndisponible:
            return []
        return [m["id"] for m in modeles if m.get("type") in ("llm", "vlm") and isinstance(m.get("id"), str)]

    def _lmstudio_modele(self):
        """Modèle chargé dans LM Studio (fiche de /api/v0/models), celui de config.toml s'il est renseigné."""
        cfg = self.lmstudio_cfg
        modeles = self._en_cache(("lmstudio", cfg.get("url")), self._lire_modeles_lmstudio)
        if cfg.get("modele"):
            return next((m for m in modeles if m.get("id") == cfg["modele"]), {"id": cfg["modele"]})
        # /api/v0/models (propre à LM Studio) indique le type et l'état de chaque modèle, contrairement à /v1/models
        charges = [m for m in modeles if m.get("state") == "loaded" and m.get("type") in ("llm", "vlm")]
        if not charges:
            raise MoteurIndisponible("Aucun modèle chargé dans LM Studio : chargez-en un, ou renseignez "
                                     "`modele` dans la section [lmstudio] de config.toml.")
        return charges[0]

    def _lire_modeles_lmstudio(self):
        url = f"{self.lmstudio_cfg.get('url', 'http://localhost:1234').rstrip('/')}/api/v0/models"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                return [m for m in json.loads(r.read()).get("data", []) if isinstance(m, dict)]
        except (OSError, ValueError, AttributeError) as e:
            raise MoteurIndisponible("LM Studio injoignable : démarrez son serveur local "
                                     "(onglet Developer > Start Server, ou « lms server start »).") from e

    def _lmstudio_requete(self, system, messages, max_tokens, schema=None, stream=False, arrets=()):
        """Envoie la requête à LM Studio et renvoie la réponse HTTP ouverte."""
        cfg = self.lmstudio_cfg
        body = {
            # modèle de config.toml : aucun aller-retour de plus ; sinon celui qui est chargé (liste en cache)
            "model": cfg.get("modele") or self._lmstudio_modele().get("id"),
            "messages": [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens,
            "temperature": cfg.get("temperature", 0.8),
            "stream": stream,
        }
        if stream:
            body["stream_options"] = {"include_usage": True}  # tokens comptés dans le dernier morceau
        if schema:
            # LM Studio contraint la sortie à ce schéma JSON
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "fiche", "strict": True, "schema": schema}}
        if arrets:
            body["stop"] = list(arrets)  # la génération s'arrête net sur l'un de ces textes
        if cfg.get("reflexion") is False:
            body["reasoning_effort"] = "none"  # coupe le mode réflexion, qui sinon mange tout max_tokens
        req = urllib.request.Request(f"{cfg.get('url', 'http://localhost:1234').rstrip('/')}/v1/chat/completions",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=cfg.get("delai_max", 180))
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise MoteurIndisponible(f"LM Studio a renvoyé une erreur : {detail[:200]}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if self._delai_depasse(e):
                raise MoteurIndisponible(self._message_lecture("LM Studio", TimeoutError())) from e
            raise MoteurIndisponible("LM Studio injoignable : démarrez son serveur local "
                                     "(onglet Developer > Start Server, ou « lms server start »).") from e
