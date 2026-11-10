from pnj_parlant import dialogue

YSOLDE = {"nom": "Ysolde", "metier": "aubergiste", "apparence": "Trapue.", "secret": "Elle dilue la bière.",
          "connaissances": ["Le pont est gardé."]}
BROM = {"nom": "Brom", "metier": "forgeron", "apparence": "Immense.", "secret": "Il a volé une épée."}


def entree(speaker, content):
    return {"speaker": speaker, "content": content}


class TestMessages:
    def test_seul_avec_le_joueur_sans_prefixes(self):
        history = [entree("Ysolde", "Bienvenue !"), entree(None, "Une bière.")]
        assert dialogue.messages("Ysolde", history) == [
            {"role": "user", "content": "(Un voyageur s'approche.)"},
            {"role": "assistant", "content": "Bienvenue !"},
            {"role": "user", "content": "Une bière."},
        ]

    def test_a_plusieurs_chacun_sait_qui_parle(self):
        history = [entree("Ysolde", "Bienvenue !"), entree("Brom", "Salut."), entree(None, "Brom, ça va ?")]
        msgs = dialogue.messages("Brom", history, presents=[YSOLDE])
        assert msgs == [
            {"role": "user", "content": "(Un voyageur s'approche.)\nYsolde : Bienvenue !"},
            {"role": "assistant", "content": "Salut."},
            {"role": "user", "content": "Voyageur : Brom, ça va ?\n(Réponds seulement en tant que Brom, "
                                        "sans écrire de nom suivi de deux-points.)"},
        ]

    def test_seul_pas_de_rappel(self):
        msgs = dialogue.messages("Ysolde", [entree("Ysolde", "Bienvenue !"), entree(None, "Salut.")])
        assert "Réponds seulement" not in msgs[-1]["content"]

    def test_les_roles_alternent_et_commencent_par_user(self):
        history = [entree("Ysolde", "A."), entree("Brom", "B."), entree(None, "C."), entree("Brom", "D.")]
        msgs = dialogue.messages("Ysolde", history, presents=[BROM])
        roles = [m["role"] for m in msgs]
        assert roles[0] == "user"
        assert all(a != b for a, b in zip(roles, roles[1:]))

    def test_le_pnj_qui_reprend_la_parole_apres_lui_meme(self):
        msgs = dialogue.messages("Ysolde", [entree("Ysolde", "Bienvenue !")])
        assert msgs[-1] == {"role": "user", "content": "(Le voyageur attend la suite.)"}

    def test_un_pnj_parti_reste_nomme(self):
        # Brom a quitté la scène : Ysolde est seule, mais doit savoir que ces paroles étaient les siennes
        msgs = dialogue.messages("Ysolde", [entree("Brom", "Je m'en vais."), entree(None, "Et toi ?")])
        assert "Brom : Je m'en vais.\nVoyageur : Et toi ?\n" in msgs[-1]["content"]


class TestArrets:
    def test_les_autres_le_voyageur_et_le_format_des_consignes(self):
        arrets = dialogue.arrets("Berthe la joyeuse", [{"nom": "Léonard le Sage"}])
        for attendu in ["Léonard le Sage :", "Léonard le Sage:", "Léonard :", "Léonard:",
                        "Voyageur :", "Le voyageur :", "Nom :", "Nom:"]:
            assert attendu in arrets
        assert not any(a.startswith("Berthe") for a in arrets)  # jamais sa propre étiquette

    def test_prenom_partage_avec_un_autre_pnj(self):
        arrets = dialogue.arrets("Jean le Meunier", [{"nom": "Jean le Forgeron"}])
        assert "Jean le Forgeron :" in arrets and "Jean :" not in arrets

    def test_seul_avec_le_voyageur(self):
        assert dialogue.arrets("Ysolde") == ["Le voyageur :", "Le voyageur:", "Voyageur :", "Voyageur:", "Nom :", "Nom:"]


def test_nettoyer_historique_garde_les_derniers_messages_valides():
    history = [entree(None, "a"), "pas un dict", entree(None, "  "), entree("X", "b"), entree(None, "c")]
    assert dialogue.nettoyer_historique(history, 2) == [entree("X", "b"), entree(None, "c")]
    assert dialogue.nettoyer_historique(None, 5) == []


class TestConsignes:
    def test_fiche_et_univers(self):
        system = dialogue.consignes(YSOLDE, monde="Le royaume de Valmer.")
        assert "Tu es Ysolde, aubergiste" in system
        assert "Le royaume de Valmer." in system
        assert "Elle dilue la bière." in system
        assert "pas seul" not in system

    def test_presente_les_autres_sans_leur_secret(self):
        system = dialogue.consignes(YSOLDE, presents=[BROM])
        assert "Brom, forgeron. Immense." in system
        assert BROM["secret"] not in system


class TestRepliques:
    def test_phrases_nettoyees(self):
        assert list(dialogue.repliques(iter(["*Rit.* Bonjour ", "à toi !"]), "Ysolde")) == ["Bonjour à toi !"]

    def test_retire_son_propre_nom_en_tete(self):
        assert list(dialogue.repliques(iter(["Ysolde : Bonjour."]), "Ysolde")) == ["Bonjour."]

    def test_s_arrete_quand_le_modele_ecrit_pour_un_autre(self):
        texte = "Ce forgeron raconte n'importe quoi, crois-moi.\nBrom : Mensonge !\nYsolde : Si."
        assert list(dialogue.repliques(iter([texte]), "Ysolde", [BROM])) == [
            "Ce forgeron raconte n'importe quoi, crois-moi."]
        texte = "Je te sers une bière tout de suite, voyageur.\nVoyageur : Merci !"
        assert list(dialogue.repliques(iter([texte]), "Ysolde")) == ["Je te sers une bière tout de suite, voyageur."]

    def test_le_format_des_consignes_recopie(self):
        texte = "Et toi, Brom, toujours à la forge du matin au soir ? Nom : Brom Brom : Oui."
        assert list(dialogue.repliques(iter(texte), "Ysolde", [BROM])) == [
            "Et toi, Brom, toujours à la forge du matin au soir ?"]

    def test_ferme_le_flux_du_modele_quand_la_reponse_est_coupee(self):
        ferme = []

        def flux():
            try:
                yield "Bien sûr, voyageur, je te sers tout de suite.\nBrom : Et moi ?"
                yield " Encore du texte que le modèle continue d'écrire."
            finally:
                ferme.append(True)
        assert len(list(dialogue.repliques(flux(), "Ysolde", [BROM]))) == 1
        assert ferme == [True]

    def test_consignes_donnent_un_vrai_nom_en_exemple(self):
        system = dialogue.consignes(YSOLDE, presents=[BROM])
        assert "« Brom : … »" in system and "Nom :" not in system
