// Tests des fonctions pures de la page de jeu (src/pnj_parlant/static/js/scene.js).
// Lancement : node --test tests/js/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// Le module est chargé depuis son texte : Node le traite ainsi en module ES sans package.json.
const source = readFileSync(new URL("../../src/pnj_parlant/static/js/scene.js", import.meta.url), "utf8");
const scene = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

const YSOLDE = { nom: "Ysolde la Rousse", metier: "aubergiste", apparence: "Trapue." };
const BROM = { nom: "Brom Œil-de-Fer", metier: "forgeron du village", apparence: "Immense." };

test("segments : narration entre parenthèses et répliques", () => {
  assert.deepEqual(scene.segments("(Il sourit.) Bienvenue ! (Il tousse.) Entrez."),
    [["Il sourit.", true], ["Bienvenue !", false], ["Il tousse.", true], ["Entrez.", false]]);
  assert.deepEqual(scene.segments("Bonjour."), [["Bonjour.", false]]);
  // réponse coupée avant la parenthèse fermante
  assert.deepEqual(scene.segments("Je vous dis (en chuchotant"), [["Je vous dis", false], ["en chuchotant", true]]);
  // morceaux sans lettre ni chiffre ignorés
  assert.deepEqual(scene.segments("( ) Rien. ..."), [["Rien. ...", false]]);
});

test("formatLine : descriptions en italique, HTML échappé", () => {
  assert.equal(scene.formatLine("(Il sourit.) <b>Salut</b>"),
    '<em class="narration">(Il sourit.)</em> &lt;b&gt;Salut&lt;/b&gt;');
});

test("interpelles : par le nom ou le métier, dans l'ordre cité", () => {
  const noms = (texte) => scene.interpelles(texte, [YSOLDE, BROM]).map(n => n.nom);
  assert.deepEqual(noms("Ysolde, une bière !"), ["Ysolde la Rousse"]);
  assert.deepEqual(noms("Et toi le forgeron ?"), ["Brom Œil-de-Fer"]);
  assert.deepEqual(noms("Où est la rousse ?"), ["Ysolde la Rousse"]);
  assert.deepEqual(noms("Brom, Ysolde, vous en pensez quoi ?"), ["Brom Œil-de-Fer", "Ysolde la Rousse"]);
  assert.deepEqual(noms("Bonjour à tous"), []);
  assert.deepEqual(noms("Brommmm ?"), []);  // mot entier seulement
  assert.deepEqual(noms("YSOLDE !"), ["Ysolde la Rousse"]);
});

test("questionnes : le PNJ à qui un autre pose une question", () => {
  const LEONARD = { nom: "Léonard le Sage", metier: "alchimiste" };
  const BERTHE = { nom: "Berthe la joyeuse", metier: "aubergiste" };
  const noms = (reply) => scene.questionnes(reply, BERTHE, [BERTHE, LEONARD]).map(n => n.nom);
  assert.deepEqual(noms("Et toi-même ? (À Léonard) Et pour toi, Léonard ? Toujours tes potions ?"), ["Léonard le Sage"]);
  assert.deepEqual(noms("Léonard est un vieux fou. Une bière, voyageur ?"), []);  // la question n'est pas pour lui
  assert.deepEqual(noms("L'alchimiste te le dira, hein ?"), ["Léonard le Sage"]);
  assert.deepEqual(noms("Berthe ? C'est moi."), []);  // pas soi-même
  assert.deepEqual(noms("Léonard, viens ici."), []);
});

test("lieuEvoque : un verbe de déplacement et un lieu cité", () => {
  const lieux = [{ id: "auberge", nom: "Auberge du Sanglier" }, { id: "forge", nom: "Forge de Brom" },
                 { id: "porte", nom: "La porte nord" }];
  const ou = (texte, actuel = "auberge") => scene.lieuEvoque(texte, lieux, actuel)?.id ?? null;
  assert.equal(ou("Allons voir Brom à la forge !"), "forge");
  assert.equal(ou("Emmène-moi à la porte nord, vite."), "porte");
  assert.equal(ou("Je vais à la Forge."), "forge");
  assert.equal(ou("La forge est loin ?"), null);              // pas de déplacement demandé
  assert.equal(ou("Retournons à l'auberge."), null);          // on y est déjà
  assert.equal(ou("Retournons à l'auberge.", "forge"), "auberge");
  assert.equal(ou("Allons dans la cave."), null);             // lieu inconnu
  assert.equal(ou("Allons au sanglier puis à la forge.", "porte"), "auberge", "le premier cité");
});

test("arrivee : texte du narrateur", () => {
  const lieu = { nom: "Forge de Brom", description: "Une chaleur d'enfer." };
  assert.equal(scene.arrivee(lieu), "(Vous arrivez : Forge de Brom. Une chaleur d'enfer.)");
  assert.equal(scene.arrivee({ nom: "Porte nord" }, [{ nom: "Ysolde" }]), "(Ysolde reste derrière. Vous arrivez : Porte nord.)");
  assert.equal(scene.arrivee(lieu, [{ nom: "A" }, { nom: "B" }]).slice(0, 26), "(A et B restent derrière. ");
});

test("position et parLieu : où se trouvent les PNJ", () => {
  const lieux = [{ id: "auberge", nom: "Auberge" }, { id: "forge", nom: "Forge" }];
  const pnjs = [{ nom: "Ysolde", lieu: "auberge" }, { nom: "Brom", lieu: "forge" },
                { nom: "Gaspard" }, { nom: "Fantôme", lieu: "cave" }];
  assert.equal(scene.position(pnjs[0], lieux), "auberge");
  assert.equal(scene.position(pnjs[0], lieux, { Ysolde: "forge" }), "forge");  // emmenée à la forge
  assert.equal(scene.position(pnjs[2], lieux), "");
  assert.equal(scene.position(pnjs[3], lieux), "");                            // lieu supprimé
  const groupes = (pos, actuel) => scene.parLieu(pnjs, lieux, pos, actuel)
    .map(g => [g.lieu?.id ?? null, g.pnjs.map(p => p.nom)]);
  assert.deepEqual(groupes({}), [["auberge", ["Ysolde"]], ["forge", ["Brom"]], [null, ["Gaspard", "Fantôme"]]]);
  assert.deepEqual(groupes({ Ysolde: "forge" }, "forge"), [["forge", ["Ysolde", "Brom"]], [null, ["Gaspard", "Fantôme"]]]);
});

test("memeVoix : même nom et même locuteur", () => {
  assert.ok(scene.memeVoix({ name: "a" }, { name: "a" }));
  assert.ok(!scene.memeVoix({ name: "a", speaker: 0 }, { name: "a", speaker: 1 }));
  assert.ok(!scene.memeVoix(undefined, undefined));
});

test("consignesEntree : scène, personne demandée et conversation récente", () => {
  const history = [{ speaker: "Ysolde la Rousse", content: "Mon cousin Gaspard arrive." },
                   { speaker: null, content: "Qui ça ?" }];
  const texte = scene.consignesEntree(history, [YSOLDE], "le cousin");
  assert.match(texte, /où se trouvent Ysolde la Rousse \(aubergiste\) et un voyageur/);
  assert.match(texte, /Qui entre : le cousin\./);
  assert.match(texte, /Ysolde la Rousse : Mon cousin Gaspard arrive\.\nVoyageur : Qui ça \?/);
  assert.match(scene.consignesEntree(history, [YSOLDE]), /de préférence une personne évoquée/);
});

test("export : en-tête, répliques et nom de fichier", () => {
  const date = new Date(2026, 10, 10, 18, 5);
  const texte = scene.texteExport([["Ysolde la Rousse", "(Elle rit.) Oui."], ["Vous", "Merci."]], [YSOLDE, BROM], date);
  assert.ok(texte.startsWith("Conversation avec Ysolde la Rousse, aubergiste ; Brom Œil-de-Fer, forgeron du village\n"
    + "Ysolde la Rousse : Trapue.\nBrom Œil-de-Fer : Immense.\n"));
  assert.ok(texte.endsWith("Ysolde la Rousse : (Elle rit.) Oui.\n\nVous : Merci.\n"));
  assert.ok(scene.texteExport([["", "(Vous arrivez : Forge.)"]], [YSOLDE], date).endsWith("\n\n(Vous arrivez : Forge.)\n"));
  assert.equal(scene.nomFichierExport([YSOLDE], date), "conversation-ysolde-la-rousse-2026-11-10-18h05.txt");
  assert.match(scene.texteExport([], [YSOLDE], date, "Forge de Brom"), /Trapue\.\nLieu : Forge de Brom\n/);
});

test("lireExport : relit un export (aller-retour)", () => {
  const date = new Date(2026, 10, 10, 18, 5);
  const lignes = [["Ysolde la Rousse", "(Elle rit.) Bienvenue !"], ["Vous", "Brom, une épée ?"],
                  ["Brom Œil-de-Fer", "Ysolde la Rousse : ce nom ne commence pas une réplique de Brom."],
                  ["", "(Ysolde la Rousse reste derrière. Vous arrivez : Forge de Brom. Il fait chaud.)"]];
  const lu = scene.lireExport(String.fromCharCode(0xFEFF)
    + scene.texteExport(lignes, [YSOLDE, BROM], date, "Forge de Brom").replace(/\n/g, "\r\n"));
  assert.deepEqual(lu.pnjs, [{ nom: "Ysolde la Rousse", metier: "aubergiste", apparence: "Trapue." },
                             { nom: "Brom Œil-de-Fer", metier: "forgeron du village", apparence: "Immense." }]);
  assert.deepEqual(lu.lignes, lignes);
  assert.equal(lu.lieu, "Forge de Brom");
  // un seul PNJ : l'apparence est la ligne suivante ; sans ligne « Lieu », celui de la dernière arrivée
  const seul = scene.lireExport(scene.texteExport([["", "(Vous arrivez : Porte nord.)"], ["Ysolde la Rousse", "Ah."]],
                                                  [YSOLDE], date));
  assert.deepEqual(seul.pnjs, [{ nom: "Ysolde la Rousse", metier: "aubergiste", apparence: "Trapue." }]);
  assert.equal(seul.lieu, "Porte nord");
  assert.throws(() => scene.lireExport("Liste de courses\n\npain"), /pas une conversation exportée/);
});

test("sceneImportee : qui est encore là à la fin de la conversation", () => {
  const L = (...qui) => qui.map(q => q.startsWith("(") ? ["", q] : [q, "…"]);
  assert.deepEqual(scene.sceneImportee(L("A", "Vous", "B", "A")), ["A", "B"]);
  assert.deepEqual(scene.sceneImportee(L("A", "B", "(A reste derrière. Vous arrivez : Forge.)", "Vous", "B")), ["B"]);
  assert.deepEqual(scene.sceneImportee(L("A", "(Vous arrivez : Forge.)", "Vous")), []);  // arrivé seul
  assert.deepEqual(scene.sceneImportee(L("A", "B", "C", "D", "B"), 3), ["B", "C", "D"]);
});

test("consignesRecreation : nom, métier, apparence et répliques du PNJ", () => {
  const texte = scene.consignesRecreation(YSOLDE, [["Ysolde la Rousse", "La bière est bonne."], ["Vous", "Merci."]]);
  assert.match(texte, /garde exactement son nom \(Ysolde la Rousse\) et son métier \(aubergiste\)/);
  assert.match(texte, /Apparence : Trapue\./);
  assert.match(texte, /- La bière est bonne\./);
  assert.doesNotMatch(texte, /Merci/);
});

test("detecteurVoix : voix soutenue au-dessus du bruit de fond, pas les bruits brefs", () => {
  // niveaux échantillonnés toutes les 50 ms à partir de t = 0
  const suite = (d, niveaux) => niveaux.map((n, i) => d.ajouter(n, i * 50));
  const bruit = Array(10).fill(0.005);  // 500 ms de calibrage : bruit 0,005, seuil 0,02

  let d = scene.detecteurVoix();
  assert.deepEqual(suite(d, [...bruit, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]),
    [...Array(16).fill(false), true]);  // 300 ms de voix
  assert.equal(d.bruit, 0.005);
  assert.equal(d.seuil, 0.02);

  d = scene.detecteurVoix();  // claquement de 100 ms, puis silence
  assert.ok(!suite(d, [...bruit, 0.5, 0.5, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005]).some(Boolean));

  d = scene.detecteurVoix();  // creux de 100 ms toléré au milieu de la voix
  assert.equal(suite(d, [...bruit, 0.1, 0.1, 0.1, 0.01, 0.01, 0.1, 0.1]).at(-1), true);

  d = scene.detecteurVoix();  // creux trop long : on repart de zéro
  assert.equal(suite(d, [...bruit, 0.1, 0.1, 0.1, 0.01, 0.01, 0.01, 0.01, 0.1, 0.1]).at(-1), false);

  d = scene.detecteurVoix();  // pièce silencieuse : le plancher évite de déclencher sur un souffle
  assert.ok(!suite(d, [...Array(10).fill(0), ...Array(10).fill(0.008)]).some(Boolean));
  assert.ok(!scene.detecteurVoix().ajouter(1, 0));  // rien pendant le calibrage
});

// --- univers.js : messages de l'import et de l'accueil ---------------------------------
const sourceUnivers = readFileSync(new URL("../../src/pnj_parlant/static/js/univers.js", import.meta.url), "utf8");
const univers = await import(`data:text/javascript;base64,${Buffer.from(sourceUnivers).toString("base64")}`);

test("univers : fichiers importables, résumés et confirmation", () => {
  const noms = univers.fichiersImportables([{ name: "a.json" }, { name: "B.ZIP" }, { name: "photo.png" }]).map(f => f.name);
  assert.deepEqual(noms, ["a.json", "B.ZIP"]);
  assert.equal(univers.resumeImport({ scenario: true, lieux: 3, pnj: 1, ignores: [] }), "Univers chargé : 3 lieux et 1 PNJ.");
  assert.equal(univers.resumeImport({ scenario: false, lieux: 1, pnj: 5, ignores: ["x.json"] }),
    "Univers chargé : 1 lieu et 5 PNJ, sans texte d’univers. Fichiers ignorés : x.json.");
  assert.equal(univers.resumeUnivers(2, 0), "Univers actuel : 2 lieux et 0 PNJ.");
  assert.match(univers.resumeUnivers(0, 0), /^Aucun univers chargé/);
  assert.match(univers.confirmationImport(4, false), /4 PNJ de la banque seront remplacés/);
  assert.match(univers.confirmationImport(4, true), /s’ajouteront/);
});
