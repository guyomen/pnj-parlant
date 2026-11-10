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
  assert.equal(scene.nomFichierExport([YSOLDE], date), "conversation-ysolde-la-rousse-2026-11-10-18h05.txt");
});
