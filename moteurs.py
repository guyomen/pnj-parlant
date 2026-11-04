"""
Moteurs de langage : Claude (API Anthropic) ou modèle local (Ollama, dans Docker).

Le choix se fait dans la section [moteurs] de config.toml, séparément pour la création
des fiches et pour les dialogues :
    creation = "claude"   # meilleure inventivité, demande le réseau
    dialogue = "local"    # fonctionne sans réseau
"""
import json
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
        # Clé de config.toml ; si elle est vide, le SDK lit ANTHROPIC_API_KEY dans l'environnement.
        self.client = anthropic.Anthropic(api_key=self.claude_cfg.get("cle_api") or None)

    def description(self):
        nom = lambda m: self.claude_cfg["modele"] if m == "claude" else f"local : {self.local_cfg.get('modele')}"
        return {"creation": nom(self.choix["creation"]), "dialogue": nom(self.choix["dialogue"])}

    # --- Points d'entrée ------------------------------------------------------
    def fiche(self, system, demande, schema):
        """Texte JSON de la fiche d'un PNJ, conforme à `schema`."""
        messages = [{"role": "user", "content": demande}]
        if self.choix["creation"] == "local":
            return self._local(system, messages, self.local_cfg["generation"]["max_tokens"], schema)
        cfg = self.claude_cfg["generation"]
        return self._claude(system, messages, cfg["max_tokens"],
                            {"effort": cfg["effort"], "format": {"type": "json_schema", "schema": schema}})

    def replique(self, system, messages):
        """Réplique du PNJ dans le dialogue, morceau de texte par morceau de texte (générateur),
        pour commencer à la lire avant qu'elle soit finie.
        Lève MoteurIndisponible dès l'appel si le moteur ne répond pas ; pendant la lecture du
        générateur si la connexion se coupe en cours de route."""
        if self.choix["dialogue"] == "local":
            return self._local_flux(system, messages, self.local_cfg["dialogue"]["max_tokens"])
        cfg = self.claude_cfg["dialogue"]
        return self._claude_flux(system, messages, cfg["max_tokens"], {"effort": cfg["effort"]})

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

    def _claude_flux(self, system, messages, max_tokens, output_config):
        try:  # la requête part ici : une erreur de connexion est levée avant de renvoyer le générateur
            flux = self.client.messages.create(model=self.claude_cfg["modele"], max_tokens=max_tokens,
                                               system=system, messages=messages, output_config=output_config,
                                               stream=True)
        except anthropic.APIConnectionError as e:
            raise MoteurIndisponible("Pas de connexion à Claude.") from e
        except anthropic.APIStatusError as e:
            raise MoteurIndisponible(f"Claude a refusé la requête ({e.status_code}).") from e

        def morceaux():
            try:
                for event in flux:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield event.delta.text
                    elif event.type == "message_delta" and event.delta.stop_reason == "max_tokens":
                        print(f"[claude] réponse coupée à max_tokens={max_tokens}")
            except anthropic.APIError as e:
                raise MoteurIndisponible("La connexion à Claude s'est interrompue.") from e
        return morceaux()

    # --- Modèle local (API d'Ollama) ------------------------------------------
    def _local(self, system, messages, max_tokens, schema=None):
        with self._ollama(system, messages, max_tokens, schema, stream=False) as r:
            data = json.loads(r.read())
        return data.get("message", {}).get("content", "")

    def _local_flux(self, system, messages, max_tokens):
        r = self._ollama(system, messages, max_tokens, stream=True)

        def morceaux():
            # Ollama envoie une ligne JSON par morceau de texte, jusqu'à "done": true
            try:
                with r:
                    for ligne in r:
                        if ligne.strip():
                            yield json.loads(ligne).get("message", {}).get("content", "")
            except (OSError, ValueError) as e:  # coupure réseau, délai dépassé, ligne illisible
                raise MoteurIndisponible("Le modèle local s'est interrompu.") from e
        return morceaux()

    def _ollama(self, system, messages, max_tokens, schema=None, stream=False):
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
