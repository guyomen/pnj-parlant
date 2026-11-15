// Tests du bandeau d'alertes (src/pnj_parlant/static/js/bandeau.js) : ses cinq exports et la fermeture au clic.
// Fichier à part : le module se charge ici avec un faux `document` (dans scene.test.mjs, il se charge sans).
// Lancement : node --test tests/js/
import assert from "node:assert/strict";
import { test } from "node:test";

const zone = { hidden: true, innerHTML: "" };
let clic = null;
globalThis.document = {
  getElementById: (id) => (id === "bandeau" ? zone : null),
  addEventListener: (type, gestionnaire) => { if (type === "click") clic = gestionnaire; },
};
let stock = {};
globalThis.sessionStorage = {
  getItem: (k) => stock[k] ?? null, setItem: (k, v) => { stock[k] = v; }, removeItem: (k) => { delete stock[k]; },
};
const bandeau = await import("../../src/pnj_parlant/static/js/bandeau.js");

const cles = () => [...zone.innerHTML.matchAll(/data-fermer="([^"]*)"/g)].map(m => m[1]);
function repartir() {  // état propre entre deux tests : le module garde ses alertes
  for (const c of cles()) bandeau.retirer(c);
  stock = {};
  delete globalThis.fetch;
}
const reponse = (status, corps) => ({ ok: status < 400, status, json: async () => {
  if (corps === undefined) throw new SyntaxError("vide");
  return corps;
} });
const cliquerSur = (cle) => clic({ target: { closest: () => ({ dataset: { fermer: cle } }) } });

test("le bandeau est abonné au clic de la page", () => {
  assert.equal(typeof clic, "function");
});

test("signaler : affiche, échappe le HTML, remplace une même clé", () => {
  repartir();
  bandeau.signaler("Micro <refusé>", { cle: "micro" });
  assert.equal(zone.hidden, false);
  assert.match(zone.innerHTML, /<strong>Erreur :<\/strong> Micro &lt;refusé&gt;/);
  assert.doesNotMatch(zone.innerHTML, /<refusé>/);
  bandeau.signaler("Micro bloqué", { cle: "micro", niveau: "avertissement" });
  assert.deepEqual(cles(), ["micro"]);
  assert.match(zone.innerHTML, /alerte avertissement/);
  assert.match(zone.innerHTML, /Attention :/);
  assert.match(zone.innerHTML, /aria-label="Fermer ce message"/);
  repartir();
});

test("signaler : la clé par défaut est le message, cinq alertes au plus", () => {
  repartir();
  for (let i = 1; i <= 7; i++) bandeau.signaler(`Message ${i}`);
  assert.deepEqual(cles(), ["Message 3", "Message 4", "Message 5", "Message 6", "Message 7"]);
  repartir();
});

test("retirer : cache le bandeau vide, ignore une clé inconnue", () => {
  repartir();
  bandeau.signaler("A", { cle: "a" });
  bandeau.signaler("B", { cle: "b" });
  const avant = zone.innerHTML;
  bandeau.retirer("inconnue");
  assert.equal(zone.innerHTML, avant);
  bandeau.retirer("a");
  assert.deepEqual(cles(), ["b"]);
  assert.equal(zone.hidden, false);
  bandeau.retirer("b");
  assert.equal(zone.hidden, true);
  assert.equal(zone.innerHTML.trim(), "");
});

test("requete : réponse reçue, l'alerte « serveur » est retirée (même sur une erreur HTTP)", async () => {
  repartir();
  bandeau.signaler(bandeau.SERVEUR_INJOIGNABLE, { cle: "serveur" });
  globalThis.fetch = async () => reponse(500);
  const r = await bandeau.requete("/api/x", { method: "POST" });
  assert.equal(r.status, 500);
  assert.deepEqual(cles(), []);
  repartir();
});

test("requete : serveur injoignable signalé puis relancé en français", async () => {
  repartir();
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await assert.rejects(bandeau.requete("/api/x"), { message: bandeau.SERVEUR_INJOIGNABLE });
  assert.deepEqual(cles(), ["serveur"]);
  assert.match(zone.innerHTML, /Serveur injoignable/);
  repartir();
});

test("requete : une requête annulée (Stop, Échap) n'est pas une panne", async () => {
  repartir();
  globalThis.fetch = async () => { throw Object.assign(new Error("abandon"), { name: "AbortError" }); };
  await assert.rejects(bandeau.requete("/api/x"), { name: "AbortError" });
  assert.deepEqual(cles(), []);
});

test("verifierSante : problèmes du serveur remplacés à chaque diagnostic", async () => {
  repartir();
  bandeau.signaler("Micro refusé", { cle: "micro" });
  globalThis.fetch = async () => reponse(200, { problemes: [
    { cle: "voix", niveau: "avertissement", message: "Pas de voix" },
    { cle: "claude", niveau: "erreur", message: "Clé absente" }] });
  await bandeau.verifierSante();
  assert.deepEqual(cles(), ["sante:voix", "sante:claude", "micro"]);
  globalThis.fetch = async () => reponse(200, { problemes: [{ cle: "claude", niveau: "erreur", message: "Clé absente" }] });
  await bandeau.verifierSante();
  assert.deepEqual(cles(), ["sante:claude", "micro"]);
  globalThis.fetch = async () => reponse(200, { problemes: [] });
  await bandeau.verifierSante();
  assert.deepEqual(cles(), ["micro"]);
  repartir();
});

test("verifierSante : serveur en panne, erreur HTTP ou réponse illisible laissent le bandeau tel quel", async () => {
  repartir();
  globalThis.fetch = async () => reponse(200, { problemes: [{ cle: "voix", niveau: "erreur", message: "M" }] });
  await bandeau.verifierSante();
  for (const faux of [async () => { throw new TypeError("x"); }, async () => reponse(503, { problemes: [] }),
                      async () => reponse(200, undefined)]) {
    globalThis.fetch = faux;
    await bandeau.verifierSante();
    assert.ok(cles().includes("sante:voix"), "l'alerte du dernier diagnostic reste");
  }
  repartir();
});

test("fermer une alerte du serveur : elle ne revient pas, sauf si son message change", async () => {
  repartir();
  const probleme = (message) => ({ cle: "voix", niveau: "avertissement", message });
  globalThis.fetch = async () => reponse(200, { problemes: [probleme("Pas de voix")] });
  await bandeau.verifierSante();
  cliquerSur("sante:voix");
  assert.deepEqual(cles(), []);
  assert.deepEqual(JSON.parse(stock["alertes-fermees"]), ["sante:voix|Pas de voix"]);
  await bandeau.verifierSante();
  assert.deepEqual(cles(), []);  // même message : reste fermée
  globalThis.fetch = async () => reponse(200, { problemes: [probleme("Voix absente ou réseau coupé")] });
  await bandeau.verifierSante();
  assert.deepEqual(cles(), ["sante:voix"]);  // message différent : elle revient
  repartir();
});

test("fermer une alerte d'action : retirée, rien n'est mémorisé ; clic ailleurs ignoré", () => {
  repartir();
  bandeau.signaler("Micro refusé", { cle: "micro" });
  clic({ target: { closest: () => null } });
  clic({ target: {} });
  assert.deepEqual(cles(), ["micro"]);
  cliquerSur("micro");
  assert.deepEqual(cles(), []);
  assert.equal(stock["alertes-fermees"], undefined);
  cliquerSur("inconnue");  // déjà partie : sans effet
  repartir();
});

test("sessionStorage illisible ou plein : le bandeau marche quand même", async () => {
  repartir();
  globalThis.sessionStorage = { getItem: () => { throw new Error("bloqué"); }, setItem: () => { throw new Error("plein"); } };
  globalThis.fetch = async () => reponse(200, { problemes: [{ cle: "voix", niveau: "erreur", message: "M" }] });
  await bandeau.verifierSante();
  assert.deepEqual(cles(), ["sante:voix"]);
  cliquerSur("sante:voix");
  assert.deepEqual(cles(), []);
  globalThis.sessionStorage = { getItem: (k) => stock[k] ?? null, setItem: (k, v) => { stock[k] = v; }, removeItem() {} };
  repartir();
});
