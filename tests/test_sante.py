"""Diagnostic du serveur pour le bandeau des pages (/api/sante) : dépendance absente, moteur injoignable, clé
manquante. Aucun réseau : Ollama et les paquets sont simulés."""
import pytest

from pnj_parlant import serveur

INSTALLES = {"tomlkit", "pocket_tts", "piper", "edge_tts", "faster_whisper"}


@pytest.fixture
def diag(monkeypatch, ctx, moteurs):
    """Tout va bien au départ : paquets présents, Ollama actif avec le modèle demandé, moteurs locaux."""
    etat = {"paquets": set(INSTALLES), "ollama": True}
    monkeypatch.setattr(serveur, "paquet_installe", lambda m: m in etat["paquets"])
    monkeypatch.setattr(serveur.systeme, "etat_ollama", lambda url: {"ok": etat["ollama"], "charges": []})
    moteurs.modeles_locaux = lambda: [{"nom": "faux", "taille": 1}]
    moteurs.local_cfg["modele"] = "faux"
    etat["cles"] = lambda: [p["cle"] for p in ctx.problemes()]
    return etat


def test_tout_va_bien(diag, client):
    assert diag["cles"]() == []
    assert client.get("/api/sante").get_json() == {"problemes": []}


def test_dependances_absentes(diag, ctx, tts):
    diag["paquets"] -= {"tomlkit", "pocket_tts"}
    tts.nom, tts.voix = "pocket", []
    problemes = {p["cle"]: p for p in ctx.problemes()}
    assert problemes["tomlkit"]["niveau"] == "erreur" and "uv sync" in problemes["tomlkit"]["message"]
    assert problemes["voix"]["niveau"] == "avertissement" and "paquet absent" in problemes["voix"]["message"]
    diag["paquets"].add("pocket_tts")  # paquet présent mais aucune voix
    assert "aucune voix" in {p["cle"]: p for p in ctx.problemes()}["voix"]["message"]


def test_reconnaissance_locale_absente(diag, ctx, tmp_path):
    class Locale:
        choisie, dossier = True, tmp_path / "modeles-stt" / "small"

        def disponible(self):
            return False
    ctx.reconnaissance = Locale()
    assert "modèle Whisper absent" in ctx.problemes()[0]["message"]
    diag["paquets"].discard("faster_whisper")
    assert "faster-whisper absent" in ctx.problemes()[0]["message"]


def test_portraits_locaux_sans_l_option(diag, ctx, portraits):
    ctx.cfg.reglages["portraits"] = {"moteur": "local"}
    portraits.actif = False
    assert diag["cles"]() == ["portraits"]


def test_moteurs_de_langage(diag, ctx, moteurs, monkeypatch):
    diag["ollama"] = False
    assert diag["cles"]() == ["ollama"]
    diag["ollama"] = True
    moteurs.local_cfg["modele"] = "absent"
    assert diag["cles"]() == ["ollama-modele"]
    moteurs.choix = {"creation": "claude", "dialogue": "lmstudio"}
    moteurs.etat_lmstudio = lambda: {"ok": False, "message": "LM Studio injoignable."}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    problemes = ctx.problemes()
    assert [p["cle"] for p in problemes] == ["claude", "lmstudio"] and problemes[1]["message"] == "LM Studio injoignable."
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")  # clé dans l'environnement : suffit
    assert diag["cles"]() == ["lmstudio"]
