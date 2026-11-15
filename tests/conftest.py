"""Fixtures communes. Les faux moteurs vivent dans faux.py (importable par les tests : `from faux import ...`)."""
import pytest
from faux import FausseReconnaissance, FauxMoteurs, FauxPortraits, FauxTTS

from pnj_parlant.config import Config
from pnj_parlant.serveur import create_app


@pytest.fixture
def cfg(tmp_path):
    return Config({"dialogue": {"historique": 12, "intervention": 0.3}, "banque": {"dossier": "pnj"}}, tmp_path)


@pytest.fixture
def moteurs():
    return FauxMoteurs()


@pytest.fixture
def tts():
    return FauxTTS()


@pytest.fixture
def portraits():
    return FauxPortraits()


@pytest.fixture
def app(cfg, moteurs, tts, portraits):
    return create_app(cfg, moteurs=moteurs, tts=tts, reconnaissance=FausseReconnaissance(), portraits=portraits)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ctx(app):
    return app.extensions["pnj"]
