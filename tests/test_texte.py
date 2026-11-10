from pnj_parlant.texte import chiffres_en_lettres, nettoyer, phrases, sans_autres_locuteurs


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


class TestSansAutresLocuteurs:
    AUTRES = ["Léonard le Sage", "Voyageur", "Le voyageur", "Nom"]

    def filtrer(self, texte, moi="Berthe la joyeuse", taille=5):
        """Texte gardé, quelle que soit la façon dont le modèle le découpe en morceaux."""
        resultats = {"".join(sans_autres_locuteurs([texte], moi, self.AUTRES))}
        for t in (1, 3, taille):
            morceaux = (texte[i:i + t] for i in range(0, len(texte), t))
            resultats.add("".join(sans_autres_locuteurs(morceaux, moi, self.AUTRES)))
        assert len(resultats) == 1, resultats
        return resultats.pop()

    def test_cas_reel_nom_recopie_puis_replique_d_un_autre_en_pleine_phrase(self):
        texte = ("Je vais très bien, merci. Et toi-même ? (À Léonard) Et pour toi, Léonard ? Toujours à rechercher "
                 "des ingrédients rares pour tes potions ? Nom : Léonard le Sage Léonard le Sage : En effet, Berthe.")
        assert self.filtrer(texte) == ("Je vais très bien, merci. Et toi-même ? (À Léonard) Et pour toi, Léonard ? "
                                       "Toujours à rechercher des ingrédients rares pour tes potions ? ")

    def test_s_arrete_sur_le_premier_mot_du_nom_ou_le_voyageur(self):
        assert self.filtrer("Bien sûr.\nLéonard : Mensonge !") == "Bien sûr.\n"
        assert self.filtrer("Une bière ? Voyageur : Oui.") == "Une bière ? "
        assert self.filtrer("léonard : coupé dès le début") == ""

    def test_retire_sa_propre_etiquette(self):
        assert self.filtrer("Berthe : Bonjour ! Berthe la joyeuse : Encore moi.") == "Bonjour ! Encore moi."

    def test_ignore_les_deux_points_ordinaires(self):
        for texte in ["Écoute bien : je ne sais rien.", "Dis-le à Léonard : il saura.", "Le prix : 3 pièces."]:
            assert self.filtrer(texte) == texte
