// Tests de la page de préparation : fiche et scénario (static/js/fiche.js), onglet Apparence (static/js/apparence.js).
import assert from "node:assert/strict";
import { test } from "node:test";

const fiche = await import(new URL("../../src/pnj_parlant/static/js/fiche.js", import.meta.url));
const apparence = await import(new URL("../../src/pnj_parlant/static/js/apparence.js", import.meta.url));
const { THEMES } = await import(new URL("../../src/pnj_parlant/static/js/univers.js", import.meta.url));

const YSOLDE = { id: "ysolde-0001", nom: "Ysolde", metier: "aubergiste", genre: "feminin", timbre: "aigu", debit: "rapide",
                 connaissances: ["La forge est au nord.", "Brom boit trop."], secret: "Elle cache un trésor.",
                 salutation: "Bienvenue !", voix: { name: "alice" }, portrait: 12 };

test("valeursFormulaire : un champ par clé, connaissances une par ligne, valeurs par défaut", () => {
  const v = fiche.valeursFormulaire(YSOLDE);
  assert.deepEqual(Object.keys(v), fiche.CHAMPS_FICHE);
  assert.equal(v.connaissances, "La forge est au nord.\nBrom boit trop.");
  assert.equal(v.genre, "feminin");
  assert.equal(v.apparence, "");
  const vierge = fiche.valeursFormulaire({});
  assert.deepEqual([vierge.genre, vierge.timbre, vierge.debit, vierge.nom], ["neutre", "moyen", "normal", ""]);
});

test("ficheDuFormulaire : champs nettoyés, connaissances en liste, le reste de la fiche gardé", () => {
  const valeurs = { ...fiche.valeursFormulaire(YSOLDE), nom: "  Ysolde la Rousse ", connaissances: " Un.\n\n  Deux. \n" };
  const npc = fiche.ficheDuFormulaire(YSOLDE, valeurs);
  assert.equal(npc.nom, "Ysolde la Rousse");
  assert.deepEqual(npc.connaissances, ["Un.", "Deux."]);
  assert.equal(npc.id, "ysolde-0001");
  assert.deepEqual(npc.voix, { name: "alice" });  // voix, portrait : pas dans le formulaire, gardés
  assert.equal(npc.secret, "Elle cache un trésor.");
  assert.ok(!("secret" in fiche.ficheDuFormulaire(YSOLDE, valeurs, true)));  // non lu : jamais renvoyé
  assert.equal(YSOLDE.nom, "Ysolde");  // la fiche d'origine n'est pas modifiée
});

test("aller-retour fiche → formulaire → fiche", () => {
  const { portrait, voix, ...sansExtras } = YSOLDE;
  const retour = fiche.ficheDuFormulaire({ id: YSOLDE.id }, fiche.valeursFormulaire(YSOLDE));
  assert.deepEqual(retour, { ...sansExtras, lieu: "", apparence: "", personnalite: "", humeur: "" });
  assert.ok(portrait && voix);
});

test("secretMasque, titreFiche, voixDuGenre, initiale", () => {
  assert.equal(fiche.secretMasque(YSOLDE), false);
  const { secret, ...lueSansMdp } = YSOLDE;
  assert.ok(secret);
  assert.equal(fiche.secretMasque(lueSansMdp), true);
  assert.equal(fiche.secretMasque({ nom: "Proposition" }), false);  // pas encore en banque : rien à masquer
  assert.equal(fiche.titreFiche(YSOLDE), "Modification de Ysolde");
  assert.equal(fiche.titreFiche({ nom: "Léo" }), "Proposition (non enregistrée)");
  assert.equal(fiche.titreFiche({}), "Nouveau PNJ");
  const voix = [{ name: "a", genre: "feminin" }, { name: "b", genre: "masculin" }];
  assert.deepEqual(fiche.voixDuGenre(voix, "feminin").map(v => v.name), ["a"]);
  assert.deepEqual(fiche.voixDuGenre(voix, "neutre").map(v => v.name), ["a", "b"]);
  assert.equal(fiche.initiale("  élise"), "É");
  assert.equal(fiche.initiale(""), "?");
  assert.equal(fiche.initiale(null), "?");
});

test("corpsScenario : changements par-dessus la version enregistrée, notes non lues jamais envoyées", () => {
  const enregistre = { monde: "Le Val", notes_mj: "Secret", theme: "donjon", style_portrait: "" };
  assert.deepEqual(fiche.corpsScenario(enregistre, { theme: "parchemin" }),
    { monde: "Le Val", notes_mj: "Secret", theme: "parchemin", style_portrait: "" });
  assert.deepEqual(fiche.corpsScenario(enregistre, { monde: "Autre", notes_mj: "" }, true),
    { monde: "Autre", theme: "donjon", style_portrait: "" });
  assert.equal(enregistre.theme, "donjon");
});

test("apparence : mention de l'origine et styles propres à l'univers", () => {
  assert.equal(apparence.mention("perso"), " · créé pour l’univers");
  assert.equal(apparence.mention("modifie"), " · modifié pour l’univers");
  assert.equal(apparence.mention("predefini"), "");
  const liste = [{ id: "peinture", nom: "Peinture", resume: "r", prompt: "p", origine: "predefini" },
                 { id: "manga", nom: "Manga 2", resume: "r2", prompt: "p2", origine: "modifie" },
                 { id: "gravure", nom: "Gravure", resume: "", prompt: "etching", origine: "perso" }];
  assert.deepEqual(apparence.portraitsPerso(liste), {
    manga: { nom: "Manga 2", resume: "r2", prompt: "p2" }, gravure: { nom: "Gravure", resume: "", prompt: "etching" } });
});

test("apparence : textes des éditeurs jumeaux (thème, style) selon l'origine", () => {
  assert.equal(apparence.libelleSuppression("theme", "modifie"), "Rétablir le thème d’origine");
  assert.equal(apparence.libelleSuppression("style", "modifie"), "Rétablir le style d’origine");
  assert.equal(apparence.libelleSuppression("theme", "perso"), "Supprimer");
  assert.equal(apparence.libelleSuppression("style", undefined), "Supprimer");
  assert.equal(apparence.confirmationSuppression("theme", "modifie", "Donjon"), "Rétablir les couleurs d’origine de « Donjon » ?");
  assert.equal(apparence.confirmationSuppression("theme", "perso", "Nuit"), "Supprimer le thème « Nuit » ?");
  assert.equal(apparence.confirmationSuppression("style", "modifie", "Manga"), "Rétablir le style d’origine de « Manga » ?");
  assert.equal(apparence.confirmationSuppression("style", "perso", "Gravure"), "Supprimer le style « Gravure » ?");
  assert.equal(apparence.messageSuppression("theme", "modifie", "Donjon"), "« Donjon » a retrouvé ses couleurs d’origine.");
  assert.equal(apparence.messageSuppression("theme", "perso", "Nuit"), "Thème « Nuit » supprimé.");
  assert.equal(apparence.messageSuppression("style", "modifie", "Manga"), "« Manga » a retrouvé sa description d’origine.");
  assert.equal(apparence.messageSuppression("style", "perso", "Gravure"), "Style « Gravure » supprimé.");
});

test("apparence : édition d'un thème existant ou nouveau (à partir du thème choisi), palettes copiées", () => {
  const tous = THEMES.map(t => ({ ...t, origine: "predefini" }));
  const { edition, base } = apparence.editionDeTheme(tous, THEMES[1].id, "");
  assert.equal(base.id, THEMES[1].id);
  assert.equal(edition.id, THEMES[1].id);
  assert.equal(edition.origine, "predefini");
  edition.clair.bg = "#123456";
  assert.notEqual(THEMES[1].clair?.bg, "#123456");  // copie : l'aperçu ne touche pas l'original
  const nouveau = apparence.editionDeTheme(tous, null, THEMES[2].id);
  assert.equal(nouveau.edition.id, null);
  assert.equal(nouveau.edition.origine, "perso");
  assert.equal(nouveau.base.id, THEMES[2].id);
  assert.equal(apparence.editionDeTheme(tous, null, "inconnu").base, THEMES[0]);
  // un thème à une seule palette prend l'autre du thème par défaut
  const sombre = apparence.editionDeTheme([{ id: "x", origine: "perso", mode: "sombre", sombre: THEMES[0].sombre }], "x", "");
  assert.deepEqual(sombre.edition.clair, THEMES[0].clair);
});

test("apparence : thème à enregistrer (palettes du mode seulement) et alertes de lisibilité", () => {
  const edition = { clair: { ...THEMES[0].clair }, sombre: { ...THEMES[0].sombre } };
  assert.deepEqual(apparence.palettesDuMode("auto"), ["clair", "sombre"]);
  assert.deepEqual(apparence.palettesDuMode("sombre"), ["sombre"]);
  const t = apparence.themeEdite({ nom: " Nuit ", resume: " Bleu ", mode: "sombre" }, edition);
  assert.deepEqual(Object.keys(t), ["nom", "resume", "mode", "sombre"]);
  assert.equal(t.nom, "Nuit");
  assert.notEqual(t.sombre, edition.sombre);
  assert.deepEqual(apparence.alertesPalettes(apparence.themeEdite({ nom: "a", resume: "", mode: "auto" }, edition)), []);
  const illisible = { ...THEMES[0].clair, ink: THEMES[0].clair.bg };
  const alertes = apparence.alertesPalettes({ mode: "clair", clair: illisible });
  assert.ok(alertes.length > 0);
  assert.match(alertes[0], /^Palette claire : .* peu lisible \(contraste \d+,\d, [\d,]+ conseillé\)\.$/);
});
