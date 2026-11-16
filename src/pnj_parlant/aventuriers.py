"""
Aventuriers : les personnages des joueurs. Facultatifs : sans aventurier choisi, le joueur reste « le voyageur ».

Une fiche d'aventurier (pnj/_aventurier-<id>.json, voir banque.py) :
    {"nom", "genre", "classe" (classe, profil, peuple… en texte libre), "apparence",
     "systeme": "" (sans caractéristiques), "dnd5" ou "cof2",
     "niveau", "caracteristiques": {id: valeur},
     "maitrises": {compétence: 1 (maîtrise) ou 2 (expertise)}   (D&D 5e)
     "superieures": [id], "capacites": [{nom, carac, bonus}]}    (Chroniques Oubliées Fantasy 2e)

Le PNJ ne voit jamais de chiffres : `portrait_pour_le_pnj` traduit ce qui se remarque (force, charisme, talents
sociaux) en mots. Les jets de dés se font dans le navigateur (js/aventurier.js) avec les bonus de `jets`.
"""
DND5, COF2 = "dnd5", "cof2"

# Caractéristiques : (id, nom, abréviation). D&D 5e : scores (10 = moyen, modificateur = (score - 10) // 2) ;
# COF 2e : la valeur est directement le modificateur du d20 (0 = moyen).
SYSTEMES = {
    DND5: {
        "nom": "Donjons & Dragons (5e édition)",
        "scores": True, "min": 1, "max": 30, "defaut": 10,
        "caracteristiques": [("for", "Force", "FOR"), ("dex", "Dextérité", "DEX"), ("con", "Constitution", "CON"),
                             ("int", "Intelligence", "INT"), ("sag", "Sagesse", "SAG"), ("cha", "Charisme", "CHA")],
        # compétences (id, nom, caractéristique) ; sociales : décrites au PNJ quand l'aventurier y excelle
        "competences": [("acrobaties", "Acrobaties", "dex"), ("arcanes", "Arcanes", "int"),
                        ("athletisme", "Athlétisme", "for"), ("discretion", "Discrétion", "dex"),
                        ("dressage", "Dressage", "sag"), ("escamotage", "Escamotage", "dex"),
                        ("histoire", "Histoire", "int"), ("intimidation", "Intimidation", "cha"),
                        ("intuition", "Intuition", "sag"), ("investigation", "Investigation", "int"),
                        ("medecine", "Médecine", "sag"), ("nature", "Nature", "int"),
                        ("perception", "Perception", "sag"), ("persuasion", "Persuasion", "cha"),
                        ("religion", "Religion", "int"), ("representation", "Représentation", "cha"),
                        ("survie", "Survie", "sag"), ("tromperie", "Tromperie", "cha")],
        "sociales": ("intimidation", "intuition", "persuasion", "representation", "tromperie"),
        "superieures": False, "capacites": False,
    },
    COF2: {
        "nom": "Chroniques Oubliées Fantasy (2e édition)",
        "scores": False, "min": -5, "max": 10, "defaut": 0,
        "caracteristiques": [("agi", "Agilité", "AGI"), ("con", "Constitution", "CON"), ("for", "Force", "FOR"),
                             ("per", "Perception", "PER"), ("cha", "Charisme", "CHA"),
                             ("int", "Intelligence", "INT"), ("vol", "Volonté", "VOL")],
        "competences": [], "sociales": (),
        # caractéristique supérieure : dé bonus (deux d20, on garde le meilleur) ; capacités : bonus à certains tests
        "superieures": True, "capacites": True,
    },
}
GENRES = ("feminin", "masculin", "neutre")
NIVEAU_MAX = 20
CAPACITES_MAX = 20
BONUS_MIN, BONUS_MAX = -10, 20

# Ce qui se remarque au premier regard (caractéristique basse, haute) ; Sagesse et Volonté se devinent à l'attitude
ALLURE = {"for": ("chétif", "d'une force impressionnante"), "dex": ("gauche", "vif et adroit"),
          "agi": ("gauche", "vif et agile"), "con": ("d'allure fragile", "robuste et endurant"),
          "int": ("pas très futé", "d'une vive intelligence"), "sag": ("naïf", "posé et perspicace"),
          "per": ("distrait", "à l'œil vif"), "cha": ("terne, sans prestance", "d'un charisme saisissant"),
          "vol": ("influençable", "d'une volonté de fer")}
FAIBLE, FORT = -1, 3        # modificateur d'une caractéristique remarquée (≤ FAIBLE ou ≥ FORT)
DOUE, MAITRE = 5, 8         # bonus d'un talent remarqué


def systemes_pour_la_page():
    """Catalogue des systèmes pour le formulaire de la page de préparation (et /api/systemes)."""
    return {sid: {"nom": s["nom"], "scores": s["scores"], "min": s["min"], "max": s["max"], "defaut": s["defaut"],
                  "caracteristiques": [{"id": i, "nom": n, "abrev": a} for i, n, a in s["caracteristiques"]],
                  "competences": [{"id": i, "nom": n, "carac": c} for i, n, c in s["competences"]],
                  "superieures": s["superieures"], "capacites": s["capacites"]}
            for sid, s in SYSTEMES.items()}


def _texte(valeur, longueur):
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        valeur = str(valeur)
    return " ".join(valeur.split())[:longueur] if isinstance(valeur, str) else ""


def _entier(valeur, defaut, minimum, maximum):
    """Entier borné ; `defaut` si la valeur n'est pas un nombre (texte d'un nombre accepté)."""
    if isinstance(valeur, bool):
        return defaut
    if isinstance(valeur, str):
        try:
            valeur = int(valeur.strip().replace("−", "-"))
        except ValueError:
            return defaut
    if not isinstance(valeur, (int, float)) or valeur != valeur:  # NaN
        return defaut
    return max(minimum, min(maximum, int(valeur)))


def normaliser(av):
    """Fiche d'aventurier aux champs sûrs (reçue du navigateur ou d'un fichier importé) : textes bornés, système
    connu (sinon aucun), valeurs dans les bornes du système. Les champs inconnus (id, portrait, jets) sont retirés."""
    av = av if isinstance(av, dict) else {}
    propre = {"nom": _texte(av.get("nom"), 80), "classe": _texte(av.get("classe"), 120),
              "apparence": _texte(av.get("apparence"), 600)}
    if av.get("genre") in GENRES:
        propre["genre"] = av["genre"]
    systeme = av.get("systeme") if av.get("systeme") in SYSTEMES else ""
    propre["systeme"] = systeme
    if not systeme:
        return propre
    s = SYSTEMES[systeme]
    ids = [c[0] for c in s["caracteristiques"]]
    caracs = av.get("caracteristiques") if isinstance(av.get("caracteristiques"), dict) else {}
    propre["niveau"] = _entier(av.get("niveau"), 1, 1, NIVEAU_MAX)
    propre["caracteristiques"] = {c: _entier(caracs.get(c), s["defaut"], s["min"], s["max"]) for c in ids}
    if s["competences"]:
        maitrises = av.get("maitrises") if isinstance(av.get("maitrises"), dict) else {}
        propre["maitrises"] = {c[0]: maitrises[c[0]] for c in s["competences"]
                               if maitrises.get(c[0]) in (1, 2) and not isinstance(maitrises.get(c[0]), bool)}
    if s["superieures"]:
        sup = av.get("superieures") if isinstance(av.get("superieures"), list) else []
        propre["superieures"] = [c for c in ids if c in sup]
    if s["capacites"]:
        capacites = av.get("capacites") if isinstance(av.get("capacites"), list) else []
        propre["capacites"] = [
            {"nom": _texte(c.get("nom"), 60), "carac": c.get("carac") if c.get("carac") in ids else ids[0],
             "bonus": _entier(c.get("bonus"), 0, BONUS_MIN, BONUS_MAX)}
            for c in capacites if isinstance(c, dict) and _texte(c.get("nom"), 60)][:CAPACITES_MAX]
    return propre


def modificateur(av, carac):
    """Bonus d'une caractéristique au d20 : (score - 10) // 2 en D&D 5e, la valeur elle-même en COF 2e."""
    s = SYSTEMES[av["systeme"]]
    valeur = av["caracteristiques"].get(carac, s["defaut"])
    return (valeur - 10) // 2 if s["scores"] else valeur


def bonus_de_maitrise(niveau):
    """D&D 5e : +2 aux niveaux 1 à 4, +3 aux niveaux 5 à 8… +6 aux niveaux 17 à 20."""
    return 2 + (max(1, niveau) - 1) // 4


def jets(av):
    """Jets que l'aventurier peut tenter (fiche normalisée) : [{id, nom, groupe, carac (abréviation), bonus,
    avantage (dé bonus de COF : caractéristique supérieure)}]. Vide sans système."""
    if av.get("systeme") not in SYSTEMES:
        return []
    s = SYSTEMES[av["systeme"]]
    abrev = {i: a for i, _, a in s["caracteristiques"]}
    sup = set(av.get("superieures", []))
    liste = [{"id": f"car:{i}", "nom": n, "groupe": "Caractéristiques", "carac": a,
              "bonus": modificateur(av, i), "avantage": i in sup} for i, n, a in s["caracteristiques"]]
    maitrise = bonus_de_maitrise(av.get("niveau", 1))
    liste += [{"id": f"comp:{i}", "nom": n, "groupe": "Compétences", "carac": abrev[c],
               "bonus": modificateur(av, c) + maitrise * av.get("maitrises", {}).get(i, 0), "avantage": False}
              for i, n, c in s["competences"]]
    liste += [{"id": f"cap:{k}", "nom": c["nom"], "groupe": "Capacités", "carac": abrev[c["carac"]],
               "bonus": modificateur(av, c["carac"]) + c["bonus"], "avantage": c["carac"] in sup}
              for k, c in enumerate(av.get("capacites", []))]
    return liste


def _allure(av):
    """Ce qui se remarque de ses caractéristiques : ["d'une force impressionnante", "terne, sans prestance"]."""
    s = SYSTEMES[av["systeme"]]
    traits = []
    for i, _, _ in s["caracteristiques"]:
        m = modificateur(av, i)
        if i in ALLURE and (m <= FAIBLE or m >= FORT):
            traits.append(ALLURE[i][m >= FORT])
    return traits


def _talents(av):
    """Talents sociaux remarquables : ["doué en persuasion", "piètre en tromperie"]."""
    s = SYSTEMES[av["systeme"]]
    sociaux = [j for j in jets(av) if j["groupe"] == "Capacités"
               or (j["groupe"] == "Compétences" and j["id"][5:] in s["sociales"])]
    talents = []
    for j in sociaux:
        if j["bonus"] >= MAITRE:
            talents.append(f"remarquable en {j['nom'].lower()}")
        elif j["bonus"] >= DOUE:
            talents.append(f"doué en {j['nom'].lower()}")
        elif j["bonus"] < 0:
            talents.append(f"piètre en {j['nom'].lower()}")
    return talents


def mots(av=None):
    """Comment le PNJ désigne le joueur : {"etiquette": "Voyageur", "le": "le voyageur", "un": "un voyageur"},
    au féminin pour une aventurière."""
    if (av or {}).get("genre") == "feminin":
        return {"etiquette": "Voyageuse", "le": "la voyageuse", "un": "une voyageuse"}
    return {"etiquette": "Voyageur", "le": "le voyageur", "un": "un voyageur"}


def portrait_pour_le_pnj(av):
    """Ce que le PNJ perçoit de l'aventurier (fiche normalisée), pour ses consignes ; "" sans aventurier.
    Son nom y figure, avec la consigne de ne s'en servir qu'une fois qu'il s'est présenté."""
    if not av or not av.get("nom"):
        return ""
    m = mots(av)
    lignes = [f"Qui te parle : {m['le']}."]
    if av.get("apparence"):
        lignes.append(f"Son apparence : {av['apparence']}")
    if av.get("classe"):
        lignes.append(f"À son allure, on devine : {av['classe']}.")
    if av.get("systeme") in SYSTEMES:
        allure, talents = _allure(av), _talents(av)
        if allure:
            lignes.append("Au premier regard : " + ", ".join(allure) + ".")
        if talents:
            lignes.append("Ses talents (tu ne les connais pas, mais ils agissent sur toi) : " + ", ".join(talents)
                          + ". Tiens-en compte selon ton caractère : on cède plus volontiers à quelqu'un de doué "
                          "pour convaincre ou impressionner, et un piètre menteur se trahit.")
    il = "elle" if av.get("genre") == "feminin" else "il"
    lignes.append(f"Son nom est {av['nom']}, mais tu ne le sais pas encore : ne l'appelle ainsi qu'une fois "
                  f"qu'{il} s'est {'présentée' if il == 'elle' else 'présenté'} ou qu'on l'a nommé"
                  f"{'e' if il == 'elle' else ''} devant toi.")
    return "\n".join(lignes)
