from pnj_parlant import dependances


def test_manquantes(tmp_path, monkeypatch):
    fichier = tmp_path / "pyproject.toml"
    fichier.write_text(
        '[project]\nname = "pnj-parlant"\ndependencies = ["pytest>=8", "paquet-absent-xyz>=1.0"]\n'
        '[project.optional-dependencies]\nvoix = ["voix-absente-xyz; sys_platform == \'win32\'"]\n'
        'stt = ["pytest"]\ntout = ["pnj-parlant[voix,stt]"]\n', encoding="utf-8")
    monkeypatch.setattr(dependances, "PROJET", "pytest")  # le paquet du projet n'est pas forcément installé
    assert dependances.manquantes(fichier) == {
        "obligatoires": ["paquet-absent-xyz"], "voix": ["voix-absente-xyz"], "stt": []}


def test_erreur_import():
    assert dependances.erreur_import("json") is None
    assert dependances.erreur_import("module_absent_xyz").startswith("ModuleNotFoundError")
