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

test("adressePortrait : seulement pour un PNJ de la banque qui a un portrait", () => {
  assert.equal(scene.adressePortrait({ id: "brom-00a1", portrait: 1731400000123 }), "/api/bank/brom-00a1/portrait?v=1731400000123");
  assert.equal(scene.adressePortrait({ id: "brom-00a1", portrait: 0 }), "");
  assert.equal(scene.adressePortrait({ nom: "Inventé", portrait: 5 }), "");  // pas encore dans la banque
  assert.equal(scene.adressePortrait(null), "");
});

// --- univers.js : messages de l'import et de l'accueil ---------------------------------
// Chargé par son chemin (il importe api.js et bandeau.js) : le package.json de la racine en fait un module ES.
const univers = await import(new URL("../../src/pnj_parlant/static/js/univers.js", import.meta.url));
const api = await import(new URL("../../src/pnj_parlant/static/js/api.js", import.meta.url));

test("univers : fichiers importables, résumés et confirmation", () => {
  const noms = univers.fichiersImportables([{ name: "a.json" }, { name: "B.ZIP" }, { name: "brom-0001.png" },
    { name: "x.JPEG" }, { name: "notes.txt" }, { name: "Thumbs.db" }]).map(f => f.name);
  assert.deepEqual(noms, ["a.json", "B.ZIP", "brom-0001.png", "x.JPEG"]);  // fiches, archives et portraits
  assert.equal(univers.resumeImport({ scenario: true, lieux: 3, pnj: 1, ignores: [] }), "Univers chargé : 3 lieux et 1 PNJ.");
  assert.equal(univers.resumeImport({ scenario: false, lieux: 1, pnj: 5, ignores: ["x.json"] }),
    "Univers chargé : 1 lieu et 5 PNJ, sans texte d’univers. Fichiers ignorés : x.json.");
  assert.equal(univers.resumeUnivers(2, 0), "Univers actuel : 2 lieux et 0 PNJ.");
  assert.match(univers.resumeUnivers(0, 0), /^Aucun univers chargé/);
  assert.match(univers.confirmationImport(4, false), /4 PNJ de la banque seront remplacés/);
  assert.match(univers.confirmationImport(4, true), /s’ajouteront/);
  assert.match(univers.confirmationViderPartie(["Ysolde", "Brom"]), /^Une conversation est en cours avec Ysolde et Brom\. /);
  assert.match(univers.confirmationViderPartie([]), /^Une conversation est en cours\. .*Annuler : elle est gardée/);
});

// Faux navigateur pour les fonctions qui appellent le serveur : fetch(url) → réponses[url]
function fauxFetch(reponses) {
  const appels = [];
  globalThis.fetch = async (url, opts) => {
    appels.push([url, opts]);
    const r = reponses[url];
    if (r instanceof Error) throw r;
    return { ok: r.status < 400, status: r.status, json: async () => { if (r.corps === undefined) throw new SyntaxError("vide"); return r.corps; } };
  };
  return appels;
}

test("api : erreurs du serveur en français, serveur injoignable", async () => {
  const appels = fauxFetch({ "/a": { status: 200, corps: { ok: 1 } }, "/b": { status: 400, corps: { error: "Nom absent." } },
                             "/c": { status: 502 }, "/d": new TypeError("Failed to fetch") });
  assert.deepEqual(await api.api("/a", { x: 1 }), { ok: 1 });
  assert.equal(appels[0][1].method, "POST");
  assert.equal(appels[0][1].body, '{"x":1}');
  await assert.rejects(api.api("/b"), { message: "Nom absent." });
  await assert.rejects(api.api("/c", undefined, "GET", { panne: true }), { message: "Erreur serveur (502)" });
  await assert.rejects(api.api("/d"), { message: /^Serveur injoignable/ });  // pas « Failed to fetch »
  const abandon = Object.assign(new Error("abandon"), { name: "AbortError" });
  fauxFetch({ "/e": abandon });
  await assert.rejects(api.api("/e"), { name: "AbortError" });  // Stop / Échap : pas une panne
});

// Mot de passe du MJ : serveur simulé qui n'accepte que « dragée » (en-tête encodé), sessionStorage en mémoire
function serveurProtege() {
  const stock = {}, appels = [];
  globalThis.sessionStorage = { getItem: (k) => stock[k] ?? null, setItem: (k, v) => { stock[k] = v; },
                                removeItem: (k) => { delete stock[k]; } };
  globalThis.fetch = async (url, opts = {}) => {
    const mdp = opts.headers?.["X-Mot-De-Passe-MJ"];
    appels.push([url, mdp, opts.body]);
    const bon = mdp === encodeURIComponent("dragée");
    const corps = url === "/api/acces" ? { mj: bon, protege: true, local: false }
      : bon ? { ok: 1 } : { error: mdp ? "Mot de passe du MJ incorrect." : "Mot de passe du MJ demandé.", mot_de_passe: true };
    const status = url === "/api/acces" || bon ? 200 : 403;
    return { ok: status < 400, status, json: async () => corps };
  };
  return { stock, appels };
}

test("api : mot de passe du MJ demandé sur 403, gardé pour l'onglet, oublié s'il est refusé", async () => {
  const { stock, appels } = serveurProtege();
  const saisies = ["faux", "dragée"];
  const questions = [];
  api.poserDialogueMdp(async (message) => { questions.push(message); return saisies.shift() ?? null; });
  try {
    assert.deepEqual(await api.api("/api/bank", { nom: "Ysolde" }), { ok: 1 });
    assert.deepEqual(appels.map(a => a[1]), [undefined, "faux", encodeURIComponent("dragée")]);
    assert.ok(appels.every(a => a[2] === '{"nom":"Ysolde"}'));  // même corps à chaque essai
    assert.match(questions[0], /demande le mot de passe du MJ/);
    assert.match(questions[1], /incorrect/);
    assert.equal(stock["mdp-mj"], "dragée");  // la même clé que la page Options
    assert.deepEqual(await api.api("/api/univers", undefined, "DELETE"), { ok: 1 });  // gardé : pas de question
    assert.equal(questions.length, 2);
    stock["mdp-mj"] = "ancien";  // mot de passe changé sur le serveur : oublié, puis « Annuler »
    await assert.rejects(api.api("/api/bank", {}), { message: "Mot de passe du MJ incorrect." });
    assert.equal(stock["mdp-mj"], undefined);
    assert.equal(questions.length, 3);
  } finally { api.poserDialogueMdp(async () => null); delete globalThis.sessionStorage; }
});

test("api : un 403 sans demande de mot de passe est rendu tel quel", async () => {
  const appels = fauxFetch({ "/x": { status: 403, corps: { error: "Depuis le PC seulement." } } });
  let demande = false;
  api.poserDialogueMdp(async () => { demande = true; return "x"; });
  try {
    await assert.rejects(api.api("/x", {}), { message: "Depuis le PC seulement." });
    assert.equal(demande, false);
    assert.equal(appels.length, 1);
  } finally { api.poserDialogueMdp(async () => null); }
});

test("api : verifierAcces demande le mot de passe jusqu'à Annuler", async () => {
  const { stock } = serveurProtege();
  const saisies = ["dragée"];
  api.poserDialogueMdp(async () => saisies.shift() ?? null);
  try {
    assert.deepEqual(await api.verifierAcces(), { mj: true, protege: true, local: false });
    assert.equal(stock["mdp-mj"], "dragée");
    stock["mdp-mj"] = "ancien";
    assert.equal((await api.verifierAcces({ demander: false })).mj, false);
    assert.equal(stock["mdp-mj"], undefined);  // refusé : oublié
    assert.equal((await api.verifierAcces()).mj, false);  // « Annuler » : lecture seule
  } finally { api.poserDialogueMdp(async () => null); delete globalThis.sessionStorage; }
});

test("univers : nom du zip exporté", () => {
  assert.equal(univers.nomTelecharge('attachment; filename=scenario-2026-11-15-10h00.zip'), "scenario-2026-11-15-10h00.zip");
  assert.equal(univers.nomTelecharge('attachment; filename="a b.zip"'), "a b.zip");
  assert.equal(univers.nomTelecharge(null), "scenario.zip");
});

test("univers : thème gardé quand le serveur répond en erreur", async () => {
  const ecrits = {};
  globalThis.localStorage = { setItem: (k, v) => { ecrits[k] = v; } };
  globalThis.document = { documentElement: { dataset: { theme: "givre" } }, getElementById: () => null };
  try {
    fauxFetch({ "/api/scenario": { status: 500, corps: { error: "panne" } }, "/api/styles": { status: 500 } });
    assert.equal(await univers.chargerTheme(), "givre");
    assert.deepEqual(ecrits, {});  // le thème par défaut n'est ni appliqué ni mémorisé
    fauxFetch({ "/api/scenario": { status: 200, corps: { theme: "donjon" } }, "/api/styles": new TypeError("x") });
    assert.equal(await univers.chargerTheme(), "donjon");
    assert.equal(ecrits.theme, "donjon");
  } finally { delete globalThis.document; delete globalThis.localStorage; }
});

// --- univers.js : thèmes graphiques -------------------------------------------------------
test("thèmes : palettes identiques à style.css, toutes lisibles", () => {
  const css = readFileSync(new URL("../../src/pnj_parlant/static/style.css", import.meta.url), "utf8");
  const zone = css.slice(css.indexOf("/* Vert-de-gris"), css.indexOf("@media (max-width: 40rem)"));
  for (const t of univers.THEMES) {
    const sel = t.id === univers.THEME_DEFAUT ? ":root, [data-theme=vert-de-gris]" : `[data-theme=${t.id}]`;
    const blocs = zone.split(sel).slice(1).map(b => b.slice(b.indexOf("{") + 1, b.indexOf("}")));
    const palettes = blocs.map(b => Object.fromEntries([...b.matchAll(/--([\w-]+):\s*(#[0-9A-Fa-f]{6})/g)]
      .map(([, c, v]) => [c, v.toLowerCase()])));
    const attendues = t.mode === "auto" ? [t.clair, t.sombre] : [t[t.mode]];
    assert.deepEqual(palettes, attendues, t.id);
    for (const p of attendues) assert.deepEqual(univers.alertesContraste(p), [], t.id);
  }
});

test("thèmes : prédéfinis, modifiés et créés pour l'univers", () => {
  const forge = { nom: "Forge", resume: "", mode: "sombre", sombre: univers.THEMES[4].sombre };
  const tous = univers.tousLesThemes({ forge, parchemin: { ...univers.THEMES[1], nom: "Vieux parchemin" } });
  assert.deepEqual(tous.map(t => `${t.id}:${t.origine}`), ["vert-de-gris:predefini", "parchemin:modifie",
    "sylve:predefini", "givre:predefini", "donjon:predefini", "forge:perso"]);
  assert.equal(tous[1].nom, "Vieux parchemin");
  assert.equal(univers.tousLesThemes().length, 5);
});

test("thèmes : CSS des thèmes de l'univers", () => {
  const p = univers.THEMES[0];
  const css = univers.cssThemes({ forge: { mode: "auto", clair: p.clair, sombre: p.sombre },
                                  nuit: { mode: "sombre", sombre: p.sombre }, "../x": { mode: "sombre", sombre: p.sombre } });
  const lignes = css.split("\n");
  assert.equal(lignes.length, 3);  // forge : clair + sombre ; nuit : une palette ; « ../x » ignoré
  assert.match(lignes[0], /^html\[data-theme="forge"\], body \[data-theme="forge"\] \{ color-scheme: light; --bg: #dce3db;/);
  assert.match(lignes[1], /^@media \(prefers-color-scheme: dark\) \{ html\[data-theme="forge"\].* --bg: #121a17;/);
  assert.match(lignes[2], /data-theme="nuit"\] \{ color-scheme: dark; --bg: #121a17;.*--wax-ink: #fff4f0; --ombre:/);
  assert.equal(univers.cssThemes({}), "");
  // couleur ou mode inattendus (le serveur les refuse déjà) : thème ignoré, rien n'est injecté
  const piege = { ...p.sombre, bg: "red; } body { display: none" };
  assert.equal(univers.cssThemes({ a: { mode: "sombre", sombre: piege }, b: { mode: "auto", clair: p.clair },
                                   c: { mode: "x", x: p.sombre } }), "");
});

test("thèmes : contraste, alertes, identifiants", () => {
  assert.equal(Math.round(univers.contraste("#000000", "#ffffff")), 21);
  assert.equal(univers.contraste("#777777", "#777777"), 1);
  const illisible = { ...univers.THEMES[0].clair, ink: "#cfd6ce" };
  const quoi = univers.alertesContraste(illisible).map(a => a.quoi);
  assert.ok(quoi.includes("Texte sur le fond"));
  // anneau de focus : seuil de 3 (repère graphique), pas 4,5
  const focus = { ...univers.THEMES[0].clair, verdigris: "#6fa392" };
  assert.deepEqual(univers.alertesContraste(focus).map(a => [a.quoi, a.seuil]),
    [["Anneau de focus sur le fond", 3], ["Anneau de focus sur les cartes", 3]]);
  // cire des textes : mélange avec l'encre (comme color-mix en CSS)
  assert.equal(univers.melange("#000000", "#ffffff", 60), "#666666");
  assert.equal(univers.melange("#ff0000", "#0000ff", 100), "#ff0000");
  const cire = { ...univers.THEMES[0].sombre, wax: "#2a1010", ink: "#2b1111" };
  assert.ok(univers.alertesContraste(cire).some(a => a.quoi.startsWith("Texte en cire")));
  assert.equal(univers.identifiant("Forge noire !", []), "forge-noire");
  assert.equal(univers.identifiant("Parchemin", ["parchemin", "parchemin-2"]), "parchemin-3");
  assert.equal(univers.identifiant("Été brûlant", []), "ete-brulant");
  assert.equal(univers.identifiant("???", []), "perso");
});

test("options : valeur d'un champ, groupes utiles, résumé", () => {
  assert.equal(scene.valeurReglage("booleen", { checked: true }), true);
  assert.equal(scene.valeurReglage("entier", { value: " 12 " }), 12);
  assert.equal(scene.valeurReglage("nombre", { value: "0,5" }), 0.5);
  assert.equal(scene.valeurReglage("nombre", { value: "" }), null);
  assert.equal(scene.valeurReglage("entier", { value: "douze" }), null);
  assert.equal(scene.valeurReglage("texte", { value: "  qwen3:8b " }), "qwen3:8b");
  const valeurs = { "moteurs.creation": "claude", "moteurs.dialogue": "lmstudio" };
  assert.equal(scene.groupeUtile({ id: "voix" }, valeurs), true);
  assert.equal(scene.groupeUtile({ si: "claude" }, valeurs), true);
  assert.equal(scene.groupeUtile({ si: "lmstudio" }, valeurs), true);
  assert.equal(scene.groupeUtile({ si: "local" }, valeurs), false);
  assert.equal(scene.resumeModifs(0), "");
  assert.equal(scene.resumeModifs(1), "1 réglage modifié");
  assert.equal(scene.resumeModifs(3), "3 réglages modifiés");
});

test("NDJSON : lignes complètes, reste, ligne illisible", () => {
  assert.deepEqual(scene.decouperNdjson('{"phrase":"Un."}\n{"phrase":"De'), { objets: [{ phrase: "Un." }], reste: '{"phrase":"De' });
  assert.deepEqual(scene.decouperNdjson('\n{"usage":{}}\n\n'), { objets: [{ usage: {} }], reste: "" });
  assert.deepEqual(scene.decouperNdjson('{"phrase":"Fin."}', true), { objets: [{ phrase: "Fin." }], reste: "" });
  assert.deepEqual(scene.decouperNdjson("", true), { objets: [], reste: "" });
  assert.throws(() => scene.decouperNdjson("<html>\n"), { message: /^Réponse du serveur illisible/ });
});

test("partie gardée : sauvegarde valide ou rejetée", () => {
  const ok = { version: 1, rencontres: [YSOLDE], scene: ["Ysolde la Rousse"], dernier: null, lieuActuel: "",
               history: [{ speaker: null, content: "Bonjour" }, { speaker: "Ysolde la Rousse", content: "Salut" }],
               positions: {}, lignes: [["Vous", "Bonjour"], ["", "(Elle sourit.)"]], tokenUsage: { input: 3 } };
  assert.equal(scene.partieValide(ok), true);
  const { version, ...ancienne } = ok;
  assert.equal(scene.partieValide(ancienne), true);  // sauvegarde d'avant les versions : même forme
  for (const abimee of [null, 42, "texte", [], { ...ok, version: 2 }, { ...ok, rencontres: [] },
                        { ...ok, rencontres: [{ metier: "x" }] }, { ...ok, lignes: "x" }, { ...ok, lignes: [["Vous"]] },
                        { ...ok, scene: "Ysolde" }, { ...ok, history: [{ speaker: 3, content: "x" }] },
                        { ...ok, history: {} }, { ...ok, positions: [] }, { ...ok, lieuActuel: 5 },
                        { ...ok, dernier: {} }, { ...ok, tokenUsage: "x" }]) {
    assert.equal(scene.partieValide(abimee), false, JSON.stringify(abimee));
  }
});

test("partie restaurée : fiches relues sur le serveur", () => {
  const v = (name) => ({ name });
  const ysolde = { ...YSOLDE, id: "y", suit: true, voix: v("b"), humeur: "gaie" };  // voix réattribuée en partie
  const brom = { ...BROM, id: "b", voix: v("a") };
  const gaspard = { nom: "Gaspard", metier: "colporteur", voix: v("c") };          // inventé : pas dans la banque
  const relues = [{ ...YSOLDE, nom: "Ysolde (renommée)", id: "y", voix: v("a"), humeur: "furieuse" },
                  { ...BROM, id: "b", voix: v("d"), apparence: "Gigantesque." }, null];
  const [y, b, g] = scene.fichesRelues([ysolde, brom, gaspard], ["Brom Œil-de-Fer", "Ysolde la Rousse"], relues);
  assert.equal(y.humeur, "furieuse");                 // modifiée en préparation
  assert.equal(y.nom, "Ysolde la Rousse");            // le journal la cite sous ce nom
  assert.equal(y.suit, true);                         // accompagne toujours le voyageur
  assert.equal(b.apparence, "Gigantesque.");
  assert.equal(b.voix.name, "d");                     // nouvelle voix de la banque : reprise
  assert.equal(y.voix.name, "a");                     // la voix de la banque ne gêne plus personne (Brom a « d »)
  assert.equal(g, gaspard);                           // inventé, ou fiche supprimée : copie gardée
  // la voix de la banque se confond avec celle d'un PNJ de la scène placé avant : la voix réattribuée reste
  const [y2] = scene.fichesRelues([ysolde, brom], ["Brom Œil-de-Fer", "Ysolde la Rousse"],
                                  [relues[0], { ...relues[1], voix: v("a") }]);
  assert.equal(y2.voix.name, "b");
});

test("bandeau : ajout sans doublon, limite, problèmes du serveur", () => {
  let a = scene.ajouterAlerte([], { cle: "serveur", niveau: "erreur", message: "Injoignable" });
  a = scene.ajouterAlerte(a, { cle: "tts", niveau: "avertissement", message: "Voix" });
  a = scene.ajouterAlerte(a, { cle: "serveur", niveau: "erreur", message: "Toujours injoignable" });
  assert.deepEqual(a.map(x => x.message), ["Voix", "Toujours injoignable"]);  // même clé : remplacée, en dernier
  assert.equal(scene.ajouterAlerte(a, { cle: "c", message: "3" }, 2).length, 2);
  const sante = scene.alertesSante(a, [{ cle: "ollama", niveau: "erreur", message: "Ollama arrêté" },
                                      { cle: "voix", niveau: "avertissement", message: "Pas de voix" }],
                                   ["sante:voix|Pas de voix"]);
  assert.deepEqual(sante.map(x => x.cle), ["sante:ollama", "tts", "serveur"]);  // « voix » fermée par le joueur
  assert.deepEqual(scene.alertesSante(sante, []).map(x => x.cle), ["tts", "serveur"]);  // problème réglé : retiré
  assert.deepEqual(scene.alertesSante([], [{ cle: "voix", niveau: "avertissement", message: "Autre" }],
                                      ["sante:voix|Pas de voix"]).length, 1);  // message changé : revient
});

test("page ouverte en HTTP : avertissement sur le micro, rien en HTTPS ou si l'information manque", () => {
  assert.match(scene.messageContexteMicro(false), /HTTP.*micro.*HTTPS/);
  assert.equal(scene.messageContexteMicro(true), null);
  assert.equal(scene.messageContexteMicro(undefined), null);
});

test("styles : aucune couleur en dur hors des palettes, cibles tactiles, viewport dynamique", () => {
  const dossier = new URL("../../src/pnj_parlant/static/", import.meta.url);
  const css = readFileSync(new URL("style.css", dossier), "utf8");
  const sansPalettes = css.slice(0, css.indexOf("/* Vert-de-gris")) + css.slice(css.indexOf("@media (max-width: 40rem)"));
  const sansCommentaires = sansPalettes.replace(/\/\*[\s\S]*?\*\//g, "").replace(/--(blanc|noir):[^;]*;/g, "");
  assert.doesNotMatch(sansCommentaires, /(?<![-\w])(white|black)(?![-\w])|rgba?\(|#[0-9a-f]{3,8}\b/i);
  assert.match(css, /@media \(pointer: coarse\)[\s\S]*min-height: 2\.75rem/);
  for (const f of ["index.html", "creation.html"]) {
    const html = readFileSync(new URL(f, dossier), "utf8");
    const style = html.slice(html.indexOf("<style>"), html.indexOf("</style>")).replace(/\/\*[\s\S]*?\*\//g, "");
    assert.doesNotMatch(style, /(?<![-\w])(white|black)(?![-\w])|rgba?\(/i, f);
    for (const m of style.matchAll(/[^;{}]*\b(?:100|70)vh[^;]*;/g))  // chaque 100vh a sa ligne 100dvh juste après
      assert.ok(style.includes(m[0].replace(/vh\b/g, "dvh").trim()), `${f} : ${m[0]}`);
    assert.doesNotMatch(html, /onsubmit=/, f);
  }
});
