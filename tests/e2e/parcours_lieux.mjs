// Pilote Edge (protocole DevTools) comme un joueur : lieux, aborder, déplacement à la voix, compagnon.
import { spawn } from "node:child_process";

const [edge, profil, conversation] = process.argv.slice(2);
const navigateur = spawn(edge, ["--headless=new", "--disable-gpu", "--no-first-run", "--remote-debugging-port=9333",
                                `--user-data-dir=${profil}`, "about:blank"], { stdio: "ignore" });
const pause = (ms) => new Promise(r => setTimeout(r, ms));
let cible;
for (let i = 0; i < 50 && !cible; i++) {
  await pause(200);
  try { cible = (await (await fetch("http://127.0.0.1:9333/json/list")).json()).find(t => t.type === "page"); } catch {}
}
const ws = new WebSocket(cible.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let n = 0; const attente = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); attente.get(d.id)?.(d); attente.delete(d.id); };
const cdp = (method, params = {}) => new Promise(r => { const id = ++n; attente.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const js = async (expression) => (await cdp("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value;
async function quand(expression, ms = 8000) {
  for (let t = 0; t < ms; t += 100) { if (await js(expression)) return true; await pause(100); }
  return false;
}
const resultats = [];
const verifier = (nom, ok) => { resultats.push(`${ok ? "OK  " : "ÉCHEC"} ${nom}`); };

// Voix du navigateur instantanée : le casque n'existe pas en mode sans écran. Avec window.__lent, une
// phrase dure jusqu'à ce qu'on la coupe (speechSynthesis.cancel). Reconnaissance vocale simulée :
// elle « entend » window.__dicte.
const simulations = `
  window.speechSynthesis.speak = (u) => { if (window.__lent) window.__enCours = u; else setTimeout(() => u.onend && u.onend(), 5); };
  window.speechSynthesis.cancel = () => { const u = window.__enCours; window.__enCours = null; u && u.onend && u.onend(); };
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SR) SR.prototype.start = function () {
    window.__ecoute = (window.__ecoute || 0) + 1;
    setTimeout(() => {
      this.onstart && this.onstart();
      this.onresult && this.onresult({ results: [Object.assign([{ transcript: window.__dicte || "" }], { isFinal: true })] });
      this.onend && this.onend();
    }, 20);
  };`;
await cdp("Page.navigate", { url: "http://127.0.0.1:5917/#jeu" });
await quand(`!!document.getElementById("micBtn") && document.readyState === "complete"`);
await js(simulations);  // après le chargement : le script d'initialisation de page ne prend pas en Edge sans écran
verifier("menu des lieux rempli (aucun + 2 lieux)", await quand(`document.querySelectorAll("#lieuSel option").length === 3`));

await js(`(() => { const s = document.getElementById("lieuSel"); s.value = "auberge-du-sanglier"; s.dispatchEvent(new Event("change")); })()`);
verifier("narration de l'arrivée à l'auberge", await quand(`document.querySelector(".narration-line")?.textContent.includes("Vous arrivez : Auberge du Sanglier. Une salle enfumée.")`));
verifier("Ysolde est là, Brom non", await quand(`(() => { const t = document.getElementById("ici").textContent; return t.includes("Ysolde") && !t.includes("Brom"); })()`));

await quand(`[...document.querySelectorAll("[data-aborder]")].some(b => b.textContent.includes("Ysolde") && !b.disabled)`);  // fin de la narration
await js(`[...document.querySelectorAll("[data-aborder]")].find(b => b.textContent.includes("Ysolde")).click()`);
verifier("aborder Ysolde : fiche et salutation", await quand(`document.querySelector(".pnj-card h1")?.textContent === "Ysolde" && document.getElementById("log").textContent.includes("Bienvenue au Sanglier")`));
await quand(`!document.getElementById("ask").disabled`);

await js(`(() => { document.getElementById("ask").value = "Allons à la forge de Brom !"; document.getElementById("sendBtn").click(); })()`);
verifier("proposition de déplacement", await quand(`!document.getElementById("proposition").hidden && document.getElementById("propTexte").textContent === "Aller à : Forge de Brom ?"`));
verifier("Ysolde répond depuis l'auberge", await quand(`document.getElementById("log").textContent.includes("Moi, Ysolde, je suis bien à Auberge du Sanglier")`));
await quand(`!document.getElementById("propOui").disabled`);

await js(`(() => { const c = document.querySelector("[data-suit='0']"); c.checked = true; c.dispatchEvent(new Event("change", { bubbles: true })); })()`);
await js(`document.getElementById("propOui").click()`);
verifier("arrivée à la forge, menu à jour", await quand(`document.getElementById("lieuSel").value === "forge-de-brom" && [...document.querySelectorAll(".narration-line")].some(l => l.textContent.includes("Vous arrivez : Forge de Brom"))`));
verifier("Ysolde a suivi, Brom est là", await quand(`document.querySelector(".pnj-card h1")?.textContent === "Ysolde" && document.getElementById("ici").textContent.includes("Brom")`));
verifier("fiche : se trouve à la forge, habituellement à l'auberge", await js(`(() => { const t = document.querySelector(".pnj-card").textContent; return t.includes("Se trouve : Forge de Brom") && t.includes("Lieu habituel : Auberge du Sanglier"); })()`));
verifier("proposition masquée", await js(`document.getElementById("proposition").hidden`));
await quand(`!document.getElementById("ask").disabled`);

await js(`(() => { document.getElementById("ask").value = "Tu te plais ici ?"; document.getElementById("sendBtn").click(); })()`);
verifier("Ysolde répond depuis la forge", await quand(`document.getElementById("log").textContent.includes("Moi, Ysolde, je suis bien à Forge de Brom")`));
await quand(`!document.getElementById("ask").disabled`);

// Sans compagnon : Ysolde reste à la forge quand on retourne à l'auberge
await js(`(() => { const c = document.querySelector("[data-suit='0']"); c.checked = false; c.dispatchEvent(new Event("change", { bubbles: true })); const s = document.getElementById("lieuSel"); s.value = "auberge-du-sanglier"; s.dispatchEvent(new Event("change")); })()`);
verifier("Ysolde reste derrière (narration, scène vide)", await quand(`[...document.querySelectorAll(".narration-line")].some(l => l.textContent.includes("Ysolde reste derrière")) && !document.querySelector(".pnj-card")`));
verifier("de retour à l'auberge, Ysolde n'y est plus", await quand(`!document.getElementById("ici").textContent.includes("Ysolde") && !document.getElementById("ici").textContent.includes("Brom")`));

verifier("banque regroupée par lieu, Ysolde avec Brom à la forge", await js(`[...document.querySelectorAll("#bankSel optgroup")].map(o => o.label + " : " + [...o.children].map(c => c.textContent.split(" — ")[0]).join(", ")).join(" | ")`) === "Forge de Brom : Brom, Ysolde");

// Ysolde est restée à la forge : on l'y retrouve
await quand(`!document.getElementById("lieuSel").disabled`);  // fin de la narration précédente
await js(`(() => { const s = document.getElementById("lieuSel"); s.value = "forge-de-brom"; s.dispatchEvent(new Event("change")); })()`);
verifier("Ysolde retrouvée à la forge, avec Brom", await quand(`(() => { const t = document.getElementById("ici").textContent; return t.includes("Ysolde") && t.includes("Brom"); })()`));

// Import d'une conversation exportée : Ysolde vient de la banque, Gaspard est recréé par le modèle
await js(`window.confirm = () => true`);
const racine = (await cdp("DOM.getDocument")).result.root.nodeId;
const champ = (await cdp("DOM.querySelector", { nodeId: racine, selector: "#importFichier" })).result.nodeId;
await cdp("DOM.setFileInputFiles", { nodeId: champ, files: [conversation] });
verifier("import : dialogue et narration affichés", await quand(`(() => { const t = document.getElementById("log").textContent; return t.includes("Des rubans et des secrets.") && document.querySelector(".narration-line")?.textContent.includes("Vous arrivez : Forge de Brom"); })()`));
verifier("import : Ysolde et Gaspard en scène, à la forge", await quand(`[...document.querySelectorAll(".pnj-card h1")].map(h => h.textContent).join(", ") === "Ysolde, Gaspard le Colporteur" && document.getElementById("lieuSel").value === "forge-de-brom"`));
await quand(`!document.getElementById("ask").disabled`);
await js(`(() => { document.getElementById("ask").value = "Gaspard, tu as encore soif ?"; document.getElementById("sendBtn").click(); })()`);
verifier("import : Gaspard reprend la conversation", await quand(`document.getElementById("log").textContent.includes("Moi, Gaspard le Colporteur, je suis bien à Forge de Brom")`));
await quand(`!document.getElementById("ask").disabled`);

// Couper la parole au PNJ : sans l'option, « Parler » reste désactivé pendant qu'il parle
const option = (id, v) => js(`(() => { const c = document.getElementById("${id}"); c.checked = ${v}; c.dispatchEvent(new Event("change")); })()`);
const parle = `!document.getElementById("stopBtn").hidden && [...document.querySelectorAll("#log .line")].at(-1)?.textContent.includes("voyageur.")`;
await option("optInterrompre", false);
await js(`(() => { window.__lent = true; document.getElementById("ask").value = "Ysolde, et toi ?"; document.getElementById("sendBtn").click(); })()`);
verifier("sans l'option, « Parler » désactivé pendant que le PNJ parle", await quand(parle) && await js(`document.getElementById("micBtn").disabled`));
await js(`document.getElementById("stopBtn").click()`);
await quand(`!document.getElementById("ask").disabled`);

// Avec l'option : « Parler » coupe le PNJ, écoute le joueur, et le PNJ répond à la nouvelle question
await option("optInterrompre", true);
await js(`(() => { document.getElementById("ask").value = "Ysolde, et toi ?"; document.getElementById("sendBtn").click(); })()`);
verifier("avec l'option, « Parler » actif pendant que le PNJ parle", await quand(parle) && !await js(`document.getElementById("micBtn").disabled`));
await js(`(() => { window.__lent = false; window.__dicte = "Pardon, je vous coupe."; document.getElementById("micBtn").click(); })()`);
const lignes = `[...document.querySelectorAll("#log .line")].map(l => l.textContent)`;
verifier("« Parler » coupe le PNJ et transmet la question", await quand(`(() => {
  const l = ${lignes}, i = l.findIndex(t => t.includes("Pardon, je vous coupe."));
  return i > 0 && !l[i - 1].includes("Que veux-tu") && l.slice(i + 1).some(t => t.includes("Que veux-tu"));
})()`) && await js(`window.__ecoute === 1 && document.getElementById("stopBtn").hidden`));

// Accueil : la conversation en cours est proposée à la reprise ; l'exemple se charge ; un PNJ au hasard démarre
await quand(`!document.getElementById("ask").disabled`);
await js(`location.hash = ""`);
verifier("accueil affiché, conversation à reprendre", await quand(`document.body.dataset.vue === "accueil" && !document.getElementById("accReprendreBtn").hidden && document.querySelector("[data-exemple='pre-novice']")`));
await js(`document.querySelector("[data-exemple='pre-novice']").click()`);
verifier("exemple Pré-Novice chargé", await quand(`document.getElementById("accStatus").textContent === "Univers chargé : 3 lieux et 5 PNJ." && document.getElementById("universActuel").textContent.includes("3 lieux et 5 PNJ")`));
await js(`document.getElementById("accHasardBtn").click()`);
const pnjPreNovice = `["Rosalie Tampon", "Bertrand le Prudent", "Lyse", "Baron Grimmoire", "Oscar"]`;
verifier("PNJ au hasard : partie lancée", await quand(`document.body.dataset.vue === "jeu" && ${pnjPreNovice}.includes(document.querySelector(".pnj-card h1")?.textContent) && document.querySelectorAll("#log .line").length === 1`));
await quand(`!document.getElementById("ask").disabled`);  // salutation entièrement affichée (elle arrive morceau par morceau)
const salutation = await js(`document.querySelector("#log .line .text").textContent`);

// Rechargement de la page : la conversation est toujours là
await cdp("Page.reload");
await quand(`!!document.getElementById("micBtn") && document.readyState === "complete"`);
await js(simulations);
verifier("conversation reprise après rechargement", await quand(`${pnjPreNovice}.includes(document.querySelector(".pnj-card h1")?.textContent) && document.querySelector("#log .line .text")?.textContent === ${JSON.stringify(salutation)}`));

// Options : accessibles depuis la partie, retour à la partie
await js(`location.hash = "options"`);
verifier("options affichées, retour vers la partie", await quand(`document.body.dataset.vue === "options" && document.getElementById("optionsRetour").getAttribute("href") === "#jeu" && document.getElementById("optInterrompre").offsetParent !== null`));

console.log(resultats.join("\n"));
// Browser.close ferme tous les processus d'Edge (sous Windows, kill() laisse vivre ses enfants, port 9333 compris)
await Promise.race([cdp("Browser.close"), pause(2000)]);
ws.close(); navigateur.kill();
process.exit(resultats.some(r => r.startsWith("ÉCHEC")) ? 1 : 0);
