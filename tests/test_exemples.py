"""Les univers d'exemple (src/pnj_parlant/exemples/<nom>/) se chargent comme une banque et leurs fiches respectent le schéma."""
import pytest

from pnj_parlant.banque import NPC_ID, Banque
from pnj_parlant.fiches import NPC_SCHEMA
from pnj_parlant.serveur import EXEMPLES as DOSSIER, exemples

EXEMPLES = sorted(p for p in DOSSIER.iterdir() if p.is_dir())


def test_il_y_a_au_moins_un_exemple_presente():
    assert EXEMPLES
    assert all(e["nom"] and e["resume"] for e in exemples())  # _infos.json : nom et résumé pour l'accueil


@pytest.mark.parametrize("dossier", EXEMPLES, ids=lambda p: p.name)
def test_exemple_complet_et_coherent(dossier):
    banque = Banque(dossier)
    scenario = banque.scenario()
    assert scenario["monde"] and scenario["notes_mj"]
    lieux = {lieu["id"] for lieu in banque.lieux()}
    assert len(lieux) >= 2 and all(NPC_ID.match(i) for i in lieux)

    pnjs = banque.liste()
    assert len(pnjs) >= 3
    proprietes = NPC_SCHEMA["properties"]
    for item in pnjs:
        npc = banque.lire(item["id"])
        manquants = [c for c in NPC_SCHEMA["required"] if not npc.get(c)]
        assert not manquants, f"{item['id']} : champs manquants {manquants}"
        for champ in ("genre", "timbre", "debit"):
            assert npc[champ] in proprietes[champ]["enum"], f"{item['id']} : {champ} = {npc[champ]}"
        assert len(npc["connaissances"]) == 3, item["id"]
        assert npc.get("lieu") in lieux, f"{item['id']} : lieu inconnu {npc.get('lieu')}"
        assert "voix" not in npc, f"{item['id']} : la voix dépend de la machine, le serveur l'attribue"
        # lu à voix haute : pas de markdown ni d'astérisques
        assert not any(c in npc["salutation"] for c in "*_#"), item["id"]
