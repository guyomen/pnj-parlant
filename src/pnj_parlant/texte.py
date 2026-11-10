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


# « Nom : » en tête de phrase : le modèle annonce qui parle (lui-même, un autre PNJ ou le voyageur)
ETIQUETTE = re.compile(r"^\s*([^:.!?()]{1,40}?)\s*:\s*")


def locuteur(phrase, noms):
    """(nom annoncé en tête de phrase parmi `noms`, ou None ; phrase sans cette étiquette).
    « Ysolde : » désigne « Ysolde la Rousse » (premier mot du nom)."""
    m = ETIQUETTE.match(phrase)
    if not m:
        return None, phrase
    etiquette = m[1].strip().lower()
    nom = next((n for n in noms if n and etiquette in (n.lower(), n.lower().split()[0])), None)
    return nom, phrase[m.end():] if nom else phrase
