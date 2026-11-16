"""
Configuration et état du serveur, réglages à chaud de la page Options, droits de cet appareil.

    GET  /api/config                  moteurs utilisés, voix, reconnaissance locale, modèles Ollama
    GET  /api/etat                    carte graphique et Ollama
    GET  /api/sante                   ce qui ne marche pas alors que le serveur tourne (bandeau des pages)
    GET|PUT /api/reglages             réglages du serveur de la page Options (écrits dans config.toml, à chaud)
    POST /api/reglages/verifier       vérifie le mot de passe du MJ
    GET  /api/acces                   droits de cet appareil sur l'univers {mj, protege, local}
"""
from flask import Blueprint, jsonify

from .. import reglages, systeme
from .acces import depuis_le_serveur, droits, garde, mdp_en_tete, protege, trop_d_essais
from .entrees import contexte, corps, erreur

bp = Blueprint("options", __name__)


@bp.get("/api/config")
def config_get():
    ctx = contexte()
    m = ctx.moteurs
    installes = m.modeles_locaux() if "local" in m.choix.values() else []
    return jsonify({"moteurs": m.description(), "tts": ctx.tts.nom if ctx.tts.catalogue() else None,
                    "stt_local": ctx.reconnaissance.disponible(), "modeles_locaux": installes,
                    "intervention": ctx.intervention, "pnj_max": ctx.pnj_max,
                    "modele_local": m.modele_local_installe(installes),
                    "modele_dialogue": modele_dialogue(m, installes),
                    "contexte_max": m.contexte_max(),
                    "portraits": ctx.portraits.nom if ctx.portraits.disponible() else None})


@bp.get("/api/etat")
def etat():
    """État de la machine pour la page Options : GPU, et Ollama ou LM Studio s'ils servent."""
    ctx = contexte()
    ollama = lmstudio = None
    if "local" in ctx.moteurs.choix.values():
        ollama = systeme.etat_ollama(ctx.moteurs.local_cfg.get("url", "http://localhost:11434"))
    if "lmstudio" in ctx.moteurs.choix.values():
        lmstudio = ctx.moteurs.etat_lmstudio()
    return jsonify({"gpu": systeme.etat_gpu(), "ollama": ollama, "lmstudio": lmstudio})


def modele_dialogue(m, installes):
    """Choix du modèle de dialogue depuis la vue Partie : None avec Claude ; sinon {moteur, cle (réglage du
    CATALOGUE), valeur (modèle en cours ; LM Studio : "" = le modèle chargé), modeles (installés), modifiable
    (cet appareil peut changer les réglages : mot de passe du MJ s'il existe, sinon PC du serveur)}."""
    moteur = m.choix.get("dialogue")
    if moteur == "local":
        valeur, modeles = m.modele_local_installe(installes), [x["nom"] for x in installes]
    elif moteur == "lmstudio":
        valeur, modeles = m.lmstudio_cfg.get("modele") or "", m.modeles_lmstudio()
    else:
        return None
    return {"moteur": moteur, "cle": f"{moteur}.modele", "valeur": valeur, "modeles": modeles,
            "modifiable": protege() or depuis_le_serveur()}


def reglages_pour_la_page():
    ctx = contexte()
    suggestions = {}
    if "local" in ctx.moteurs.choix.values():  # modèles installés dans Ollama (seulement s'il sert)
        suggestions["local.modele"] = [m["nom"] for m in ctx.moteurs.modeles_locaux()]
    return {"groupes": reglages.pour_la_page(ctx.cfg.reglages, suggestions),
            "protege": bool(reglages.lire(ctx.cfg.reglages, "serveur.mot_de_passe_mj")),
            "local": depuis_le_serveur(), "fichier": ctx.cfg.fichier.name if ctx.cfg.fichier else None}


@bp.get("/api/acces")
def acces():
    """Droits de cet appareil sur l'univers (mot de passe éventuel dans l'en-tête) : {mj, protege, local}."""
    etat_, attente = droits(mdp_en_tete(), True)
    if etat_ == "verrou":
        return trop_d_essais(attente)
    return jsonify({"mj": etat_ == "ok", "protege": protege(), "local": depuis_le_serveur()})


@bp.get("/api/sante")
def sante():
    """Problèmes à afficher dans le bandeau des pages (vide si tout va bien)."""
    return jsonify({"problemes": contexte().problemes_recents()})


@bp.get("/api/reglages")
def reglages_get():
    """Réglages du serveur pour la page Options (secrets masqués) et droits de cet appareil."""
    return jsonify(reglages_pour_la_page())


@bp.post("/api/reglages/verifier")
def reglages_verifier():
    mdp = corps().get("mot_de_passe")
    return garde(mdp if isinstance(mdp, str) else None, False) or jsonify({"ok": True})


@bp.put("/api/reglages")
def reglages_put():
    """{changements: {clé: valeur}} ; mot de passe du MJ dans l'en-tête X-Mot-De-Passe-MJ. Écrit config.toml et
    applique aussitôt ; renvoie les réglages et `redemarrage` (libellés qui attendent un redémarrage)."""
    refuse = garde(mdp_en_tete(), False, demander=True)
    if refuse:
        return refuse
    try:
        changements = corps().get("changements")
        redemarrage = contexte().appliquer_reglages(reglages.valider(changements))
    except ValueError as e:
        return erreur(str(e), 400)
    except OSError as e:
        return erreur(f"config.toml n'a pas pu être écrit : {e}", 500)
    return jsonify({**reglages_pour_la_page(), "redemarrage": redemarrage})
