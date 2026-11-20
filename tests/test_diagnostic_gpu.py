"""scripts/diagnostic_gpu.py : rapport de la carte graphique, à lancer sur une machine qu'on ne peut pas joindre.
Chargé par son chemin ; commandes externes et Ollama remplacés (ni réseau, ni PowerShell, ni nvidia-smi)."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "diagnostic_gpu.py"


@pytest.fixture
def diag(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("diagnostic_gpu", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commandes = []
    monkeypatch.setattr(module, "commande", lambda args, delai=15: commandes.append(args))
    monkeypatch.setattr(module, "RAPPORT", tmp_path / "diagnostic-gpu.txt")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("hors ligne")))
    monkeypatch.setattr(module.time, "sleep", lambda s: None)  # relevés à 1 s d'écart : sans attendre
    from pnj_parlant import systeme  # compteurs de Windows : jamais les vrais
    monkeypatch.setattr(systeme, "compteurs_windows", lambda: (
        {"pid_1_luid_0x0_0x1_phys_0_eng_3_engtype_Compute_0": 80.0}, {"luid_0x0_0x1_phys_0": 4096.0 * 1024 * 1024}))
    module.commandes = commandes
    return module


def test_rapport_complet_sans_chemin_personnel(diag, monkeypatch):
    from pnj_parlant import systeme
    monkeypatch.setattr(systeme, "etat_gpu", lambda: {"nom": "AMD Radeon RX 6600", "usage": None,
                                                      "memoire_mo": None, "memoire_totale_mo": 8192})
    assert diag.main() == 0
    rapport = diag.RAPPORT.read_text(encoding="utf-8")
    assert "=== Système" in rapport and "=== Ce que lit systeme.py" in rapport and "=== Ollama" in rapport
    assert "etat_gpu()" in rapport and "AMD Radeon RX 6600" in rapport
    assert "Ollama ne répond pas : hors ligne" in rapport
    assert str(Path.home()) not in rapport  # ni nom d'utilisateur ni chemin personnel
    assert diag.commandes[0][0] == "git"


def test_exception_rapportee_sans_arreter_le_diagnostic(diag, monkeypatch):
    from pnj_parlant import systeme

    def panne():
        raise RuntimeError("registre cassé")
    monkeypatch.setattr(systeme, "etat_gpu", panne)
    assert diag.main() == 0
    rapport = diag.RAPPORT.read_text(encoding="utf-8")
    assert "EXCEPTION" in rapport and "RuntimeError: registre cassé" in rapport


def test_releves_des_compteurs_de_windows(diag, capsys):
    from pnj_parlant import systeme
    diag.section_compteurs_pdh(systeme)
    rapport = "\n".join(diag.lignes)
    assert rapport.count("relevé ") == 8
    assert "activité 80 %, mémoire dédiée 4096 Mo" in rapport and "{'Compute_0': 80.0}" in rapport


def test_octets_du_registre(diag):
    assert diag.octets_lisibles((8 << 30).to_bytes(8, "little")) == "octets 0000000002000000 = 8589934592"
    assert diag.octets_lisibles("AMD Radeon\0".encode("utf-16-le")) == "texte 'AMD Radeon'"
    assert diag.octets_lisibles(b"\x00\xd8\x01") == "octets 00d801"  # UTF-16 coupé : laissé en octets
