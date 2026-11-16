// Tests de l'aventurier joué et des jets de dés (src/pnj_parlant/static/js/aventurier.js).
import assert from "node:assert/strict";
import { test } from "node:test";

const { JET_LIBRE, affichageJet, apercuBonus, appreciation, bonusDeMaitrise, detailJet, ficheAventurier, formaterBonus, jetChoisi, lancer,
        menuJets, modificateurDnd, portraitAventurier, resumeAventurier, texteJet } =
  await import(new URL("../../src/pnj_parlant/static/js/aventurier.js", import.meta.url));

// Hasard qui donne ces d20 dans l'ordre (valeur v → (v - 1) / 20)
const des = (...valeurs) => { const v = [...valeurs]; return () => (v.shift() - 1) / 20; };

const PERSUASION = { id: "comp:persuasion", nom: "Persuasion", groupe: "Compétences", carac: "CHA", bonus: 6, avantage: false };
const AGILITE = { id: "car:agi", nom: "Agilité", groupe: "Caractéristiques", carac: "AGI", bonus: 3, avantage: true };
const ALDRIC = { id: "aldric-0001", nom: "Aldric", classe: "Paladin", systeme: "dnd5", niveau: 5, portrait: 12,
                 jets: [AGILITE, PERSUASION] };

test("formaterBonus et modificateurDnd", () => {
  assert.deepEqual([3, 0, -2].map(formaterBonus), ["+3", "+0", "−2"]);
  assert.deepEqual([1, 8, 9, 10, 11, 15, 20, 30].map(modificateurDnd), [-5, -1, -1, 0, 0, 2, 5, 10]);
});

test("lancer : d20 + bonus, avantage et désavantage", () => {
  assert.deepEqual(lancer(PERSUASION, "normal", des(11)), { des: [11], naturel: 11, bonus: 6, total: 17, mode: "normal" });
  assert.equal(lancer(AGILITE, "avantage", des(4, 15)).naturel, 15);
  const r = lancer(AGILITE, "desavantage", des(4, 15));
  assert.equal(r.naturel, 4);
  assert.equal(r.total, 7);
  for (let i = 0; i < 200; i++) {  // vrai hasard : toujours entre 1 et 20
    const n = lancer(JET_LIBRE).naturel;
    assert.ok(n >= 1 && n <= 20 && Number.isInteger(n));
  }
});

test("appreciation : critiques d'abord, puis seuils 10, 15, 20", () => {
  assert.equal(appreciation({ naturel: 20, total: 18 }), "réussite critique");
  assert.equal(appreciation({ naturel: 1, total: 12 }), "échec critique");  // un 1 échoue même avec un gros bonus
  assert.deepEqual([22, 15, 14, 10, 9, 5, 4].map(total => appreciation({ naturel: 8, total })),
    ["excellent résultat", "bon résultat", "résultat moyen", "résultat moyen", "mauvais résultat",
     "mauvais résultat", "très mauvais résultat"]);
});

test("textes du jet : sans chiffre pour le PNJ, avec pour le journal ; élision", () => {
  const r = lancer(PERSUASION, "normal", des(11));
  assert.equal(texteJet(PERSUASION, r), "(Jet de Persuasion : bon résultat.)");
  assert.equal(affichageJet(PERSUASION, r), "(Jet de Persuasion : 17, bon résultat.)");
  assert.equal(detailJet(r), "d20 : 11 +6");
  const a = lancer(AGILITE, "avantage", des(4, 15));
  assert.equal(texteJet(AGILITE, a), "(Jet d’Agilité : bon résultat.)");
  assert.equal(detailJet(a), "2d20 (4, 15), garde 15 +3");
  assert.equal(texteJet({ nom: "Histoire" }, a), "(Jet d’Histoire : bon résultat.)");
  assert.equal(texteJet(JET_LIBRE, lancer(JET_LIBRE, "normal", des(20))), "(Jet de chance : réussite critique.)");
  assert.equal(detailJet(lancer(JET_LIBRE, "normal", des(7))), "d20 : 7");
});

test("menuJets : le dé sans bonus en tête, puis un groupe par sorte de jet", () => {
  assert.deepEqual(menuJets(null), [{ groupe: "", jets: [{ jet: JET_LIBRE, libelle: "d20 sans bonus" }] }]);
  const menu = menuJets(ALDRIC);
  assert.deepEqual(menu.map(g => g.groupe), ["", "Caractéristiques", "Compétences"]);
  assert.equal(menu[1].jets[0].libelle, "Agilité +3 ★");          // ★ : dé bonus (caractéristique supérieure)
  assert.equal(menu[2].jets[0].libelle, "Persuasion (CHA) +6");
  assert.equal(jetChoisi(ALDRIC, "comp:persuasion"), PERSUASION);
  assert.equal(jetChoisi(ALDRIC, "inconnu"), JET_LIBRE);
  assert.equal(jetChoisi(null, "comp:persuasion"), JET_LIBRE);
});

test("apercuBonus : mêmes bonus que le serveur (tests/test_aventuriers.py)", () => {
  const dnd5 = { scores: true, defaut: 10, caracteristiques: [{ id: "for" }, { id: "int" }, { id: "cha" }],
                 competences: [{ id: "persuasion", carac: "cha" }, { id: "intimidation", carac: "cha" },
                               { id: "arcanes", carac: "int" }] };
  const a = apercuBonus({ niveau: 5, caracteristiques: { for: 16, int: 8, cha: 16 },
                          maitrises: { persuasion: 1, intimidation: 2 } }, dnd5);
  assert.deepEqual(a, { maitrise: 3, caracs: { for: 3, int: -1, cha: 3 },
                        competences: { persuasion: 6, intimidation: 9, arcanes: -1 }, capacites: [] });
  const cof2 = { scores: false, defaut: 0, caracteristiques: [{ id: "agi" }, { id: "cha" }], competences: [] };
  const c = apercuBonus({ caracteristiques: { agi: 3, cha: 2 }, capacites: [{ nom: "Baratin", carac: "cha", bonus: 5 }] }, cof2);
  assert.deepEqual(c.caracs, { agi: 3, cha: 2 });
  assert.deepEqual(c.capacites, [7]);
  assert.deepEqual([1, 4, 5, 9, 13, 17, 20].map(bonusDeMaitrise), [2, 2, 3, 4, 5, 6, 6]);
});

test("résumé, fiche envoyée au serveur et portrait", () => {
  const systemes = { dnd5: { nom: "Donjons & Dragons (5e édition)" } };
  assert.equal(resumeAventurier(ALDRIC, systemes), "Paladin · Donjons & Dragons 5e, niveau 5");
  assert.equal(resumeAventurier({ classe: "Barde" }, systemes), "Barde");
  assert.equal(resumeAventurier({ systeme: "" }), "");
  assert.deepEqual(Object.keys(ficheAventurier(ALDRIC)).sort(), ["classe", "id", "niveau", "nom", "systeme"]);
  assert.equal(ficheAventurier(null), null);
  assert.equal(portraitAventurier(ALDRIC), "/api/aventuriers/aldric-0001/portrait?v=12");
  assert.equal(portraitAventurier({ ...ALDRIC, portrait: 0 }), "");
});
