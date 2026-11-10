"""
Traitement du texte des répliques : nettoyage avant la synthèse vocale, nombres en toutes lettres,
découpage en phrases au fil de l'écriture du modèle, repérage de « Nom : » en tête de réplique.
"""
import re

from num2words import num2words


def nettoyer(text):
    """Retire didascalies *...*, markdown et emojis avant la synthèse vocale.
    Le texte entre parenthèses est gardé : le navigateur le fait lire par la voix du narrateur."""
    text = re.sub(r"\*[^*]*\*", "", text)
    text = re.sub(r"[#_`>]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def chiffres_en_lettres(text):
    """Écrit les nombres en toutes lettres (« 12 » → « douze »), que la synthèse vocale lit mal en chiffres."""
    def ordinal(m):
        return num2words(int(m[1]), lang="fr", to="ordinal")  # 1er → premier, 2e → deuxième

    def nombre(m):
        entier, decimales = m[1], m[2]
        if len(entier) > 15:  # trop long pour un nombre : chiffre par chiffre
            return " ".join(num2words(int(c), lang="fr") for c in entier)
        mot = num2words(int(entier), lang="fr")
        if decimales:
            if decimales.startswith("0"):  # 2,05 → deux virgule zéro cinq
                mot += " virgule " + " ".join(num2words(int(c), lang="fr") for c in decimales)
            else:
                mot += " virgule " + num2words(int(decimales), lang="fr")
        return mot

    text = re.sub(r"\b(\d+)\s?(er|re|ère|ere|e|è|ème|eme)\b", ordinal, text)
    text = re.sub(r"(?<=\d)[\u202f\u00a0 ](?=\d{3}\b)", "", text)  # « 1 000 » → « 1000 »
    return re.sub(r"(\d+)(?:[,.](\d+))?", nombre, text)


# Fin de phrase : ponctuation, éventuels guillemets ou parenthèse fermants, puis une espace
FIN_DE_PHRASE = re.compile(r"[.!?…]+[»”\"')]*\s+")
PHRASE_MIN = 40  # caractères : « Ah ! » attend la phrase suivante, pour éviter un blanc entre deux sons


def phrases(morceaux):
    """Regroupe en phrases complètes le texte qui arrive morceau par morceau,
    pour que chaque phrase soit lue pendant que le modèle écrit la suivante."""
    tampon = ""
    for morceau in morceaux:
        tampon += morceau
        while True:
            # on ne coupe pas au milieu d'une didascalie *...*, que nettoyer() retire en entier,
            # ni d'une description (...), que le navigateur fait lire par la voix du narrateur
            fin = next((m.end() for m in FIN_DE_PHRASE.finditer(tampon)
                        if len(tampon[:m.end()].strip()) >= PHRASE_MIN
                        and tampon[:m.end()].count("*") % 2 == 0
                        and tampon[:m.end()].count("(") <= tampon[:m.end()].count(")")), None)
            if fin is None:
                break
            yield tampon[:fin]
            tampon = tampon[fin:]
    if tampon.strip():
        yield tampon


# --- Qui parle ? -------------------------------------------------------------------
# À plusieurs, un petit modèle a tendance à écrire la suite de la scène à la place des autres
# (« … tes potions ? Léonard : En effet. »), voire à recopier le format des consignes (« Nom : »).
FIN = r"(?:[.!?…]+[»”\"')]*\s+|\n)"                        # fin de phrase ou de ligne, avant une étiquette
FIN_EMISE = re.compile(r"(?:[.!?…]+[»”\"')]*\s*|\n\s*)$")  # le texte déjà envoyé finit une phrase


def etiquettes(noms):
    """Façons d'annoncer chaque nom : complet, ou premier mot (« Ysolde » pour « Ysolde la Rousse »)."""
    variantes = {v for n in noms if n for v in (n, n.split()[0]) if len(v) >= 3}
    return sorted(variantes, key=len, reverse=True)  # les plus longues d'abord


def sans_autres_locuteurs(morceaux, moi, autres):
    """Le texte du PNJ `moi`, morceau par morceau, débarrassé des étiquettes à son nom (« Berthe : ») et
    arrêté dès qu'il annonce un autre locuteur (« Léonard : », « Voyageur : », « Nom : »).
    Une étiquette n'est reconnue qu'en début de réponse, de ligne ou de phrase : « Dis-le à Léonard : il
    saura » reste intact."""
    miennes = {e.lower() for e in etiquettes([moi])}
    toutes = etiquettes([moi, *autres])
    motif = "|".join(map(re.escape, toutes))
    au_debut = re.compile(rf"\s*({motif})\s*:\s*", re.IGNORECASE)
    apres_une_fin = re.compile(rf"{FIN}\s*({motif})\s*:\s*", re.IGNORECASE)
    garde = max(map(len, toutes), default=0) + 8  # une étiquette peut arriver en plusieurs morceaux

    tampon, debut, flux = "", True, iter(morceaux)  # debut : le tampon commence une phrase
    while True:
        morceau = next(flux, None)
        tampon += morceau or ""
        while True:
            m = (au_debut.match(tampon) if debut else None) or apres_une_fin.search(tampon)
            if m is None:
                break
            a_moi = m[1].lower() in miennes
            if a_moi and m.end() == len(tampon) and morceau is not None:
                break  # sa propre étiquette, peut-être suivie d'espaces encore à venir : on attend la suite
            if m.start(1) > 0:
                yield tampon[:m.start(1)]  # ce qui précède l'étiquette
            if not a_moi:
                return  # le modèle fait parler quelqu'un d'autre : la réplique s'arrête là
            tampon, debut = tampon[m.end():], False  # sa propre étiquette : retirée
        if morceau is None:  # fin du flux
            if tampon:
                yield tampon
            return
        if len(tampon) > garde:  # on garde la fin, qui pourrait être le début d'une étiquette
            envoye, tampon = tampon[:-garde], tampon[-garde:]
            debut = bool(FIN_EMISE.search(envoye))
            yield envoye
