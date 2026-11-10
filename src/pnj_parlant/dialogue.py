"""
Dialogue avec un ou plusieurs PNJ : consignes du PNJ, mise en scène de la conversation, découpage de
sa réponse en phrases prêtes à être lues.

Le serveur ne garde rien : le navigateur envoie toute la scène à chaque réplique,
    [{"speaker": nom du PNJ, ou None pour le joueur, "content": ...}, ...]
salutations comprises. Chaque PNJ y voit ses répliques comme les siennes (rôle « assistant ») et celles
des autres comme des paroles entendues (rôle « user »), précédées du nom de leur auteur quand ils sont
plusieurs.
"""
from . import texte

VOYAGEUR = "Voyageur"


PHRASES_MAX = 3  # par réplique, réglable dans [dialogue] phrases_max de config.toml


def consignes(npc, monde="", presents=(), phrases_max=PHRASES_MAX):
    """Prompt système du PNJ : sa fiche, l'univers connu de tous, les autres PNJ présents.
    Jamais les notes du MJ (elles peuvent contenir l'intrigue), ni le secret des autres PNJ."""
    infos = "\n".join(f"- {c}" for c in npc.get("connaissances", []))
    longueur = "une phrase courte" if phrases_max == 1 else f"1 à {phrases_max} phrases courtes"
    scene = ""
    if presents:
        autres = "\n".join(f"- {p.get('nom')}, {p.get('metier')}. {p.get('apparence', '')}" for p in presents)
        scene = f"""
- Tu n'es pas seul avec le voyageur. Sont aussi présents :
{autres}
  Tu entends leurs paroles précédées de leur nom (« {presents[0].get('nom')} : … ») et celles du voyageur
  précédées de « {VOYAGEUR} : ». Tu peux t'adresser à eux, les taquiner ou les contredire, selon ta personnalité.
  Mais tu n'écris que TA réplique : jamais celle d'un autre, jamais un nom suivi de deux-points.
  Si tu poses une question à quelqu'un, arrête-toi là : il répondra lui-même."""
    univers = (f"""Ce que tout habitant sait du monde :
<univers>
{monde}
</univers>
""" if monde else "")
    return f"""{univers}Tu es {npc.get('nom')}, {npc.get('metier')}, dans un monde médiéval-fantastique.
Apparence : {npc.get('apparence')}
Personnalité : {npc.get('personnalite')} Humeur du jour : {npc.get('humeur')}.
Ce que tu sais et peux révéler :
{infos}
Ton secret (ne le révèle que si le voyageur gagne vraiment ta confiance ou te paie bien) : {npc.get('secret')}

Règles :
- Tes réponses sont LUES À VOIX HAUTE : {longueur}, langage parlé.
- Aucun markdown, aucun emoji, aucune action entre astérisques.
- Reste toujours dans ton personnage. Tu ne sais rien du monde réel moderne.
- Ne cite aucun lieu, personnage, faction ou événement absent de l'univers ci-dessus ou de ta fiche.
  Si on te demande quelque chose que tu ignores, dis-le à ta manière ou reste vague, sans inventer de nom propre.
- Si c'est ton métier, tu peux proposer des marchandises avec des prix en pièces d'or ou d'argent.{scene}"""


def nettoyer_historique(history, maximum):
    """Les `maximum` derniers messages valides de la scène."""
    return [m for m in history or [] if isinstance(m, dict) and str(m.get("content") or "").strip()][-maximum:]


def messages(nom, history, presents=()):
    """La scène vue par le PNJ `nom`, au format des API de dialogue (rôles user / assistant alternés,
    en commençant par « user »)."""
    # À plusieurs (ou si un PNJ vient de quitter la scène), chacun doit savoir qui a parlé
    groupe = bool(presents) or any(m.get("speaker") not in (None, nom) for m in history)
    # L'API attend un premier message « user » : on met en scène l'arrivée du joueur.
    resultat = [{"role": "user", "content": "(Un voyageur s'approche.)"}]
    for m in history:
        contenu = str(m["content"]).strip()[:1000]
        if m.get("speaker") == nom:
            role = "assistant"
        else:
            role = "user"
            if groupe:
                contenu = f"{m.get('speaker') or VOYAGEUR} : {contenu}"
        if resultat[-1]["role"] == role:  # fusionne les messages consécutifs du même rôle
            resultat[-1]["content"] += "\n" + contenu
        else:
            resultat.append({"role": role, "content": contenu})
    if resultat[-1]["role"] == "assistant":  # le PNJ reprend la parole après lui-même
        resultat.append({"role": "user", "content": "(Le voyageur attend la suite.)"})
    if groupe:  # rappel juste avant la réponse : c'est là qu'un petit modèle y fait le plus attention
        resultat[-1]["content"] += f"\n({RAPPEL.format(nom=nom)})"
    return resultat


RAPPEL = "Réponds seulement en tant que {nom}, sans écrire de nom suivi de deux-points."
# Étiquettes qui, en début de phrase, annoncent que le modèle fait parler quelqu'un d'autre
AUTRES_LOCUTEURS = [VOYAGEUR, "Le voyageur", "Nom"]


def arrets(nom, presents=()):
    """Séquences d'arrêt pour le modèle (option `stop` d'Ollama, `stop_sequences` de Claude) : la génération
    s'arrête net dès que le modèle annonce un autre locuteur (« Léonard : », « Voyageur: », « Nom : »),
    sans attendre qu'il ait écrit toute la réplique de l'autre. Le filtre de repliques() reste le filet de
    sécurité pour les variantes que ces textes exacts ne couvrent pas."""
    miennes = {e.lower() for e in texte.etiquettes([nom])}
    autres = [e for e in texte.etiquettes([p["nom"] for p in presents] + AUTRES_LOCUTEURS)
              if e.lower() not in miennes]  # deux PNJ peuvent partager un prénom
    return [f"{e}{deux_points}" for e in autres for deux_points in (" :", ":")]


def repliques(morceaux, nom, presents=(), phrases_max=PHRASES_MAX):
    """Phrases de la réponse du PNJ `nom`, nettoyées et prêtes à être lues, au fil de l'écriture du modèle.
    S'arrête si le modèle se met à écrire la réplique d'un autre (« Brom : … », « Voyageur : … »), ou après
    `phrases_max` phrases : un petit modèle ne respecte pas toujours la longueur demandée."""
    autres = [p["nom"] for p in presents] + AUTRES_LOCUTEURS
    try:
        sien = texte.sans_autres_locuteurs(morceaux, nom, autres)  # sans les répliques des autres
        for phrase in texte.phrases(texte.limiter_phrases(sien, phrases_max)):
            phrase = texte.nettoyer(phrase)
            if phrase:
                yield phrase
    finally:
        if hasattr(morceaux, "close"):
            morceaux.close()  # réponse coupée : on ferme la connexion, le modèle arrête d'écrire
