// Tests de l'état des contrôles de la vue Partie (src/pnj_parlant/static/js/controles.js), appliqué par setBusy.
import assert from "node:assert/strict";
import { test } from "node:test";

const { etatControles } = await import(new URL("../../src/pnj_parlant/static/js/controles.js", import.meta.url));

const YSOLDE = { id: "ysolde-0001", nom: "Ysolde" };
const BROM = { id: "brom-0001", nom: "Brom" };
const INVENTE = { nom: "Léo" };  // pas encore dans la banque
const BASE = { busy: false, npcs: [YSOLDE], rencontres: [YSOLDE], maxPnj: 3, multi: true, entree: true,
               interrompre: false, parole: false, ecoute: false, microDispo: true, choixBanque: "", modeleModifiable: true };
const etat = (changements) => etatControles({ ...BASE, ...changements });

test("etatControles : sans scène, on ne peut que créer ou jouer un PNJ", () => {
  const e = etat({ npcs: [], rencontres: [], choixBanque: "brom-0001" });
  assert.equal(e.desactive.genBtn, false);
  assert.equal(e.desactive.loadBtn, false);
  for (const id of ["sendBtn", "ask", "micBtn", "addBtn", "entreeBtn", "exportBtn"]) assert.equal(e.desactive[id], true, id);
  assert.equal(e.cache.entreeRow, true);
  assert.equal(e.cache.discuterBtn, true);
});

test("etatControles : action en cours, tout est désactivé sauf l'export", () => {
  const e = etat({ busy: true, choixBanque: "brom-0001" });
  for (const [id, v] of Object.entries(e.desactive)) assert.equal(v, id !== "exportBtn", id);
  assert.equal(e.aborder, true);
  assert.equal(e.retirer, true);
});

test("etatControles : « Parler » pendant que le PNJ parle seulement avec l'option, toujours actif en écoute", () => {
  assert.equal(etat({ busy: true, parole: true }).desactive.micBtn, true);
  assert.equal(etat({ busy: true, parole: true, interrompre: true }).desactive.micBtn, false);
  assert.equal(etat({ busy: true, parole: false, interrompre: true }).desactive.micBtn, true);  // transcription
  assert.equal(etat({ busy: true, ecoute: true }).desactive.micBtn, false);  // cliquable pour finir
  assert.equal(etat({ microDispo: false }).desactive.micBtn, true);
  assert.equal(etat({}).desactive.micBtn, false);
});

test("etatControles : « Enregistrer » seulement s'il reste un PNJ hors de la banque", () => {
  assert.equal(etat({}).desactive.saveBtn, true);
  assert.equal(etat({ npcs: [YSOLDE, INVENTE] }).desactive.saveBtn, false);
});

test("etatControles : scène pleine (maxPnj), PNJ déjà présent", () => {
  const plein = etat({ npcs: [YSOLDE, BROM, INVENTE], choixBanque: "autre" });
  assert.equal(plein.desactive.addBtn, true);
  assert.equal(plein.desactive.entreeBtn, true);
  assert.equal(plein.aborder, true);
  assert.equal(etat({ npcs: [YSOLDE, BROM, INVENTE], multi: false }).aborder, false);  // aborder remplace la scène
  assert.equal(etat({ choixBanque: "ysolde-0001" }).desactive.addBtn, true);  // déjà dans la scène
  assert.equal(etat({ choixBanque: "brom-0001" }).desactive.addBtn, false);
  assert.equal(etat({ maxPnj: 1, choixBanque: "brom-0001" }).desactive.addBtn, true);
});

test("etatControles : sans « Plusieurs PNJ », ses sous-options et boutons disparaissent", () => {
  const e = etat({ multi: false, npcs: [YSOLDE, BROM] });
  assert.equal(e.sousOptions, false);
  assert.equal(e.cache.addBtn, true);
  assert.equal(e.cache.entreeRow, true);  // « Faire entrer » coché mais inactif
  assert.equal(e.cache.discuterBtn, true);
  const avec = etat({ npcs: [YSOLDE, BROM] });
  assert.equal(avec.sousOptions, true);
  assert.equal(avec.cache.discuterBtn, false);
  assert.equal(etat({ entree: false }).cache.entreeRow, true);
});

test("etatControles : modèle de l'IA modifiable seulement avec les droits et hors action", () => {
  assert.equal(etat({}).desactive.modeleSel, false);
  assert.equal(etat({ modeleModifiable: false }).desactive.modeleSel, true);
  assert.equal(etat({ busy: true }).desactive.modeleSel, true);
});
