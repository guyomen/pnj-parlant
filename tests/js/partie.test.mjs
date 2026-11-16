// Tests de la partie en cours et de ses transitions (src/pnj_parlant/static/js/partie.js).
import assert from "node:assert/strict";
import { test } from "node:test";

const P = await import(new URL("../../src/pnj_parlant/static/js/partie.js", import.meta.url));
const { VERSION_PARTIE, partieValide } = await import(new URL("../../src/pnj_parlant/static/js/scene.js", import.meta.url));

const LIEUX = [{ id: "auberge", nom: "Auberge" }, { id: "forge", nom: "Forge" }];
const fiche = (nom, autres = {}) => ({ nom, salutation: `Je suis ${nom}.`, ...autres });

test("nouvellePartie / vider : une partie vide, remise à zéro sur place", () => {
  const p = P.nouvellePartie();
  assert.deepEqual(p, { npcs: [], history: [], dernier: null, rencontres: [], lieuActuel: "", positions: {} });
  P.nouvelleScene(p, fiche("Ysolde", { lieu: "auberge" }), LIEUX);
  const meme = p;
  P.vider(p);
  assert.equal(p, meme);
  assert.deepEqual(p, P.nouvellePartie());
});

test("nouvelleScene : le PNJ seul, sa salutation, et la scène là où il se trouve", () => {
  const p = P.nouvellePartie();
  const ysolde = fiche("Ysolde", { lieu: "auberge" });
  P.nouvelleScene(p, ysolde, LIEUX);
  assert.deepEqual(p.npcs, [ysolde]);
  assert.deepEqual(p.history, [{ speaker: "Ysolde", content: "Je suis Ysolde." }]);
  assert.equal(p.dernier, ysolde);
  assert.deepEqual(p.rencontres, [ysolde]);
  assert.equal(p.lieuActuel, "auberge");
  assert.deepEqual(p.positions, { Ysolde: "auberge" });
  // Brom a suivi le voyageur à l'auberge pendant la partie : on va le voir là-bas, pas à sa forge
  p.positions.Brom = "auberge";
  P.nouvelleScene(p, fiche("Brom", { lieu: "forge" }), LIEUX);
  assert.equal(p.lieuActuel, "auberge");
  // lieu inconnu (supprimé du scénario) : la scène reste où elle est
  P.nouvelleScene(p, fiche("Léo", { lieu: "tour" }), LIEUX);
  assert.equal(p.lieuActuel, "auberge");
  assert.equal(p.positions["Léo"], "auberge");
  const sansLieu = P.nouvellePartie();
  P.nouvelleScene(sansLieu, fiche("Léo"), LIEUX);
  assert.equal(sansLieu.lieuActuel, "");
  assert.deepEqual(sansLieu.positions, {});
});

test("rejoindre : il salue, devient le dernier à parler, rencontré une seule fois", () => {
  const p = P.nouvellePartie();
  const ysolde = fiche("Ysolde", { lieu: "auberge" }), brom = fiche("Brom");
  P.nouvelleScene(p, ysolde, LIEUX);
  P.rejoindre(p, brom);
  assert.deepEqual(p.npcs, [ysolde, brom]);
  assert.deepEqual(p.history.at(-1), { speaker: "Brom", content: "Je suis Brom." });
  assert.equal(p.dernier, brom);
  assert.equal(p.positions.Brom, "auberge");
  P.retirer(p, 1);
  P.rejoindre(p, { ...brom });  // revient : pas une deuxième rencontre
  assert.equal(p.rencontres.length, 2);
});

test("retirer : il quitte la scène ; s'il parlait en dernier, le principal répondra", () => {
  const p = P.nouvellePartie();
  const ysolde = fiche("Ysolde"), brom = fiche("Brom"), leo = fiche("Léo");
  P.nouvelleScene(p, ysolde, LIEUX);
  P.rejoindre(p, brom);
  P.rejoindre(p, leo);
  assert.equal(P.retirer(p, 2), leo);
  assert.equal(p.dernier, ysolde);
  p.dernier = brom;
  P.retirer(p, 0);
  assert.equal(p.dernier, brom);  // pas lui : inchangé
  assert.equal(p.rencontres.length, 3);  // gardé pour l'export
});

test("changerDeLieu : les compagnons suivent avec la conversation, les autres restent sur place", () => {
  const p = P.nouvellePartie();
  const ysolde = fiche("Ysolde", { lieu: "auberge" }), brom = fiche("Brom", { suit: true });
  P.nouvelleScene(p, ysolde, LIEUX);
  P.rejoindre(p, brom);
  const { lieu, restent } = P.changerDeLieu(p, "forge", LIEUX);
  assert.deepEqual(lieu, LIEUX[1]);
  assert.deepEqual(restent, [ysolde]);
  assert.deepEqual(p.npcs, [brom]);
  assert.equal(p.dernier, brom);  // Brom avait parlé en dernier, il est encore là
  assert.equal(p.lieuActuel, "forge");
  assert.deepEqual(p.positions, { Ysolde: "auberge", Brom: "forge" });
  assert.deepEqual(p.history.at(-1), { speaker: null, content: "(Le voyageur et ses compagnons arrivent : Forge.)" });
  assert.equal(p.history.length, 3);
});

test("changerDeLieu : seul, la conversation repart de zéro ; « aucun lieu » sans narration", () => {
  const p = P.nouvellePartie();
  const ysolde = fiche("Ysolde", { lieu: "auberge" });
  P.nouvelleScene(p, ysolde, LIEUX);
  const r = P.changerDeLieu(p, "forge", LIEUX);
  assert.deepEqual(r.restent, [ysolde]);
  assert.deepEqual(p.npcs, []);
  assert.equal(p.dernier, null);
  assert.deepEqual(p.history, []);
  const compagnon = fiche("Brom", { suit: true });
  P.nouvelleScene(p, compagnon, LIEUX);  // forge
  const aucun = P.changerDeLieu(p, "", LIEUX);
  assert.equal(aucun.lieu, undefined);
  assert.equal(p.lieuActuel, "");
  assert.equal(p.positions.Brom, undefined);
  assert.equal(p.history.length, 1);  // pas de narration d'arrivée
});

test("reprendreImport : scène, dernier à avoir parlé, historique du fichier", () => {
  const p = P.nouvellePartie();
  const ysolde = fiche("Ysolde"), brom = fiche("Brom"), leo = fiche("Léo");
  const lignes = [["Ysolde", "Bonjour."], ["Vous", "Salut."], ["", "(Ils arrivent.)"], ["Brom", "Hm."], ["Léo", "La la."]];
  P.reprendreImport(p, lignes, [ysolde, brom, leo], [ysolde, brom], "forge");
  assert.deepEqual(p.rencontres, [ysolde, brom, leo]);
  assert.deepEqual(p.npcs, [ysolde, brom]);
  assert.equal(p.dernier, brom);  // Léo a parlé après, mais n'est plus en scène
  assert.equal(p.lieuActuel, "forge");
  assert.deepEqual(p.positions, { Ysolde: "forge", Brom: "forge" });
  assert.deepEqual(p.history.map(h => h.speaker), ["Ysolde", null, null, "Brom", "Léo"]);
  P.reprendreImport(p, lignes, [ysolde], [], "");
  assert.deepEqual(p.history, []);
  assert.equal(p.dernier, null);
});

test("instantane puis restaurer : la partie revient telle quelle (sauvegarde valide)", () => {
  const p = P.nouvellePartie();
  const ysolde = fiche("Ysolde", { id: "ysolde-0001", lieu: "auberge" }), brom = fiche("Brom", { suit: true });
  assert.equal(P.instantane(p, [], {}), null);  // rien à garder
  P.nouvelleScene(p, ysolde, LIEUX);
  P.rejoindre(p, brom);
  const s = JSON.parse(JSON.stringify(P.instantane(p, [["Ysolde", "Je suis Ysolde."]], { input: 5 })));
  assert.equal(s.version, VERSION_PARTIE);
  assert.deepEqual(s.scene, ["Ysolde", "Brom"]);
  assert.equal(s.dernier, "Brom");
  assert.ok(partieValide(s));
  const relue = { ...ysolde, humeur: "joyeuse" };  // fiche modifiée en préparation entre-temps
  const q = P.nouvellePartie();
  P.restaurer(q, s, [relue, null], LIEUX);
  assert.equal(q.npcs[0].humeur, "joyeuse");
  assert.equal(q.npcs[1].nom, "Brom");
  assert.equal(q.dernier, q.npcs[1]);
  assert.equal(q.lieuActuel, "auberge");
  assert.deepEqual(q.history, p.history);
  P.restaurer(q, s, [null, null], [LIEUX[1]]);  // l'auberge n'existe plus
  assert.equal(q.lieuActuel, "");
});

test("cumulerUsage : dernière réplique et cumul des tokens", () => {
  const c = P.compteurVide();
  assert.equal(c.available, false);
  P.cumulerUsage(c, { input_tokens: 100, output_tokens: 20 });
  P.cumulerUsage(c, { input_tokens: 150, output_tokens: 30 });
  assert.deepEqual(c, { input: 250, output: 50, lastInput: 150, lastOutput: 30, available: true });
});
