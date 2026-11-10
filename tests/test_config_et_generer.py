import pytest

from pnj_parlant import config
from pnj_parlant.generer import generer
from pnj_parlant.moteurs import MoteurIndisponible


class TestConfig:
    def test_introuvable(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PNJ_CONFIG", raising=False)
        with pytest.raises(config.ConfigIntrouvable):
            config.charger()

    def test_chemins_relatifs_au_dossier_de_config(self, tmp_path, monkeypatch):
        fichier = tmp_path / "jeu" / "config.toml"
        fichier.parent.mkdir()
        fichier.write_text('[banque]\ndossier = "pnj"\n', encoding="utf-8")
        monkeypatch.setenv("PNJ_CONFIG", str(fichier))
        cfg = config.charger()
        assert cfg.section("banque") == {"dossier": "pnj"}
        assert cfg.section("absente") == {}
        assert cfg.chemin("pnj") == fichier.parent.resolve() / "pnj"


class TestGenerer:
    def test_remplit_la_banque(self, ctx):
        messages = []
        assert generer(ctx, 3, "aubergiste", afficher=messages.append) == 3
        assert len(ctx.banque.liste()) == 3
        npc = ctx.banque.lire(ctx.banque.liste()[0]["id"])
        assert npc["voix"]["moteur"] == "faux"
        assert "Ysolde la Rousse, aubergiste (feminin)" in messages[0]

    def test_ignore_les_fiches_invalides(self, ctx, moteurs):
        moteurs.fiche_json = "pas du json"
        assert generer(ctx, 2, afficher=lambda m: None) == 0

    def test_s_arrete_si_le_moteur_ne_repond_pas(self, ctx, moteurs):
        moteurs.fiche_json = MoteurIndisponible("Docker arrêté.")
        messages = []
        assert generer(ctx, 5, afficher=messages.append) == 0
        assert messages == ["[1/5] arrêt : Docker arrêté."]
