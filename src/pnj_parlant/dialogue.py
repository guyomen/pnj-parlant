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


def consignes(npc, monde="", presents=()):
    """Prompt système du PNJ : sa fiche, l'univers connu de tous, les autres PNJ présents.
    Jamais les notes du MJ (elles peuvent contenir l'intrigue), ni le secret des autres PNJ."""
    infos = "\n".join(f"- {c}" for c in npc.get("connaissances", []))
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
- Tes réponses sont LUES À VOIX HAUTE : 1 à 3 phrases courtes, langage parlé.
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


def repliques(morceaux, nom, presents=()):
    """Phrases de la réponse du PNJ `nom`, nettoyées et prêtes à être lues, au fil de l'écriture du modèle.
    S'arrête si le modèle se met à écrire la réplique d'un autre (« Brom : … », « Voyageur : … »)."""
    autres = [p["nom"] for p in presents] + AUTRES_LOCUTEURS
    for phrase in texte.phrases(texte.sans_autres_locuteurs(morceaux, nom, autres)):
        phrase = texte.nettoyer(phrase)
        if phrase:
            yield phrase
