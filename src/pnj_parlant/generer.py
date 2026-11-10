"""
Remplit la banque de PNJ (dossier pnj/) avec le moteur de création choisi dans config.toml.

    pnj-banque 20                       # 20 PNJ aux métiers tirés au sort
    pnj-banque 5 --metier "aubergiste"  # 5 aubergistes

Chaque PNJ est un fichier JSON lisible : relisez-les et retouchez-les à la main si besoin.
"""
import argparse

from . import config as configuration
from .moteurs import MoteurIndisponible
from .serveur import Contexte


def generer(ctx, nombre, metier="", afficher=print):
    """Crée `nombre` PNJ dans la banque ; renvoie le nombre de PNJ ajoutés."""
    ok = 0
    for i in range(1, nombre + 1):
        try:
            npc = ctx.creer_pnj(metier)
        except ValueError:
            afficher(f"[{i}/{nombre}] fiche invalide, ignorée")
            continue
        except MoteurIndisponible as e:  # réseau, clé, Docker arrêté… inutile d'insister
            afficher(f"[{i}/{nombre}] arrêt : {e}")
            break
        except KeyboardInterrupt:  # Ctrl+C : le PNJ en cours est abandonné, les précédents sont gardés
            afficher(f"\n[{i}/{nombre}] interrompu")
            break
        npc_id = ctx.enregistrer_pnj(npc)
        ok += 1
        afficher(f"[{i}/{nombre}] {npc['nom']}, {npc['metier']} ({npc['genre']}) -> {npc_id}.json")
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description="Génère des PNJ dans la banque.")
    parser.add_argument("nombre", type=int, help="nombre de PNJ à créer")
    parser.add_argument("--metier", default="", help="métier imposé (sinon tiré au sort)")
    parser.add_argument("--config", help="chemin de config.toml (par défaut : celui du dossier courant)")
    args = parser.parse_args(argv)
    try:
        ctx = Contexte(configuration.charger(args.config))
    except (configuration.ConfigIntrouvable, ValueError) as e:
        raise SystemExit(str(e)) from e
    ok = generer(ctx, args.nombre, args.metier)
    print(f"{ok} PNJ ajoutés dans {ctx.banque.dossier}")


if __name__ == "__main__":
    main()
