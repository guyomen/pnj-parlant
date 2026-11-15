// Tests de l'ordre des répliques (src/pnj_parlant/static/js/tours.js), hasard injecté.
import assert from "node:assert/strict";
import { test } from "node:test";

const tours = await import(new URL("../../src/pnj_parlant/static/js/tours.js", import.meta.url));

const YSOLDE = { nom: "Ysolde la Rousse", metier: "aubergiste" };
const BROM = { nom: "Brom", metier: "forgeron" };
const LEO = { nom: "Léo", metier: "barde" };
const SCENE = [YSOLDE, BROM, LEO];
// hasard rejoué : chaque appel rend le nombre suivant
const suite = (...nombres) => () => nombres.shift();

test("auHasard : l'élément désigné par le tirage", () => {
  assert.equal(tours.auHasard(SCENE, () => 0), YSOLDE);
  assert.equal(tours.auHasard(SCENE, () => 0.5), BROM);
  assert.equal(tours.auHasard(SCENE, () => 0.99), LEO);
});

test("avecIntervention : seulement si l'option est active et le tirage sous la probabilité", () => {
  assert.deepEqual(tours.avecIntervention([YSOLDE], SCENE, { actif: true, proba: 0.3, hasard: suite(0.1, 0.9) }), [YSOLDE, LEO]);
  assert.deepEqual(tours.avecIntervention([YSOLDE], SCENE, { actif: true, proba: 0.3, hasard: suite(0.5) }), [YSOLDE]);
  assert.deepEqual(tours.avecIntervention([YSOLDE], SCENE, { actif: false, hasard: suite(0) }), [YSOLDE]);
  // personne d'autre dans la scène : aucun tirage
  assert.deepEqual(tours.avecIntervention([YSOLDE], [YSOLDE], { actif: true, hasard: () => assert.fail("tirage") }), [YSOLDE]);
  const ordre = [BROM];
  assert.equal(tours.avecIntervention(ordre, SCENE, { actif: true, hasard: suite(0, 0) }), ordre);  // complété sur place
  assert.deepEqual(ordre, [BROM, YSOLDE]);
});

test("ordreDesReponses : cités, sinon le dernier à avoir parlé, sinon le premier de la scène", () => {
  const sans = { actif: false };
  assert.deepEqual(tours.ordreDesReponses([BROM, YSOLDE], SCENE, LEO, { actif: true, hasard: suite(0) }), [BROM, YSOLDE]);
  assert.deepEqual(tours.ordreDesReponses([BROM], SCENE, LEO, sans), [BROM]);
  assert.deepEqual(tours.ordreDesReponses([], SCENE, LEO, sans), [LEO]);
  assert.deepEqual(tours.ordreDesReponses([], SCENE, { nom: "parti" }, sans), [YSOLDE]);  // a quitté la scène
  assert.deepEqual(tours.ordreDesReponses([], SCENE, null, sans), [YSOLDE]);
  assert.deepEqual(tours.ordreDesReponses([BROM], SCENE, LEO, { actif: true, proba: 0.3, hasard: suite(0.2, 0) }), [BROM, YSOLDE]);
});

test("ordreDiscussion : un autre que le dernier, puis une intervention possible", () => {
  assert.deepEqual(tours.ordreDiscussion(SCENE, YSOLDE, { actif: false, hasard: suite(0.9) }), [LEO]);
  assert.deepEqual(tours.ordreDiscussion(SCENE, YSOLDE, { actif: true, proba: 0.3, hasard: suite(0, 0.1, 0) }), [BROM, YSOLDE]);
});

test("prioriser : questionnés en tête, dans l'ordre cité, une seule fois", () => {
  assert.deepEqual(tours.prioriser([LEO], [BROM, YSOLDE]), [BROM, YSOLDE, LEO]);
  assert.deepEqual(tours.prioriser([LEO, BROM], [BROM]), [BROM, LEO]);  // déplacé, pas dupliqué
  const appeles = [BROM, YSOLDE];
  tours.prioriser([], appeles);
  assert.deepEqual(appeles, [BROM, YSOLDE]);  // la liste reçue n'est pas retournée
});

// Faux tour : enregistre l'appel et rend la réplique prévue pour ce PNJ
function fauxTours(repliques) {
  const appels = [];
  const tour = async (n, voix) => {
    appels.push(n.nom);
    await voix;
    const r = repliques[n.nom] ?? { reply: "Hm." };
    return { voice: Promise.resolve(n.nom), erreur: r.erreur ?? null, reply: r.reply ?? "" };
  };
  return { appels, tour };
}

test("enchainerTours : chacun son tour, un PNJ questionné répond juste après", async () => {
  const { appels, tour } = fauxTours({ "Ysolde la Rousse": { reply: "Brom, tu en penses quoi ?" } });
  const { tours: faits, voix } = await tours.enchainerTours([YSOLDE, LEO], { tour, presents: () => SCENE });
  assert.deepEqual(appels, ["Ysolde la Rousse", "Brom", "Léo"]);
  assert.equal(faits.length, 3);
  assert.equal(await voix, "Léo");  // fin de la dernière parole
});

test("enchainerTours : au plus MAX_TOURS répliques quand ils s'interpellent sans fin", async () => {
  const { appels, tour } = fauxTours({ "Ysolde la Rousse": { reply: "Et toi, Brom ?" }, Brom: { reply: "Et toi, Ysolde ?" } });
  await tours.enchainerTours([YSOLDE], { tour, presents: () => SCENE });
  assert.equal(appels.length, tours.MAX_TOURS);
  assert.deepEqual(appels, ["Ysolde la Rousse", "Brom", "Ysolde la Rousse", "Brom"]);
});

test("enchainerTours : arrêt sur erreur, sur Stop, et si le PNJ a quitté la scène", async () => {
  let f = fauxTours({ "Ysolde la Rousse": { erreur: new Error("panne") } });
  await tours.enchainerTours([YSOLDE, BROM], { tour: f.tour, presents: () => SCENE });
  assert.deepEqual(f.appels, ["Ysolde la Rousse"]);

  const ctrl = new AbortController();
  f = fauxTours({});
  const tour = async (n, v) => { ctrl.abort(); return f.tour(n, v); };
  await tours.enchainerTours([YSOLDE, BROM], { tour, presents: () => SCENE, signal: ctrl.signal });
  assert.deepEqual(f.appels, ["Ysolde la Rousse"]);

  f = fauxTours({});
  const { tours: aucun, voix } = await tours.enchainerTours([LEO, BROM], { tour: f.tour, presents: () => [YSOLDE, BROM] });
  assert.deepEqual(f.appels, []);
  assert.deepEqual(aucun, []);
  assert.equal(await voix, undefined);
});

test("oublierNonDit : réplique interrompue raccourcie à ce qui a été dit, ou retirée", () => {
  const dite = { speaker: "Brom", content: "Bonjour. Je forge des épées. Et des haches." };
  const muette = { speaker: "Léo", content: "Je chante." };
  const history = [{ speaker: null, content: "Salut" }, dite, muette];
  tours.oublierNonDit(history, dite, "Bonjour.");
  tours.oublierNonDit(history, muette, "");
  assert.deepEqual(history, [{ speaker: null, content: "Salut" }, { speaker: "Brom", content: "Bonjour." }]);
  tours.oublierNonDit(history, muette, "");  // déjà retirée : rien d'autre ne disparaît
  assert.equal(history.length, 2);
});
