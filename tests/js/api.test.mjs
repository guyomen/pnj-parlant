// Tests d'apiStream (src/pnj_parlant/static/js/api.js) : réponse NDJSON de /api/npc/talk lue au fil de l'eau.
// fetch est remplacé par un faux qui renvoie un vrai ReadableStream, découpé en morceaux arbitraires.
import assert from "node:assert/strict";
import { test } from "node:test";

const { apiStream } = await import(new URL("../../src/pnj_parlant/static/js/api.js", import.meta.url));

// Flux d'octets découpé comme l'envoie le réseau ; `annule` dit si le lecteur a été relâché
function fauxFlux(morceaux, { status = 200, corps } = {}) {
  const etat = { annule: false, appels: [] };
  globalThis.fetch = async (url, opts) => {
    etat.appels.push([url, opts]);
    const body = new ReadableStream({
      pull(ctrl) {
        const m = morceaux.shift();
        if (m === undefined) ctrl.close(); else ctrl.enqueue(new TextEncoder().encode(m));
      },
      cancel() { etat.annule = true; },
    });
    return { ok: status < 400, status, body, json: async () => corps ?? {} };
  };
  return etat;
}

test("apiStream : objets rendus ligne par ligne, même coupés au milieu", async () => {
  const etat = fauxFlux(['{"phrase": "Bonjour', ' voyageur."}\n{"phr', 'ase": "Entr', "ez.\"}\n", '{"usage": {"input_tokens": 3}}']);
  const recus = [];
  await apiStream("/api/npc/talk", { npc: { nom: "Ysolde" } }, (o) => recus.push(o));
  assert.deepEqual(recus, [{ phrase: "Bonjour voyageur." }, { phrase: "Entrez." }, { usage: { input_tokens: 3 } }]);
  assert.equal(etat.appels[0][1].method, "POST");
  assert.equal(etat.appels[0][1].body, '{"npc":{"nom":"Ysolde"}}');
  assert.equal(etat.annule, false);  // flux lu jusqu'au bout
});

test("apiStream : caractère accentué coupé entre deux paquets", async () => {
  globalThis.fetch = async () => {
    const octets = new TextEncoder().encode('{"phrase": "Été."}\n');
    const morceaux = [octets.slice(0, 13), octets.slice(13)];  // « É » est sur deux octets : 12-13
    return { ok: true, status: 200, body: new ReadableStream({ pull(c) { const m = morceaux.shift(); if (m) c.enqueue(m); else c.close(); } }) };
  };
  const recus = [];
  await apiStream("/x", {}, (o) => recus.push(o));
  assert.deepEqual(recus, [{ phrase: "Été." }]);
});

test("apiStream : erreur du serveur avant le flux, en français", async () => {
  fauxFlux([], { status: 503, corps: { error: "Ollama ne répond pas." } });
  await assert.rejects(apiStream("/api/npc/talk", {}, () => {}), { message: "Ollama ne répond pas." });
});

test("apiStream : une erreur levée par onItem arrête la lecture et relâche le lecteur", async () => {
  const etat = fauxFlux(['{"error": "Panne."}\n', '{"phrase": "jamais lue"}\n']);
  const recus = [];
  await assert.rejects(apiStream("/x", {}, (o) => { recus.push(o); if (o.error) throw new Error(o.error); }),
                       { message: "Panne." });
  assert.deepEqual(recus, [{ error: "Panne." }]);
  assert.equal(etat.annule, true);  // la connexion se ferme
});

test("apiStream : ligne illisible = erreur en français, lecteur relâché", async () => {
  const etat = fauxFlux(["pas du json\n", '{"phrase": "x"}\n']);
  await assert.rejects(apiStream("/x", {}, () => {}), (e) => !/JSON|Unexpected/.test(e.message));
  assert.equal(etat.annule, true);
});

test("apiStream : signal transmis à fetch (Stop / Échap)", async () => {
  const etat = fauxFlux([]);
  const ctrl = new AbortController();
  await apiStream("/x", {}, () => {}, ctrl.signal);
  assert.equal(etat.appels[0][1].signal, ctrl.signal);
});
