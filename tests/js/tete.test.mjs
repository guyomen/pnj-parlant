// Tests du script du <head> (src/pnj_parlant/static/js/tete.js) : script classique, exécuté ici dans un
// contexte vm avec un faux document et un faux localStorage, comme le ferait le navigateur avant l'affichage.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../src/pnj_parlant/static/js/tete.js", import.meta.url), "utf8");

function executer(stockage, session = {}) {
  const ajoutes = [];
  const document = {
    documentElement: { dataset: {} },
    head: { appendChild: (el) => ajoutes.push(el) },
    createElement: (tag) => ({ tag }),
  };
  const faux = (valeurs) => valeurs === null
    ? { getItem() { throw new Error("stockage interdit"); } }
    : { getItem: (cle) => valeurs[cle] ?? null };
  vm.runInNewContext(source, { document, localStorage: faux(stockage), sessionStorage: faux(session) });
  executer.mj = "mj" in document.documentElement.dataset;
  return { theme: document.documentElement.dataset.theme, ajoutes };
}

test("tete.js : mode MJ gardé par l'onglet posé avant l'affichage (<html data-mj>)", () => {
  executer({}, { "mode-mj": "1" });
  assert.equal(executer.mj, true);
  executer({}, {});
  assert.equal(executer.mj, false);
  executer({}, null);  // stockage interdit : mode joueur, sans erreur
  assert.equal(executer.mj, false);
});

test("tete.js : thème et CSS des thèmes de l'univers gardés posés avant l'affichage", () => {
  const { theme, ajoutes } = executer({ theme: "parchemin", "theme-css": "html[data-theme=\"x\"] { --bg: #000000; }" });
  assert.equal(theme, "parchemin");
  assert.deepEqual(ajoutes, [{ tag: "style", id: "themes-perso", textContent: "html[data-theme=\"x\"] { --bg: #000000; }" }]);
});

test("tete.js : rien de gardé = thème par défaut, aucune feuille ajoutée", () => {
  assert.deepEqual(executer({}), { theme: "", ajoutes: [] });
});

test("tete.js : stockage interdit (navigation privée stricte) sans erreur", () => {
  assert.deepEqual(executer(null), { theme: undefined, ajoutes: [] });
});

test("tete.js : chargé en script classique bloquant dans le <head> des deux pages, avant style.css", () => {
  for (const page of ["index.html", "creation.html"]) {
    const html = readFileSync(new URL(`../../src/pnj_parlant/static/${page}`, import.meta.url), "utf8");
    const tete = html.slice(0, html.indexOf("</head>"));
    assert.match(tete, /<script src="js\/tete\.js"><\/script>/, page);  // ni module, ni defer, ni async
    assert.ok(tete.indexOf("js/tete.js") < tete.indexOf("style.css"), page);
  }
});
