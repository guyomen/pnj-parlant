from pnj_parlant.texte import chiffres_en_lettres, locuteur, nettoyer, phrases


class TestNettoyer:
    def test_retire_didascalies_markdown_et_emojis(self):
        assert nettoyer("*Il rit.* **Bonjour** _toi_ ! 🍺") == "Bonjour toi !"

    def test_garde_les_parentheses_pour_le_narrateur(self):
        assert nettoyer("(Il sourit.)   Entrez.") == "(Il sourit.) Entrez."


class TestChiffresEnLettres:
    def test_entiers_et_ordinaux(self):
        assert chiffres_en_lettres("12 pièces") == "douze pièces"
        assert chiffres_en_lettres("le 1er jour") == "le premier jour"

    def test_decimales(self):
        assert chiffres_en_lettres("2,5") == "deux virgule cinq"
        assert chiffres_en_lettres("2,05") == "deux virgule zéro cinq"

    def test_milliers_separes_par_une_espace(self):
        assert chiffres_en_lettres("1 000 écus") == "mille écus"


def decouper(texte, taille=7):
    """Simule l'arrivée du texte en petits morceaux, comme le modèle l'écrit."""
    return list(phrases(texte[i:i + taille] for i in range(0, len(texte), taille)))


class TestPhrases:
    def test_regroupe_les_phrases_trop_courtes(self):
        # « Ah ! » seul ferait un blanc entre deux sons : il attend la phrase suivante
        assert decouper("Ah ! Tu cherches le vieux pont du nord, voyageur ? Il est loin.") == [
            "Ah ! Tu cherches le vieux pont du nord, voyageur ? ", "Il est loin."]

    def test_ne_coupe_pas_une_description_entre_parentheses(self):
        texte = "(Il se gratte la tête. Puis il sourit largement.) Bienvenue voyageur, que puis-je pour toi ? Voilà."
        assert decouper(texte)[0] == "(Il se gratte la tête. Puis il sourit largement.) "

    def test_ne_coupe_pas_une_didascalie_entre_asterisques(self):
        texte = "*Il se gratte la tête. Puis il sourit largement.* Bienvenue, que veux-tu ? Rien."
        assert decouper(texte)[0].endswith("que veux-tu ? ")

    def test_rend_le_reste_a_la_fin(self):
        assert decouper("Court.") == ["Court."]
        assert decouper("") == []


class TestLocuteur:
    NOMS = ["Ysolde la Rousse", "Brom", "Voyageur"]

    def test_reconnait_le_nom_complet_ou_le_premier_mot(self):
        assert locuteur("Ysolde : (Elle rit.) Oui !", self.NOMS) == ("Ysolde la Rousse", "(Elle rit.) Oui !")
        assert locuteur("Ysolde la Rousse: Ha.", self.NOMS) == ("Ysolde la Rousse", "Ha.")
        assert locuteur("Brom : Tais-toi.", self.NOMS) == ("Brom", "Tais-toi.")

    def test_ignore_les_deux_points_ordinaires(self):
        for phrase in ["Écoute bien : je ne sais rien.", "Dis, Brom : ça va ?", "Bonjour."]:
            assert locuteur(phrase, self.NOMS) == (None, phrase)
