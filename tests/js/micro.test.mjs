// Tests du micro du joueur (src/pnj_parlant/static/js/micro.js) : niveau, fin de parole, ouverture de l'analyse.
import assert from "node:assert/strict";
import { test } from "node:test";

const micro = await import(new URL("../../src/pnj_parlant/static/js/micro.js", import.meta.url));

test("niveauRms : moyenne quadratique des échantillons", () => {
  assert.equal(micro.niveauRms(new Float32Array([0, 0, 0])), 0);
  assert.equal(micro.niveauRms(new Float32Array([0.5, -0.5, 0.5, -0.5])), 0.5);
  assert.ok(Math.abs(micro.niveauRms([1, 0]) - Math.SQRT1_2) < 1e-9);
  assert.equal(micro.niveauRms([]), 0);
});

test("barreNiveau : vingt crans au plus", () => {
  assert.equal(micro.barreNiveau(0), "");
  assert.equal(micro.barreNiveau(0.01), "▮▮");
  assert.equal(micro.barreNiveau(1), "▮".repeat(20));
});

test("contraintes du micro : écho, bruit et gain traités par le navigateur", () => {
  assert.deepEqual(micro.CONTRAINTES_MICRO, { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
});

// Rejoue des niveaux toutes les 100 ms (comme la minuterie de listenLocal) ; renvoie l'instant de l'arrêt
function rejouer(suivi, niveaux, pas = 100) {
  for (let i = 0; i < niveaux.length; i++) if (suivi.ajouter(niveaux[i], (i + 1) * pas)) return (i + 1) * pas;
  return null;
}

test("suiviEcoute : voix au-dessus du bruit de fond, arrêt après 1,2 s de silence", () => {
  const suivi = micro.suiviEcoute({ debut: 0 });
  // calibration (0,5 s) sur un bruit de 0,01 → seuil 0,03 ; voix à 0,1 de 0,6 à 1,5 s, puis bruit
  const niveaux = [...Array(5).fill(0.01), ...Array(10).fill(0.1), ...Array(20).fill(0.02)];
  assert.equal(rejouer(suivi, niveaux), 1500 + 1300);  // dernier son à 1,5 s, plus de 1 200 ms après
  assert.equal(suivi.entendu, true);
  assert.equal(suivi.muet(), false);
  assert.ok(Math.abs(suivi.bruit - 0.01) < 1e-9);
});

test("suiviEcoute : le bruit pendant la calibration n'est pas pris pour la voix", () => {
  const suivi = micro.suiviEcoute({ debut: 0 });
  assert.equal(rejouer(suivi, Array(5).fill(0.2)), null);
  assert.equal(suivi.entendu, false);
  assert.equal(suivi.ajouter(0.5, 600), false);  // nettement au-dessus (seuil 0,6) : pas encore
  assert.equal(suivi.ajouter(0.7, 700), false);
  assert.equal(suivi.entendu, true);
});

test("suiviEcoute : seuil plancher, personne ne parle (8 s), durée maximale (30 s)", () => {
  const muet = micro.suiviEcoute({ debut: 0 });
  assert.equal(rejouer(muet, Array(100).fill(0.003)), 8100);  // sous le plancher 0,004 : jamais entendu
  assert.equal(muet.muet(), false);  // un signal faible n'est pas un micro muet : Whisper tranchera
  const coupe = micro.suiviEcoute({ debut: 0 });
  assert.equal(rejouer(coupe, Array(100).fill(0)), 8100);
  assert.equal(coupe.muet(), true);
  const bavard = micro.suiviEcoute({ debut: 0 });
  assert.equal(rejouer(bavard, [...Array(5).fill(0.01), ...Array(400).fill(0.1)]), 30100);  // parle sans arrêt
});

test("suiviEcoute : après une coupure de parole, voix déjà entendue et bruit déjà mesuré", () => {
  const suivi = micro.suiviEcoute({ debut: 0, dejaEntendu: true, bruit: 0.05 });
  assert.equal(suivi.entendu, true);
  assert.equal(suivi.ajouter(0.1, 100), false);  // sous le seuil (0,15) : silence qui court depuis le début
  assert.equal(rejouer(micro.suiviEcoute({ debut: 0, dejaEntendu: true, bruit: 0.05 }), Array(20).fill(0.1)), 1300);
  const reprend = micro.suiviEcoute({ debut: 0, dejaEntendu: true, bruit: 0.05 });
  assert.equal(reprend.ajouter(0.2, 100), false);  // au-dessus dès le début : pas de calibration
  assert.equal(reprend.dernierSon, 100);
});

// Faux AudioContext : enregistre ce qui est créé, fermé ; `echec` fait échouer resume()
function fauxAudio({ etat = "running", echec = null } = {}) {
  const journal = [];
  class AudioContext {
    constructor(opts) { journal.push(["ctx", opts]); this.state = etat; }
    async resume() { journal.push(["resume"]); if (echec) throw echec; }
    createAnalyser() { return { fftSize: 4, getFloatTimeDomainData: (t) => t.set([0.5, -0.5, 0.5, -0.5]) }; }
    createMediaStreamSource(stream) { return { connect: (a) => journal.push(["connect", stream.nom, a.fftSize]) }; }
    async close() { journal.push(["close"]); }
  }
  return { AudioContext, journal };
}
const flux = (sampleRate) => ({ nom: "micro", getAudioTracks: () => [{ getSettings: () => ({ sampleRate }) }] });

test("ouvrirAnalyse : contexte à la fréquence du micro, niveau lu sur l'analyseur", async () => {
  const { AudioContext, journal } = fauxAudio({ etat: "suspended" });
  const a = await micro.ouvrirAnalyse(flux(48000), { AudioContext });
  assert.deepEqual(journal, [["ctx", { sampleRate: 48000 }], ["resume"], ["connect", "micro", 4]]);
  assert.equal(a.niveau(), 0.5);
  const sans = fauxAudio();
  await micro.ouvrirAnalyse(flux(undefined), { AudioContext: sans.AudioContext });
  assert.deepEqual(sans.journal[0], ["ctx", undefined]);  // fréquence inconnue : celle par défaut
});

test("ouvrirAnalyse : en cas d'échec, le contexte est refermé et l'erreur transmise", async () => {
  const { AudioContext, journal } = fauxAudio({ etat: "suspended", echec: new Error("refus") });
  await assert.rejects(micro.ouvrirAnalyse(flux(16000), { AudioContext }), { message: "refus" });
  assert.deepEqual(journal.at(-1), ["close"]);
});
