"""
Moteurs de langage : Claude (API Anthropic), modèle local (Ollama, dans Docker)
ou modèle local servi par LM Studio (API compatible OpenAI).

Le choix se fait dans la section [moteurs] de config.toml, séparément pour la création
des fiches et pour les dialogues :
    creation = "claude"     # meilleure inventivité, demande le réseau
    dialogue = "local"      # fonctionne sans réseau (Ollama)
    dialogue = "lmstudio"   # fonctionne sans réseau (LM Studio, sans Docker)
"""
import json
import re
import urllib.error
import urllib.request

import anthropic


class MoteurIndisponible(Exception):
    """Le moteur ne répond pas (réseau, Docker arrêté, modèle absent…). Le message est pour le joueur."""


class Moteurs:
    def __init__(self, config):
        self.choix = config.get("moteurs", {"creation": "claude", "dialogue": "claude"})
        self.claude_cfg = config["claude"]
        self.local_cfg = config.get("local", {})
        self.lmstudio_cfg = config.get("lmstudio", {})
        # Clé de config.toml ; si elle est vide, le SDK lit ANTHROPIC_API_KEY dans l'environnement.
        self.client = anthropic.Anthropic(api_key=self.claude_cfg.get("cle_api") or None)

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
        """Modèles installés dans Ollama : [{"nom": ..., "taille": octets}]. Vide si Ollama ne répond pas."""
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

    def choisir_modele_local(self, nom):
        """Change de modèle local jusqu'au redémarrage du serveur (config.toml n'est pas modifié)."""
        if nom not in [x["nom"] for x in self.modeles_locaux()]:
            raise MoteurIndisponible(f"Modèle local « {nom} » absent d'Ollama.")
        self.local_cfg["modele"] = nom

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
        except anthropic.APIConnectionError as e:
            raise MoteurIndisponible("Pas de connexion à Claude.") from e
        except anthropic.APIStatusError as e:
            raise MoteurIndisponible(f"Claude a refusé la requête ({e.status_code}).") from e
        if msg.stop_reason == "max_tokens":
            print(f"[claude] réponse coupée à max_tokens={max_tokens}")
        return "".join(b.text for b in msg.content if b.type == "text")

    def _claude_flux(self, system, messages, max_tokens, output_config, arrets=(), on_usage=None):
        options = {"stop_sequences": list(arrets)} if arrets else {}
        try:  # la requête part ici : une erreur de connexion est levée avant de renvoyer le générateur
            flux = self.client.messages.create(model=self.claude_cfg["modele"], max_tokens=max_tokens,
                                               system=system, messages=messages, output_config=output_config,
                                               stream=True, **options)
        except anthropic.APIConnectionError as e:
            raise MoteurIndisponible("Pas de connexion à Claude.") from e
        except anthropic.APIStatusError as e:
            raise MoteurIndisponible(f"Claude a refusé la requête ({e.status_code}).") from e

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
            except anthropic.APIError as e:
                raise MoteurIndisponible("La connexion à Claude s'est interrompue.") from e
            finally:
                flux.close()  # réponse abandonnée en route (Stop, filtre) : Claude arrête d'écrire
            if on_usage and {"input_tokens", "output_tokens"} <= usage.keys():
                on_usage(usage)
        return morceaux()

    # --- Modèle local (API d'Ollama) ------------------------------------------
    def _local(self, system, messages, max_tokens, schema=None):
        with self._ollama(system, messages, max_tokens, schema, stream=False) as r:
            data = json.loads(r.read())
        return data.get("message", {}).get("content", "")

    def _local_flux(self, system, messages, max_tokens, arrets=(), on_usage=None):
        r = self._ollama(system, messages, max_tokens, stream=True, arrets=arrets)

        def morceaux():
            # Ollama envoie une ligne JSON par morceau de texte, jusqu'à "done": true.
            # Réponse abandonnée en route (Stop, filtre) : fermer la connexion arrête la génération.
            usage = {}
            try:
                with r:
                    for ligne in r:
                        if ligne.strip():
                            data = json.loads(ligne)
                            if data.get("done"):
                                if data.get("prompt_eval_count") is not None:
                                    usage["input_tokens"] = data["prompt_eval_count"]
                                if data.get("eval_count") is not None:
                                    usage["output_tokens"] = data["eval_count"]
                            yield data.get("message", {}).get("content", "")
            except (OSError, ValueError) as e:  # coupure réseau, délai dépassé, ligne illisible
                raise MoteurIndisponible("Le modèle local s'est interrompu.") from e
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
            body["think"] = cfg["reflexion"]  # false : coupe le mode réflexion (Qwen 3…), plus rapide
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
            raise MoteurIndisponible("Modèle local injoignable : lancez-le avec « docker compose up -d ».") from e

    # --- Modèle local (LM Studio, API compatible OpenAI) ----------------------
    def _lmstudio(self, system, messages, max_tokens, schema=None):
        with self._lmstudio_requete(system, messages, max_tokens, schema) as r:
            choix = json.loads(r.read())["choices"][0]
        if choix.get("finish_reason") == "length":
            print(f"[lmstudio] réponse coupée à max_tokens={max_tokens}")
        texte = choix["message"].get("content") or ""
        # Les modèles à réflexion (Qwen 3…) peuvent laisser leur raisonnement dans <think>…</think>
        return re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL).strip()

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
                        if data.get("usage"):
                            usage["input_tokens"] = data["usage"].get("prompt_tokens")
                            usage["output_tokens"] = data["usage"].get("completion_tokens")
                        for choix in data.get("choices", []):
                            if choix.get("finish_reason") == "length":
                                print(f"[lmstudio] réponse coupée à max_tokens={max_tokens}")
                            if choix.get("delta", {}).get("content"):
                                yield choix["delta"]["content"]
            except (OSError, ValueError) as e:  # coupure réseau, délai dépassé, ligne illisible
                raise MoteurIndisponible("LM Studio s'est interrompu.") from e
            if on_usage and usage and None not in usage.values():
                on_usage(usage)
        return morceaux()

    def _lmstudio_modele(self):
        """Modèle chargé dans LM Studio (fiche de /api/v0/models), celui de config.toml s'il est renseigné."""
        cfg = self.lmstudio_cfg
        url = f"{cfg.get('url', 'http://localhost:1234').rstrip('/')}/api/v0/models"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                modeles = json.loads(r.read()).get("data", [])
        except (OSError, ValueError) as e:
            raise MoteurIndisponible("LM Studio injoignable : démarrez son serveur local "
                                     "(onglet Developer > Start Server, ou « lms server start »).") from e
        if cfg.get("modele"):
            return next((m for m in modeles if m["id"] == cfg["modele"]), {"id": cfg["modele"]})
        # /api/v0/models (propre à LM Studio) indique le type et l'état de chaque modèle, contrairement à /v1/models
        charges = [m for m in modeles if m.get("state") == "loaded" and m.get("type") in ("llm", "vlm")]
        if not charges:
            raise MoteurIndisponible("Aucun modèle chargé dans LM Studio : chargez-en un, ou renseignez "
                                     "`modele` dans la section [lmstudio] de config.toml.")
        return charges[0]

    def _lmstudio_requete(self, system, messages, max_tokens, schema=None, stream=False, arrets=()):
        """Envoie la requête à LM Studio et renvoie la réponse HTTP ouverte."""
        cfg = self.lmstudio_cfg
        body = {
            "model": self._lmstudio_modele()["id"],
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
            raise MoteurIndisponible("LM Studio injoignable : démarrez son serveur local "
                                     "(onglet Developer > Start Server, ou « lms server start »).") from e
