"""Hook Claude Code .claude/hooks/doc_a_jour.py (événement Stop) : code changé sans documentation."""
import importlib.util
import io
import json
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture
def hook():
    spec = importlib.util.spec_from_file_location("doc_a_jour", RACINE / ".claude" / "hooks" / "doc_a_jour.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lancer(hook, monkeypatch, capsys, modifies, entree=None):
    monkeypatch.setattr(hook, "fichiers_modifies", lambda: modifies)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(entree or {})))
    assert hook.main() == 0
    return capsys.readouterr().out


def test_code_sans_doc_bloque(hook, monkeypatch, capsys):
    sortie = json.loads(lancer(hook, monkeypatch, capsys, ["src/pnj_parlant/texte.py"]))
    assert sortie["decision"] == "block"
    assert "src/pnj_parlant/texte.py" in sortie["reason"]


def test_code_avec_doc_ou_sans_code_laisse_finir(hook, monkeypatch, capsys):
    assert lancer(hook, monkeypatch, capsys, ["src/pnj_parlant/texte.py", ".claude/rules/serveur.md"]) == ""
    assert lancer(hook, monkeypatch, capsys, ["tests/test_texte.py"]) == ""
    assert lancer(hook, monkeypatch, capsys, ["src/pnj_parlant/__pycache__/texte.pyc"]) == ""


def test_ne_bloque_pas_deux_fois(hook, monkeypatch, capsys):
    assert lancer(hook, monkeypatch, capsys, ["src/x.py"], {"stop_hook_active": True}) == ""


def test_git_lance_a_la_racine_du_projet(hook, monkeypatch, tmp_path):
    """Le dossier courant de la session peut avoir changé : git status part de CLAUDE_PROJECT_DIR."""
    vus = {}

    def faux_run(cmd, **kw):
        vus["cwd"] = kw.get("cwd")
        return subprocess.CompletedProcess(cmd, 0, stdout=' M src/a.py\nR  docs/v.md -> docs/n.md\n?? "src/b c.py"\n')

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(hook.subprocess, "run", faux_run)
    assert hook.fichiers_modifies() == ["src/a.py", "docs/n.md", "src/b c.py"]
    assert vus["cwd"] == str(tmp_path)


def test_racine_par_defaut(hook, monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert Path(hook.racine_du_projet()) == RACINE
