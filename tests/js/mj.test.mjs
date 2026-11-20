// Tests du mode MJ (src/pnj_parlant/static/js/mj.js) : ouverture selon /api/acces, mot de passe vérifié par
// /api/reglages/verifier, mode gardé dans sessionStorage et annoncé. fetch, sessionStorage et la fenêtre du mot de
// passe sont remplacés ; pas de document (le module n'y touche que s'il existe).
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

const stockage = new Map();
globalThis.sessionStorage = {
  getItem: (c) => (stockage.has(c) ? stockage.get(c) : null),
  setItem: (c, v) => stockage.set(c, String(v)),
  removeItem: (c) => stockage.delete(c),
};
const mj = await import(new URL("../../src/pnj_parlant/static/js/mj.js", import.meta.url));
const api = await import(new URL("../../src/pnj_parlant/static/js/api.js", import.meta.url));

// Faux serveur : /api/acces renvoie `acces` ; /api/reglages/verifier accepte `bon` (sinon 403, ou `statut`)
function serveur({ acces, bon = "secret", statut = 403, erreur = "Mot de passe du MJ incorrect." }) {
  const appels = [];
  globalThis.fetch = async (url, opts = {}) => {
    appels.push([url, opts.body ? JSON.parse(opts.body) : null]);
    if (url === "/api/acces") return { ok: true, status: 200, json: async () => acces };
    const ok = JSON.parse(opts.body).mot_de_passe === bon;
    return { ok, status: ok ? 200 : statut, json: async () => (ok ? { ok: true } : { error: erreur }) };
  };
  return appels;
}
// Fenêtre du mot de passe : rend les réponses dans l'ordre (null = Annuler) et garde les questions posées
function saisies(...reponses) {
  const questions = [];
  api.poserDialogueMdp(async (message) => { questions.push(message); return reponses.shift() ?? null; });
  return questions;
}

beforeEach(() => stockage.clear());

test("ouvertureMJ et modeEncoreValide : selon le mot de passe du MJ et l'appareil", () => {
  assert.equal(mj.ouvertureMJ({ protege: true, local: true }), "mot_de_passe");  // exigé même sur le PC
  assert.equal(mj.ouvertureMJ({ protege: false, local: true }), "libre");
  assert.equal(mj.ouvertureMJ({ protege: false, local: false }), "impossible");
  assert.equal(mj.modeEncoreValide({ protege: true, local: false }, "secret"), true);
  assert.equal(mj.modeEncoreValide({ protege: true, local: true }, ""), false);  // mot de passe oublié ou ajouté depuis
  assert.equal(mj.modeEncoreValide({ protege: false, local: true }, ""), true);
  assert.equal(mj.modeEncoreValide({ protege: false, local: false }, "vieux"), false);  // mot de passe retiré
});

test("poserModeMJ : gardé pour l'onglet ; le quitter oublie le mot de passe du MJ", () => {
  assert.equal(mj.modeMJ(), false);
  mj.poserModeMJ(true);
  assert.equal(mj.modeMJ(), true);
  api.garderMdp("secret");
  mj.poserModeMJ(false);
  assert.equal(mj.modeMJ(), false);
  assert.equal(api.mdpMJ(), "");
});

test("connecterMJ : PC du serveur sans mot de passe = mode MJ sans rien demander", async () => {
  const appels = serveur({ acces: { mj: true, protege: false, local: true } });
  const questions = saisies();
  assert.deepEqual(await mj.connecterMJ(), { ok: true });
  assert.equal(mj.modeMJ(), true);
  assert.deepEqual(questions, []);
  assert.deepEqual(appels.map(a => a[0]), ["/api/acces"]);
});

test("connecterMJ : autre appareil sans mot de passe défini = refus expliqué", async () => {
  serveur({ acces: { mj: false, protege: false, local: false } });
  saisies("secret");
  assert.deepEqual(await mj.connecterMJ(), { ok: false, message: mj.MESSAGE_SANS_MDP });
  assert.equal(mj.modeMJ(), false);
});

test("connecterMJ : mot de passe demandé, redemandé s'il est faux, puis gardé", async () => {
  const appels = serveur({ acces: { mj: false, protege: true, local: false } });
  const questions = saisies("faux", "secret");
  assert.deepEqual(await mj.connecterMJ(), { ok: true });
  assert.equal(mj.modeMJ(), true);
  assert.equal(api.mdpMJ(), "secret");
  assert.deepEqual(questions, ["Mot de passe du MJ :", "Mot de passe du MJ incorrect. Réessayez :"]);
  assert.deepEqual(appels.slice(1).map(a => a[1].mot_de_passe), ["faux", "secret"]);
});

test("connecterMJ : mot de passe déjà gardé (préparation) essayé sans rien demander", async () => {
  serveur({ acces: { mj: true, protege: true, local: true } });
  api.garderMdp("secret");
  const questions = saisies();
  assert.deepEqual(await mj.connecterMJ(), { ok: true });
  assert.deepEqual(questions, []);
});

test("connecterMJ : « Annuler » = mode joueur, mot de passe refusé oublié", async () => {
  serveur({ acces: { mj: false, protege: true, local: false } });
  api.garderMdp("ancien");
  saisies(null);
  assert.deepEqual(await mj.connecterMJ(), { ok: false });
  assert.equal(mj.modeMJ(), false);
  assert.equal(api.mdpMJ(), "");
});

test("connecterMJ : trop d'essais (429) = message du serveur, sans redemander", async () => {
  serveur({ acces: { mj: false, protege: true, local: false }, statut: 429,
            erreur: "Trop d’essais de mot de passe : réessayez dans 5 s." });
  const questions = saisies("faux", "secret");
  assert.deepEqual(await mj.connecterMJ(), { ok: false, message: "Trop d’essais de mot de passe : réessayez dans 5 s." });
  assert.equal(questions.length, 1);
  assert.equal(mj.modeMJ(), false);
});
