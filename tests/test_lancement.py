"""Points d'entrée et codes de sortie dont dépendent les lanceurs (lot 7.2) : serveur.main, generer.main,
dependances.main et `python -m pnj_parlant.config` (codes 0, 1 et 2 lus par lancer.bat)."""
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from pnj_parlant import config as configuration
from pnj_parlant import dependances, generer, serveur

RACINE = Path(__file__).parents[1]


# --- python -m pnj_parlant.config ----------------------------------------------------------------
class TestCodesDeSortieDeConfig:
    def lancer(self, tmp_path, contenu=None):
        env = {**os.environ, "PYTHONPATH": str(RACINE / "src")}
        env.pop("PNJ_CONFIG", None)
        if contenu is not None:
            (tmp_path / "config.toml").write_text(contenu, encoding="utf-8")
        return subprocess.run([sys.executable, "-m", "pnj_parlant.config"], cwd=tmp_path, env=env,
                              capture_output=True, timeout=60).returncode

    def test_ollama_attendu_sur_ce_pc_code_0(self, tmp_path):
        assert self.lancer(tmp_path, '[moteurs]\ncreation = "local"\ndialogue = "claude"\n') == 0

    def test_tout_claude_code_1(self, tmp_path):
        assert self.lancer(tmp_path, '[moteurs]\ncreation = "claude"\ndialogue = "claude"\n') == 1

    def test_ollama_sur_un_autre_pc_code_1(self, tmp_path):
        assert self.lancer(tmp_path, '[local]\nurl = "http://192.168.1.9:11434"\n') == 1

    def test_config_absente_code_2(self, tmp_path):
        assert self.lancer(tmp_path) == 2


# --- dependances.main ----------------------------------------------------------------------------
class TestDependancesMain:
    def appeler(self, monkeypatch, capsys, absents, erreur=None):
        tous = {"obligatoires": [], "voix": [], "stt": [], **absents}
        monkeypatch.setattr(dependances, "manquantes", lambda chemin: tous)
        monkeypatch.setattr(dependances, "erreur_import", lambda: erreur)
        monkeypatch.setattr(dependances.shutil, "which", lambda nom: None)
        code = dependances.main()
        return code, capsys.readouterr().out

    def test_tout_est_la_code_0_sans_rien_afficher(self, monkeypatch, capsys):
        assert self.appeler(monkeypatch, capsys, {}) == (0, "")

    def test_option_absente_code_0_avec_conseil(self, monkeypatch, capsys):
        code, sortie = self.appeler(monkeypatch, capsys, {"voix": ["piper-tts"]})
        assert code == 0 and "piper-tts" in sortie and "synthèse vocale" in sortie
        assert 'pip install -e ".[tout]"' in sortie

    def test_conseil_avec_uv_quand_il_est_installe(self, monkeypatch, capsys):
        monkeypatch.setattr(dependances.shutil, "which", lambda nom: "uv")
        monkeypatch.setattr(dependances, "manquantes", lambda c: {"obligatoires": [], "voix": [], "stt": ["av"]})
        monkeypatch.setattr(dependances, "erreur_import", lambda: None)
        assert dependances.main() == 0 and "uv pip install" in capsys.readouterr().out

    def test_dependance_obligatoire_absente_code_1(self, monkeypatch, capsys):
        code, sortie = self.appeler(monkeypatch, capsys, {"obligatoires": ["flask"]})
        assert code == 1 and "ne peut pas démarrer" in sortie and "flask" in sortie

    def test_environnement_endommage_code_1(self, monkeypatch, capsys):
        code, sortie = self.appeler(monkeypatch, capsys, {}, erreur="ImportError: DLL load failed")
        assert code == 1 and "endommagé" in sortie and "DLL load failed" in sortie

    def test_l_import_n_est_pas_essaye_quand_il_manque_des_paquets(self, monkeypatch, capsys):
        monkeypatch.setattr(dependances, "manquantes", lambda c: {"obligatoires": ["flask"], "voix": [], "stt": []})

        def boum():
            raise AssertionError("ne doit pas être appelé")
        monkeypatch.setattr(dependances, "erreur_import", boum)
        monkeypatch.setattr(dependances.shutil, "which", lambda nom: None)
        assert dependances.main() == 1


# --- generer.main --------------------------------------------------------------------------------
class TestGenererMain:
    def test_cree_les_pnj_et_resume(self, monkeypatch, capsys, ctx):
        vus = []
        monkeypatch.setattr(generer.configuration, "charger", lambda chemin=None: vus.append(chemin) or "cfg")
        monkeypatch.setattr(generer, "Contexte", lambda cfg: ctx)
        generer.main(["2", "--metier", "aubergiste", "--config", "mon.toml"])
        sortie = capsys.readouterr().out
        assert vus == ["mon.toml"]
        assert "[2/2]" in sortie and f"2 PNJ ajoutés dans {ctx.banque.dossier}" in sortie
        assert len(ctx.banque.liste()) == 2

    def test_config_introuvable_sort_avec_le_message(self, monkeypatch):
        def charger(chemin=None):
            raise configuration.ConfigIntrouvable("config.toml introuvable")
        monkeypatch.setattr(generer.configuration, "charger", charger)
        with pytest.raises(SystemExit) as e:
            generer.main(["1"])
        assert str(e.value) == "config.toml introuvable"

    def test_nombre_obligatoire_et_entier(self):
        with pytest.raises(SystemExit) as e:
            generer.main([])
        assert e.value.code == 2
        with pytest.raises(SystemExit):
            generer.main(["beaucoup"])


# --- serveur.main --------------------------------------------------------------------------------
class FausseApp:
    def __init__(self, ctx):
        self.extensions = {"pnj": ctx}
        self.lancee = None

    def run(self, **kwargs):
        self.lancee = kwargs


class FauxContexte:
    def __init__(self, problemes=(), stt_disponible=False):
        self.tts = SimpleNamespace(prechauffer=self.prechauffer)
        self.reconnaissance = SimpleNamespace(disponible=lambda: stt_disponible, charger=self.charger)
        self._problemes = list(problemes)
        self.evenements = {"voix": threading.Event(), "stt": threading.Event()}

    def prechauffer(self):
        self.evenements["voix"].set()

    def charger(self):
        self.evenements["stt"].set()

    def problemes(self):
        return self._problemes


@pytest.fixture
def lancement(monkeypatch):
    """Remplace signaux, config, create_app et certificat ; renvoie un objet pour régler et lire ce qui s'est passé."""
    etat = SimpleNamespace(signaux=[], ctx=FauxContexte(), srv={}, app=None, certificat=[])
    monkeypatch.setattr(serveur.signal, "signal", lambda sig, gestionnaire: etat.signaux.append((sig, gestionnaire)))
    monkeypatch.setattr(serveur.configuration, "charger",
                        lambda chemin=None: SimpleNamespace(section=lambda nom: etat.srv))

    def create_app(cfg):
        etat.app = FausseApp(etat.ctx)
        return etat.app
    monkeypatch.setattr(serveur, "create_app", create_app)
    monkeypatch.setattr(serveur, "certificat", lambda cfg: etat.certificat.append(cfg) or ("c.crt", "c.key"))
    monkeypatch.setattr(serveur.logging.getLogger("pnj_parlant"), "addHandler", lambda h: None)
    return etat


class TestServeurMain:
    def test_demarrage_par_defaut(self, lancement, capsys):
        serveur.main([])
        assert lancement.app.lancee == {"host": "0.0.0.0", "port": 5000, "ssl_context": None}
        assert lancement.ctx.evenements["voix"].wait(2) and not lancement.ctx.evenements["stt"].is_set()
        assert lancement.certificat == [] and capsys.readouterr().out == ""

    def test_ctrl_c_et_arret_branches(self, lancement):
        serveur.main([])
        assert {s for s, _ in lancement.signaux} >= {serveur.signal.SIGINT, serveur.signal.SIGTERM}
        assert all(g is serveur.arreter for _, g in lancement.signaux)

    def test_hote_port_et_https_de_la_configuration(self, lancement):
        lancement.srv.update({"hote": "127.0.0.1", "port": 7800, "https": True})
        serveur.main([])
        assert lancement.app.lancee == {"host": "127.0.0.1", "port": 7800, "ssl_context": ("c.crt", "c.key")}

    def test_config_donnee_en_argument(self, lancement, monkeypatch):
        vus = []
        monkeypatch.setattr(serveur.configuration, "charger",
                            lambda chemin=None: vus.append(chemin) or SimpleNamespace(section=lambda nom: {}))
        serveur.main(["--config", "autre.toml"])
        assert vus == ["autre.toml"]

    def test_problemes_affiches_dans_la_console(self, lancement, capsys):
        lancement.ctx = FauxContexte(problemes=[{"niveau": "erreur", "message": "clé absente"},
                                                {"niveau": "avertissement", "message": "voix absentes"}])
        serveur.main([])
        sortie = capsys.readouterr().out
        assert "[ERREUR] clé absente" in sortie and "[attention] voix absentes" in sortie

    def test_reconnaissance_locale_prechargee(self, lancement):
        lancement.ctx = FauxContexte(stt_disponible=True)
        serveur.main([])
        assert lancement.ctx.evenements["stt"].wait(2)

    @pytest.mark.parametrize("erreur", [configuration.ConfigIntrouvable("config.toml introuvable"),
                                        ValueError("moteur de voix inconnu")])
    def test_configuration_inutilisable_sort_avec_le_message(self, lancement, monkeypatch, erreur):
        def charger(chemin=None):
            raise erreur
        monkeypatch.setattr(serveur.configuration, "charger", charger)
        with pytest.raises(SystemExit) as e:
            serveur.main([])
        assert str(e.value) == str(erreur) and lancement.app is None


def test_arreter_quitte_sans_attendre_les_fils(monkeypatch, capsys):
    sorties = []
    monkeypatch.setattr(serveur.os, "_exit", sorties.append)
    serveur.arreter()
    assert sorties == [0] and "Arrêt" in capsys.readouterr().out


def test_certificat_cree_une_fois_puis_reutilise(tmp_path, monkeypatch):
    from werkzeug import serving
    creations = []

    def fabriquer(base, host):
        creations.append((base, host))
        Path(base + ".crt").write_text("c")
        Path(base + ".key").write_text("k")
    monkeypatch.setattr(serving, "make_ssl_devcert", fabriquer)
    cfg = configuration.Config({}, tmp_path)
    cert, cle = serveur.certificat(cfg)
    assert cert.endswith("devcert.crt") and cle.endswith("devcert.key") and len(creations) == 1
    assert creations[0][1] == "pnj-parlants" and serveur.certificat(cfg) == (cert, cle) and len(creations) == 1
