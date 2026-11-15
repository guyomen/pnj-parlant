// Tests du script du <head> (src/pnj_parlant/static/js/tete.js) : script classique, exécuté ici dans un
// contexte vm avec un faux document et un faux localStorage, comme le ferait le navigateur avant l'affichage.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../src/pnj_parlant/static/js/tete.js", import.meta.url), "utf8");

function executer(stockage) {
  const ajoutes = [];
  const document = {
    documentElement: { dataset: {} },
    head: { appendChild: (el) => ajoutes.push(el) },
    createElement: (tag) => ({ tag }),
  };
  const localStorage = stockage === null
    ? { getItem() { throw new Error("stockage interdit"); } }
    : { getItem: (cle) => stockage[cle] ?? null };
  vm.runInNewContext(source, { document, localStorage });
  return { theme: document.documentElement.dataset.theme, ajoutes };
}

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
