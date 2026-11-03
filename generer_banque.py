"""
Remplit la banque de PNJ (dossier pnj/) avec le moteur de création choisi dans config.toml.

    python generer_banque.py 20                       # 20 PNJ aux métiers tirés au sort
    python generer_banque.py 5 --metier "aubergiste"  # 5 aubergistes

Chaque PNJ est un fichier JSON lisible : relisez-les et retouchez-les à la main si besoin.
"""
import argparse

from app import BANK_DIR, create_npc, save_npc
from moteurs import MoteurIndisponible


def main():
    parser = argparse.ArgumentParser(description="Génère des PNJ dans la banque.")
    parser.add_argument("nombre", type=int, help="nombre de PNJ à créer")
    parser.add_argument("--metier", default="", help="métier imposé (sinon tiré au sort)")
    args = parser.parse_args()

    ok = 0
    for i in range(1, args.nombre + 1):
        try:
            npc = create_npc(args.metier)
        except ValueError:
            print(f"[{i}/{args.nombre}] fiche invalide, ignorée")
            continue
        except MoteurIndisponible as e:  # réseau, clé, Docker arrêté… inutile d'insister
            print(f"[{i}/{args.nombre}] arrêt : {e}")
            break
        npc_id = save_npc(npc)
        ok += 1
        print(f"[{i}/{args.nombre}] {npc['nom']}, {npc['metier']} ({npc['genre']}) -> {npc_id}.json")
    print(f"{ok} PNJ ajoutés dans {BANK_DIR}")


if __name__ == "__main__":
    main()
